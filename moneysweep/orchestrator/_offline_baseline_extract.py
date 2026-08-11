"""Local-only cabilderos extraction and entity comparison."""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path
from typing import Any

from moneysweep.orchestrator._offline_baseline_core import (
    KEY_CANDIDATES,
    REGISTRATION_RE,
    WAYBACK_RE,
    OfflineBaselineViolation,
    _file_info,
    sanitized_child_environment,
    sha256_file,
)


def _pdf_text(pdf: Path, work_dir: Path) -> Path:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise OfflineBaselineViolation("pdftotext is required for cabilderos extraction")
    text_path = work_dir / "cabilderos.txt"
    subprocess.run(
        [executable, "-layout", str(pdf), str(text_path)],
        check=True,
        env=sanitized_child_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return text_path


def extract_cabilderos(pdf: Path, output_csv: Path, work_dir: Path) -> dict[str, Any]:
    pages = _pdf_text(pdf, work_dir).read_text(errors="replace").split("\f")
    current_url = ""
    current_timestamp = ""
    rows: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        snapshot = WAYBACK_RE.search(page)
        if snapshot:
            current_url = snapshot.group(1)
            current_timestamp = snapshot.group(2)
        lines = page.splitlines()
        for index, line in enumerate(lines):
            registrations = REGISTRATION_RE.findall(line)
            for registration in registrations:
                before = [
                    value.strip() for value in lines[max(0, index - 4) : index] if value.strip()
                ]
                after = [value.strip() for value in lines[index : index + 7] if value.strip()]
                prefix = line.split(registration, 1)[0].strip()
                name_parts = before[-2:] + ([prefix] if prefix else [])
                snapshot_date = ""
                if len(current_timestamp) >= 8:
                    snapshot_date = (
                        f"{current_timestamp[:4]}-{current_timestamp[4:6]}-{current_timestamp[6:8]}"
                    )
                rows.append(
                    {
                        "snapshot_url": current_url,
                        "snapshot_timestamp": current_timestamp,
                        "snapshot_date": snapshot_date,
                        "registration_number": registration,
                        "lobbyist_name_heuristic": " ".join(name_parts).strip(),
                        "source_page": page_number,
                        "context_raw": " | ".join(before[-3:] + after[:5]),
                        "extraction_status": "PROVISIONAL_REGISTRATION_INDEX",
                        "canonical_credit": "false",
                    }
                )
    rows.sort(
        key=lambda row: (
            str(row["snapshot_timestamp"]),
            str(row["registration_number"]),
            int(row["source_page"]),
        )
    )
    default_fields = [
        "snapshot_url",
        "snapshot_timestamp",
        "snapshot_date",
        "registration_number",
        "lobbyist_name_heuristic",
        "source_page",
        "context_raw",
        "extraction_status",
        "canonical_credit",
    ]
    fields = list(rows[0]) if rows else default_fields
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    unique_registrations = {str(row["registration_number"]) for row in rows}
    snapshots = sorted(
        {str(row["snapshot_timestamp"]) for row in rows if row["snapshot_timestamp"]}
    )
    return {
        "stage": "cabilderos_provisional_extraction",
        "status": "PROVISIONAL_NO_CANONICAL_CREDIT",
        "emitted_rows": len(rows),
        "unique_registration_numbers": len(unique_registrations),
        "duplicate_occurrences": len(rows) - len(unique_registrations),
        "snapshot_timestamps": snapshots,
        "output": _file_info(output_csv),
    }


def _normalized_keys(path: Path) -> tuple[dict[str, Any], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    key: str | None = None
    for candidate in KEY_CANDIDATES:
        if candidate not in columns:
            continue
        if any(" ".join((row.get(candidate) or "").casefold().split()) for row in rows):
            key = candidate
            break
    keys: set[str] = set()
    if key is not None:
        for row in rows:
            value = " ".join((row.get(key) or "").casefold().split())
            if value:
                keys.add(value)
    return (
        {
            "path": path.name,
            "file_sha256": sha256_file(path),
            "row_count": len(rows),
            "schema": columns,
            "stable_key_column": key,
            "nonblank_unique_keys": len(keys),
        },
        keys,
    )


def local_entity_comparison(left: Path, right: Path) -> dict[str, Any]:
    left_info, left_keys = _normalized_keys(left)
    right_info, right_keys = _normalized_keys(right)
    intersection = left_keys & right_keys
    union = left_keys | right_keys
    denominator = max(len(left_keys), len(right_keys))
    overlap = len(intersection) / denominator if denominator else 1.0
    if left_info["file_sha256"] == right_info["file_sha256"]:
        duplicate_status = "IDENTICAL_FILE"
    elif overlap >= 0.95:
        duplicate_status = "OVERLAPPING_DERIVED_PRODUCTS"
    else:
        duplicate_status = "DISTINCT_DERIVED_PRODUCTS"
    return {
        "schema_version": "entity_product_comparison_v2_local_fallback",
        "status": "COMPLETE",
        "left": left_info,
        "right": right_info,
        "stable_key_overlap": {
            "left_unique": len(left_keys),
            "right_unique": len(right_keys),
            "intersection_unique": len(intersection),
            "union_unique": len(union),
            "overlap_rate_max_denominator": round(overlap, 6),
            "jaccard_rate": round(len(intersection) / len(union), 6) if union else 1.0,
        },
        "duplicate_status": duplicate_status,
        "canonical_certification": False,
    }
