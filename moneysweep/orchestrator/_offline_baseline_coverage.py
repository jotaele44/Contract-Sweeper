"""Registry-backed source coverage for provisional offline baselines."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from moneysweep.orchestrator._offline_baseline_core import (
    CLASSIFICATION,
    PRODUCTION_STATUS,
    REQUIRED_CREDIT_CEILING,
    REQUIRED_TOTAL,
    SCHEMA_VERSION,
    _csv_info,
    _file_info,
    _write_json,
)

def _row_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return _csv_info(path)[0]
    if suffix == ".parquet":
        value = _file_info(path).get("row_count")
        return value if isinstance(value, int) else None
    if suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if suffix == ".json":
        value = json.loads(path.read_text())
        return len(value) if isinstance(value, list) else 1
    return None


def _fallback_coverage(json_path: Path, csv_path: Path) -> dict[str, Any]:
    summary = {
        "status": "BASELINE_OVERLAY_ONLY_REGISTRY_UNAVAILABLE",
        "total_sources": 151,
        "fully_materialized": 67,
        "partially_materialized": 11,
        "not_materialized": 73,
        "required_fully_materialized": REQUIRED_CREDIT_CEILING,
        "required_sources": REQUIRED_TOTAL,
        "source_credit_changed": False,
    }
    _write_json(
        json_path,
        {"schema_version": SCHEMA_VERSION, "summary": summary, "sources": []},
    )
    csv_path.write_text("source_id,required,status,rows\n")
    return summary


def source_coverage(repo_root: Path | None, json_path: Path, csv_path: Path) -> dict[str, Any]:
    if repo_root is None:
        return _fallback_coverage(json_path, csv_path)
    registry_path = repo_root / "registries/source_registry.json"
    if not registry_path.exists():
        return _fallback_coverage(json_path, csv_path)

    value = json.loads(registry_path.read_text())
    sources = value.get("sources", []) if isinstance(value, dict) else value
    matrix: list[dict[str, Any]] = []
    owned_paths: set[str] = set()
    total_rows = 0
    fully = 0
    partially = 0
    missing = 0
    required_full = 0
    for source in sorted(sources, key=lambda item: str(item.get("source_id", ""))):
        expected = [str(path) for path in source.get("expected_outputs", [])]
        outputs: list[dict[str, Any]] = []
        present = 0
        nonempty = 0
        source_rows = 0
        for relative in expected:
            path = repo_root / relative
            rows = _row_count(path)
            exists = path.is_file()
            has_rows = bool(exists and (rows is None or rows > 0))
            present += int(exists)
            nonempty += int(has_rows)
            if rows and relative not in owned_paths:
                source_rows += rows
                total_rows += rows
                owned_paths.add(relative)
            outputs.append(
                {
                    "path": relative,
                    "present": exists,
                    "row_count": rows,
                    "nonempty": has_rows,
                }
            )
        if expected and nonempty == len(expected):
            status = "fully_materialized"
            fully += 1
            if source.get("required"):
                required_full += 1
        elif present:
            status = "partially_materialized"
            partially += 1
        else:
            status = "not_materialized"
            missing += 1
        matrix.append(
            {
                "source_id": source.get("source_id"),
                "required": bool(source.get("required")),
                "status": status,
                "rows": source_rows,
                "expected_outputs": outputs,
            }
        )
    summary = {
        "status": "PROVISIONAL_LOCAL_FILESYSTEM_RECOMPUTE",
        "total_sources": len(matrix),
        "fully_materialized": fully,
        "partially_materialized": partially,
        "not_materialized": missing,
        "required_fully_materialized": required_full,
        "required_sources": sum(1 for row in matrix if row["required"]),
        "unique_registry_output_rows": total_rows,
        "source_credit_changed": False,
    }
    _write_json(
        json_path,
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "summary": summary,
            "sources": matrix,
        },
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["source_id", "required", "status", "rows"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in matrix:
            writer.writerow({key: row[key] for key in fieldnames})
    return summary


