"""Validate immutable guide-source snapshots and regenerate bounded audit outputs.

This script does not acquire sources by itself. It validates already-materialized
OCIF, OCS and FTZ snapshot runs, verifies raw bytes and processed outputs against
manifest hashes/counts, computes CSV schema fingerprints, then regenerates the
30-avenue/158-source audit. Certification remains fail-closed and the bounded
scope must never be promoted to ALL_PUERTO_RICO_FINANCE.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from scripts.audit_guide_financial_avenues import run as run_guide_audit
from scripts.config import PROJECT_ROOT

SNAPSHOT_SOURCES = (
    "ocif_guide_financial_classes",
    "ocs_insurer_registry",
    "ftz_board_pr",
)
SNAPSHOT_SCHEMA = "guide_source_snapshot_manifest_v1"
PUBLIC_ADJ_REL = Path("registries/guide_public_denominator_adjudications_v1.yaml")
REPORT_REL = Path("reports/guide_financial_live_freeze_v1.json")
CERT_REL = Path("reports/guide_bounded_100_percent_certification_v1.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_schema(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        row_count = sum(1 for _ in reader)
    encoded = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "columns": header,
        "column_count": len(header),
        "row_count": row_count,
        "schema_fingerprint_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected YAML mapping: {path}")
    return value


def latest_manifest(snapshot_root: Path, source_id: str) -> Path:
    source_dir = snapshot_root / source_id
    manifests = sorted(source_dir.glob("*/manifest.json")) if source_dir.exists() else []
    if not manifests:
        raise RuntimeError(f"{source_id}: no immutable snapshot manifest under {source_dir}")
    return manifests[-1]


def _processed_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(manifest.get("processed_outputs"), list):
        return [dict(x) for x in manifest["processed_outputs"]]
    if isinstance(manifest.get("processed_output"), dict):
        return [dict(manifest["processed_output"])]
    return []


def validate_source_snapshot(root: Path, snapshot_root: Path, source_id: str) -> dict[str, Any]:
    manifest_path = latest_manifest(snapshot_root, source_id)
    manifest = _load_json(manifest_path)
    errors: list[str] = []

    if manifest.get("schema_version") != SNAPSHOT_SCHEMA:
        errors.append(f"manifest schema != {SNAPSHOT_SCHEMA}")
    if manifest.get("source_id") != source_id:
        errors.append(f"manifest source_id={manifest.get('source_id')!r}")

    manifestations = manifest.get("manifestations")
    if not isinstance(manifestations, list) or not manifestations:
        errors.append("no manifestations")
        manifestations = []

    raw_receipts: list[dict[str, Any]] = []
    for index, item in enumerate(manifestations):
        if not isinstance(item, dict):
            errors.append(f"manifestation[{index}] not object")
            continue
        for field in ("url", "retrieved_at_utc", "byte_size", "sha256", "raw_file", "retained_rows"):
            if field not in item:
                errors.append(f"manifestation[{index}] missing {field}")
        raw_file = str(item.get("raw_file") or "")
        raw_path = manifest_path.parent / raw_file if raw_file else None
        observed_size = None
        observed_sha = None
        if raw_path is None or not raw_path.is_file():
            errors.append(f"manifestation[{index}] raw file missing: {raw_file!r}")
        else:
            observed_size = raw_path.stat().st_size
            observed_sha = sha256_file(raw_path)
            if observed_size != int(item.get("byte_size", -1)):
                errors.append(f"manifestation[{index}] byte-size mismatch")
            if observed_sha != str(item.get("sha256") or ""):
                errors.append(f"manifestation[{index}] sha256 mismatch")
        raw_receipts.append(
            {
                "index": index,
                "url": item.get("url"),
                "retrieved_at_utc": item.get("retrieved_at_utc"),
                "raw_file": raw_file,
                "byte_size": observed_size,
                "sha256": observed_sha,
                "retained_rows": item.get("retained_rows"),
            }
        )

    processed = _processed_entries(manifest)
    if not processed:
        errors.append("no processed output receipt")
    processed_receipts: list[dict[str, Any]] = []
    for index, item in enumerate(processed):
        rel = str(item.get("path") or "")
        path = root / rel if rel else None
        if path is None or not path.is_file():
            errors.append(f"processed[{index}] missing path: {rel!r}")
            continue
        observed_size = path.stat().st_size
        observed_sha = sha256_file(path)
        if observed_size != int(item.get("byte_size", -1)):
            errors.append(f"processed[{index}] byte-size mismatch")
        if observed_sha != str(item.get("sha256") or ""):
            errors.append(f"processed[{index}] sha256 mismatch")
        schema = csv_schema(path)
        if schema["row_count"] != int(item.get("row_count", -1)):
            errors.append(f"processed[{index}] row-count mismatch")
        processed_receipts.append(
            {
                "path": rel,
                "byte_size": observed_size,
                "sha256": observed_sha,
                **schema,
            }
        )

    return {
        "source_id": source_id,
        "manifest_path": str(manifest_path.relative_to(root)),
        "manifest_sha256": sha256_file(manifest_path),
        "run_started_at_utc": manifest.get("run_started_at_utc"),
        "raw_manifestation_count": len(raw_receipts),
        "raw_manifestations": raw_receipts,
        "processed_outputs": processed_receipts,
        "errors": errors,
        "state": "PASS" if not errors else "FAIL",
    }


def build_certification(root: Path, freeze_report: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    public_adj = _load_yaml(root / PUBLIC_ADJ_REL)
    adjudications = public_adj.get("adjudications") or {}
    public_open = sorted(
        key
        for key, value in adjudications.items()
        if isinstance(value, dict) and str(value.get("certification_state", "OPEN")) != "PASS"
    )
    source_failures = sorted(
        item["source_id"] for item in freeze_report["sources"] if item["state"] != "PASS"
    )
    metrics = audit["metrics_payload"]
    guide_projection = metrics["guide_projection"]
    residue = {
        "source_snapshot_failures": source_failures,
        "public_denominator_open": public_open,
        "a_only": guide_projection.get("a_only", []),
        "symmetric_difference": guide_projection.get("symmetric_difference", []),
    }
    zero_residue = not any(residue.values())
    return {
        "schema_version": "guide_bounded_100_percent_certification_v1",
        "scope_id": "GUIDE_BOUNDED_100_PERCENT",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "guide_avenue_count": metrics["guide_avenue_count"],
        "base_source_count": metrics["base_source_count"],
        "set_metrics": guide_projection,
        "source_snapshot_report": str(REPORT_REL),
        "source_snapshot_report_sha256": sha256_file(root / REPORT_REL),
        "public_denominator_registry": str(PUBLIC_ADJ_REL),
        "public_denominator_registry_sha256": sha256_file(root / PUBLIC_ADJ_REL),
        "residue": residue,
        "unresolved_residue_count": sum(len(value) for value in residue.values()),
        "certification_state": "PASS" if zero_residue else "OPEN",
        "scope_limitation": "GUIDE_BOUNDED_100_PERCENT != ALL_PUERTO_RICO_FINANCE",
    }


def run(root: Path = PROJECT_ROOT, *, snapshot_dir: str) -> dict[str, Any]:
    snapshot_root = root / snapshot_dir
    source_results = [validate_source_snapshot(root, snapshot_root, sid) for sid in SNAPSHOT_SOURCES]
    freeze_report = {
        "schema_version": "guide_financial_live_freeze_v1",
        "scope_id": "GUIDE_BOUNDED_100_PERCENT",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot_root": snapshot_dir,
        "sources": source_results,
        "source_states": {item["source_id"]: item["state"] for item in source_results},
        "all_snapshot_gates_pass": all(item["state"] == "PASS" for item in source_results),
        "scope_limitation": "GUIDE_BOUNDED_100_PERCENT != ALL_PUERTO_RICO_FINANCE",
    }
    report_path = root / REPORT_REL
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(freeze_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    audit = run_guide_audit(root, write=True)
    certification = build_certification(root, freeze_report, audit)
    cert_path = root / CERT_REL
    cert_path.write_text(json.dumps(certification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "freeze_report": freeze_report,
        "audit_metrics": audit["metrics_payload"],
        "certification": certification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        default="data/raw/guide_financial_avenue_snapshots",
        help="repository-relative immutable snapshot root",
    )
    args = parser.parse_args()
    result = run(snapshot_dir=args.snapshot_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["freeze_report"]["all_snapshot_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
