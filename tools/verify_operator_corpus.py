from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.operator_corpus_common import (
        CORPUS_SCHEMA_VERSION,
        RECEIPT_SCHEMA_VERSION,
        VERIFICATION_SCHEMA_VERSION,
        csv_rows,
        expected_outputs,
        load_sources,
        manifest_digest,
        safe_relative_path,
        sha256_file,
        source_definition_digest,
        source_ids_digest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from operator_corpus_common import (  # type: ignore[no-redef]
        CORPUS_SCHEMA_VERSION,
        RECEIPT_SCHEMA_VERSION,
        VERIFICATION_SCHEMA_VERSION,
        csv_rows,
        expected_outputs,
        load_sources,
        manifest_digest,
        safe_relative_path,
        sha256_file,
        source_definition_digest,
        source_ids_digest,
    )


def _expected_claims(output_path: str, expected: list[str]) -> bool:
    for item in expected:
        if item.endswith("/"):
            if output_path.startswith(item):
                return True
        elif output_path == item:
            return True
    return False


def _expected_satisfied(expected_path: str, actual_paths: set[str]) -> bool:
    if expected_path.endswith("/"):
        return any(path.startswith(expected_path) for path in actual_paths)
    return expected_path in actual_paths


def verify(*, root: Path, corpus_root: Path) -> dict[str, Any]:
    root = root.resolve()
    corpus_root = corpus_root.resolve()
    errors: list[str] = []
    sources, registry_paths = load_sources(root)
    source_by_id = {str(source["source_id"]): source for source in sources}
    current_registry_digest = source_ids_digest(sources)
    current_required = sum(source.get("required") is True for source in sources)

    manifest_path = corpus_root / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"operator corpus manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("operator corpus manifest must contain an object")

    if manifest.get("schema_version") != CORPUS_SCHEMA_VERSION:
        errors.append("unsupported_corpus_schema")
    claimed_corpus_id = manifest.get("corpus_id")
    computed_corpus_id = manifest_digest(manifest)
    if claimed_corpus_id != computed_corpus_id:
        errors.append("corpus_id_mismatch")

    registry = manifest.get("registry")
    if not isinstance(registry, dict):
        registry = {}
        errors.append("manifest_registry_missing")
    if registry.get("total_sources") != len(sources):
        errors.append("registry_total_sources_mismatch")
    if registry.get("required_sources") != current_required:
        errors.append("registry_required_sources_mismatch")
    if registry.get("source_ids_sha256") != current_registry_digest:
        errors.append("registry_source_ids_digest_mismatch")
    if registry.get("registry_paths") != registry_paths:
        errors.append("registry_paths_mismatch")

    manifest_sources = manifest.get("sources")
    if not isinstance(manifest_sources, list):
        manifest_sources = []
        errors.append("manifest_sources_missing")

    seen_source_ids: set[str] = set()
    manifest_output_paths: set[str] = set()
    source_results: list[dict[str, Any]] = []
    for entry in manifest_sources:
        if not isinstance(entry, dict):
            errors.append("invalid_manifest_source_entry")
            continue
        source_id = str(entry.get("source_id", "")).strip()
        source_errors: list[str] = []
        if not source_id:
            errors.append("empty_manifest_source_id")
            continue
        if source_id in seen_source_ids:
            errors.append(f"duplicate_manifest_source:{source_id}")
            continue
        seen_source_ids.add(source_id)
        source = source_by_id.get(source_id)
        if source is None:
            errors.append(f"unknown_manifest_source:{source_id}")
            continue

        definition_digest = source_definition_digest(source)
        if entry.get("source_definition_sha256") != definition_digest:
            source_errors.append("source_definition_digest_mismatch")

        receipt_rel = safe_relative_path(str(entry.get("receipt_path", "")))
        receipt_path = corpus_root / receipt_rel
        if not receipt_path.exists() or not receipt_path.is_file():
            source_errors.append("receipt_missing")
            receipt: dict[str, Any] = {}
        else:
            if sha256_file(receipt_path) != entry.get("receipt_sha256"):
                source_errors.append("receipt_sha256_mismatch")
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt = payload if isinstance(payload, dict) else {}
            if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
                source_errors.append("receipt_schema_mismatch")
            if receipt.get("source_id") != source_id:
                source_errors.append("receipt_source_id_mismatch")
            receipt_registry = receipt.get("registry")
            if not isinstance(receipt_registry, dict):
                source_errors.append("receipt_registry_missing")
            else:
                if receipt_registry.get("source_ids_sha256") != current_registry_digest:
                    source_errors.append("receipt_registry_digest_mismatch")
                if receipt_registry.get("source_definition_sha256") != definition_digest:
                    source_errors.append("receipt_definition_digest_mismatch")

        outputs = entry.get("outputs")
        if not isinstance(outputs, list):
            outputs = []
            source_errors.append("manifest_outputs_missing")
        actual_paths: set[str] = set()
        receipt_outputs = receipt.get("outputs") if isinstance(receipt, dict) else None
        receipt_by_path = {
            str(item.get("path")): item
            for item in receipt_outputs or []
            if isinstance(item, dict) and item.get("path")
        }

        for output in outputs:
            if not isinstance(output, dict):
                source_errors.append("invalid_manifest_output")
                continue
            rel = safe_relative_path(str(output.get("path", ""))).as_posix()
            actual_paths.add(rel)
            manifest_output_paths.add(rel)
            expected = expected_outputs(source)
            if not _expected_claims(rel, expected):
                source_errors.append(f"undeclared_output:{rel}")

            receipt_output = receipt_by_path.get(rel)
            if receipt_output is None:
                source_errors.append(f"receipt_output_missing:{rel}")
            else:
                for key in ("sha256", "bytes", "rows"):
                    if receipt_output.get(key) != output.get(key):
                        source_errors.append(f"receipt_manifest_{key}_mismatch:{rel}")

            object_rel = safe_relative_path(str(output.get("object", "")))
            object_path = corpus_root / object_rel
            mount_path = corpus_root / "mount" / rel
            expected_sha = output.get("sha256")
            expected_bytes = output.get("bytes")
            expected_rows = output.get("rows")
            for label, path in (("object", object_path), ("mount", mount_path)):
                if not path.exists() or not path.is_file():
                    source_errors.append(f"{label}_missing:{rel}")
                    continue
                if sha256_file(path) != expected_sha:
                    source_errors.append(f"{label}_sha256_mismatch:{rel}")
                if path.stat().st_size != expected_bytes:
                    source_errors.append(f"{label}_bytes_mismatch:{rel}")
                if csv_rows(path) != expected_rows:
                    source_errors.append(f"{label}_rows_mismatch:{rel}")

        missing_expected = [
            item for item in expected_outputs(source) if not _expected_satisfied(item, actual_paths)
        ]
        validation = receipt.get("validation") if isinstance(receipt, dict) else None
        source_results.append(
            {
                "source_id": source_id,
                "required": source.get("required") is True,
                "expected_output_count": len(expected_outputs(source)),
                "present_output_count": len(actual_paths),
                "missing_expected_outputs": missing_expected,
                "coverage_contract_pass": (
                    validation.get("coverage_contract_pass")
                    if isinstance(validation, dict)
                    else None
                ),
                "receipt_schema_valid": (
                    validation.get("schema_valid") if isinstance(validation, dict) else None
                ),
                "errors": sorted(set(source_errors)),
            }
        )
        errors.extend(f"{source_id}:{item}" for item in source_errors)

    processed_dir = corpus_root / "mount" / "data" / "staging" / "processed"
    processed_paths: set[str] = set()
    if processed_dir.exists():
        for path in processed_dir.rglob("*.csv"):
            processed_paths.add(path.relative_to(corpus_root / "mount").as_posix())
    orphan_processed = sorted(processed_paths - manifest_output_paths)
    if orphan_processed:
        errors.extend(f"orphan_processed_file:{path}" for path in orphan_processed)

    report = {
        "schema_version": VERIFICATION_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verified": not errors,
        "operator_corpus_authoritative": not errors,
        "corpus_id": claimed_corpus_id,
        "computed_corpus_id": computed_corpus_id,
        "registry": {
            "total_sources": len(sources),
            "required_sources": current_required,
            "source_ids_sha256": current_registry_digest,
            "registry_paths": registry_paths,
        },
        "manifest_source_count": len(seen_source_ids),
        "processed_file_inventory": {
            "total_csv_files": len(processed_paths),
            "orphan_files": orphan_processed,
            "orphan_file_count": len(orphan_processed),
        },
        "sources": sorted(source_results, key=lambda item: item["source_id"]),
        "errors": sorted(set(errors)),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an operator corpus fail-closed.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--corpus-root", type=Path, default=Path("build/operator-corpus"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/operator_corpus_verification.json")
    )
    args = parser.parse_args()

    report = verify(root=args.root, corpus_root=args.corpus_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verified": report["verified"],
                "corpus_id": report["corpus_id"],
                "errors": len(report["errors"]),
            },
            sort_keys=True,
        )
    )
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
