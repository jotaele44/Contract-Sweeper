"""Execution and immutable receipts for the offline baseline profile."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from moneysweep.orchestrator._offline_baseline_core import (
    CLASSIFICATION,
    PRODUCTION_STATUS,
    REQUIRED_CREDIT_CEILING,
    REQUIRED_TOTAL,
    SCHEMA_VERSION,
    BaselineConfig,
    OfflineBaselineViolation,
    _credential_names,
    _file_info,
    _write_json,
    block_network,
    discover_inputs,
    sha256_file,
)
from moneysweep.orchestrator._offline_baseline_coverage import source_coverage
from moneysweep.orchestrator._offline_baseline_extract import (
    extract_cabilderos,
    local_entity_comparison,
)


def _stage_inputs(found: Sequence[Mapping[str, Any]], repo_root: Path) -> list[dict[str, Any]]:
    staged: list[dict[str, Any]] = []
    for record in found:
        source = Path(str(record["source_path"]))
        destination = repo_root / str(record["stage_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        staged.append(
            {
                "logical_name": record["logical_name"],
                "destination": destination.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(destination),
                "status": "STAGED_LOCAL_ONLY",
            }
        )
    return staged


def _run_repo_stages(workspace_root: Path, output_dir: Path) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    try:
        from scripts.ingest_cor3 import run as ingest_cor3
    except ImportError as error:
        stages.append(
            {
                "stage": "cor3_ingest",
                "status": "BLOCKED_IMPORT_ERROR",
                "detail": str(error),
            }
        )
    else:
        result = ingest_cor3(root=workspace_root, force=True)
        output = workspace_root / "data/staging/processed/pr_cor3_projects.csv"
        stages.append(
            {
                "stage": "cor3_ingest",
                "status": result.get("status", "UNKNOWN"),
                "rows": result.get("rows", 0),
                "output": (
                    _file_info(output, output.relative_to(workspace_root).as_posix())
                    if output.exists()
                    else None
                ),
            }
        )

    stages.append(
        {
            "stage": "unified_master",
            "status": "SUPPLIED_PRODUCT_VALIDATED_NO_PARTIAL_CORPUS_REBUILD",
            "path": "data/staging/processed/entity_master.csv",
        }
    )
    try:
        from scripts.compare_entity_products import compare
    except ImportError as error:
        stages.append(
            {
                "stage": "entity_product_comparison_v2",
                "status": "BLOCKED_IMPORT_ERROR",
                "detail": str(error),
            }
        )
    else:
        report = compare(
            workspace_root / "data/staging/processed/entity_master.csv",
            workspace_root / "data/staging/processed/pr_entity_profiles.csv",
        )
        _write_json(output_dir / "entity_product_comparison.json", report)
        stages.append(
            {
                "stage": "entity_product_comparison_v2",
                "status": report.get("status"),
                "duplicate_status": report.get("duplicate_status"),
            }
        )
    return stages


def _input_digest(found: Sequence[Mapping[str, Any]], git_sha: str) -> str:
    compact = []
    for row in sorted(found, key=lambda item: str(item["logical_name"])):
        compact.append(
            {
                "logical_name": row["logical_name"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "row_count": row.get("row_count"),
            }
        )
    payload = json.dumps(
        {"schema_version": SCHEMA_VERSION, "git_sha": git_sha, "inputs": compact},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _blocked_sources(found: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    names = {str(row["logical_name"]) for row in found}
    cabilderos_status = "BLOCKED_MISSING_STRUCTURED_EXPORT"
    if "cabilderos_pdf" in names:
        cabilderos_status = "PROVISIONAL_PDF_INDEX_NO_CANONICAL_CREDIT"
    cor3_status = "BLOCKED_MISSING_OFFICIAL_WORKBOOK"
    if "cor3_official_workbook" in names:
        cor3_status = "LOCAL_INGEST_PRESENT_CREDIT_HELD_PENDING_RECEIPT"
    pairs = [
        ("hud_drgr_authorized", "BLOCKED_MISSING_AUTHORIZED_EXPORTS"),
        ("prasa", "BLOCKED_MISSING_OFFICIAL_FILTERED_EXPORT"),
        ("pr_cabilderos", cabilderos_status),
        ("cms_provider_enrichment", "BLOCKED_MISSING_PROVIDER_LEVEL_INPUT"),
        ("export_receipts", "BLOCKED_MISSING_AUTHORITATIVE_RECEIPT_MANIFEST"),
        ("cor3", cor3_status),
    ]
    return [
        {"source_id": source_id, "status": status, "canonical_credit": False}
        for source_id, status in pairs
    ]


def _file_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for path in root.rglob("*"):
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha256_file(path)
    return hashes


def _finalize(temp_dir: Path, final_dir: Path) -> str:
    if final_dir.exists():
        if _file_hashes(final_dir) != _file_hashes(temp_dir):
            raise OfflineBaselineViolation("immutable run directory contains different bytes")
        shutil.rmtree(temp_dir)
        return "EXISTING_IDENTICAL"
    temp_dir.replace(final_dir)
    return "CREATED"


def _existing_generated_at(final_dir: Path) -> str | None:
    receipt = final_dir / "run_receipt.json"
    if not receipt.exists():
        return None
    try:
        value = json.loads(receipt.read_text(encoding="utf-8")).get("generated_at")
    except (OSError, json.JSONDecodeError):
        return None
    return str(value) if value else None


def _empty_required_inputs(found: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    empty = []
    for row in found:
        if not row.get("required_for_run"):
            continue
        size = int(row.get("size_bytes") or 0)
        row_count = row.get("row_count")
        if size == 0 or row_count == 0:
            empty.append(dict(row))
    return empty


def _find_input(found: Sequence[Mapping[str, Any]], logical_name: str) -> Path | None:
    for row in found:
        if row["logical_name"] == logical_name:
            return Path(str(row["source_path"]))
    return None


def run_offline_baseline(config: BaselineConfig) -> dict[str, Any]:
    input_dir = config.input_dir.resolve()
    output_root = config.output_root.resolve()
    repo_root = config.repo_root.resolve() if config.repo_root else None
    output_root.mkdir(parents=True, exist_ok=True)
    found, missing = discover_inputs(input_dir)
    required_missing = [row for row in missing if row["required_for_run"]]
    if config.strict_inputs and required_missing:
        names = ", ".join(str(row["logical_name"]) for row in required_missing)
        raise OfflineBaselineViolation(f"missing required local inputs: {names}")
    if config.strict_inputs:
        required_empty = _empty_required_inputs(found)
        if required_empty:
            names = ", ".join(str(row["logical_name"]) for row in required_empty)
            raise OfflineBaselineViolation(f"empty required local inputs: {names}")

    digest = _input_digest(found, config.git_sha)
    run_id = f"offline-baseline-{digest[:16]}"
    temp_dir = output_root / f".{run_id}.tmp"
    final_dir = output_root / run_id
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    generated_at = (
        config.generated_at
        or _existing_generated_at(final_dir)
        or datetime.now(timezone.utc).isoformat()
    )

    public_inputs = []
    for row in found:
        public_inputs.append({key: value for key, value in row.items() if key != "source_path"})
    _write_json(
        temp_dir / "input_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "git_sha": config.git_sha,
            "generated_at": generated_at,
            "input_manifest_sha256": digest,
            "credentials_present_but_not_used": _credential_names(os.environ),
            "inputs": public_inputs,
            "missing_inputs": missing,
        },
    )
    _write_json(
        temp_dir / "preexisting_outputs_manifest.json",
        {"schema_version": SCHEMA_VERSION, "outputs": []},
    )

    staged: list[dict[str, Any]] = []
    with block_network():
        if repo_root is not None:
            workspace_root = temp_dir / "repo_workspace"
            staged = _stage_inputs(found, workspace_root)
            stages = _run_repo_stages(workspace_root, temp_dir)
        else:
            stages = [
                {
                    "stage": "cor3_ingest",
                    "status": "LOCAL_VALIDATED_OUTPUT_USED_REPOSITORY_UNAVAILABLE",
                },
                {
                    "stage": "unified_master",
                    "status": "SUPPLIED_PRODUCT_VALIDATED_NO_PARTIAL_CORPUS_REBUILD",
                },
                {"stage": "entity_product_comparison_v2", "status": "LOCAL_FALLBACK"},
            ]
        pdf = _find_input(found, "cabilderos_pdf")
        if pdf is None:
            stages.append(
                {
                    "stage": "cabilderos_provisional_extraction",
                    "status": "BLOCKED_MISSING_PDF",
                }
            )
        else:
            stages.append(
                extract_cabilderos(pdf, temp_dir / "pr_cabilderos_provisional.csv", temp_dir)
            )

    if repo_root is None:
        left = _find_input(found, "entity_master")
        right = _find_input(found, "entity_profiles")
        if left is not None and right is not None:
            _write_json(
                temp_dir / "entity_product_comparison.json",
                local_entity_comparison(left, right),
            )

    coverage = source_coverage(
        repo_root,
        temp_dir / "source_coverage_matrix.json",
        temp_dir / "source_coverage_matrix.csv",
    )
    blocked = _blocked_sources(found)
    _write_json(
        temp_dir / "blocked_source_ledger.json",
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "blocked_sources": blocked,
        },
    )
    required_after = int(coverage.get("required_fully_materialized", REQUIRED_CREDIT_CEILING))
    required_after = min(required_after, REQUIRED_CREDIT_CEILING)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "classification": CLASSIFICATION,
        "production_status": PRODUCTION_STATUS,
        "generated_at": generated_at,
        "git_sha": config.git_sha,
        "input_manifest_sha256": digest,
        "staged_inputs": staged,
        "stages": stages,
        "coverage_summary": coverage,
        "required_source_credit": {
            "before": REQUIRED_CREDIT_CEILING,
            "after": required_after,
            "required_total": REQUIRED_TOTAL,
            "credit_changed": False,
            "policy": "Fail closed until receipt-backed authoritative exports are validated.",
        },
        "blocked_source_count": len(blocked),
        "network_access_authorized": False,
        "credential_execution_authorized": False,
        "raw_data_commit_authorized": False,
        "data_promotion_authorized": False,
        "production_activation_authorized": False,
        "canonical_certification": False,
        "no_double_counting_policy": "Each registry output path contributes rows at most once.",
        "reproducibility_command": (
            "python3 run_all.py --profile offline-baseline "
            f"--offline-git-sha {config.git_sha} --offline-generated-at {generated_at}"
        ),
    }
    _write_json(temp_dir / "run_receipt.json", receipt)

    outputs = []
    for path in sorted(temp_dir.rglob("*")):
        if path.is_file() and path.name != "output_manifest.json":
            outputs.append(_file_info(path, path.relative_to(temp_dir).as_posix()))
    _write_json(
        temp_dir / "output_manifest.json",
        {"schema_version": SCHEMA_VERSION, "run_id": run_id, "outputs": outputs},
    )
    receipt_sha = sha256_file(temp_dir / "run_receipt.json")
    sums = []
    for path in sorted(temp_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(temp_dir).as_posix()
            sums.append(f"{sha256_file(path)}  {relative}")
    (temp_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    immutable_status = _finalize(temp_dir, final_dir)
    return {
        "status": "PASS_PROVISIONAL_BASELINE",
        "immutable_status": immutable_status,
        "run_id": run_id,
        "output_dir": final_dir.as_posix(),
        "receipt_sha256": receipt_sha,
        "classification": CLASSIFICATION,
        "production_status": PRODUCTION_STATUS,
        "coverage_summary": coverage,
        "blocked_source_count": len(blocked),
    }
