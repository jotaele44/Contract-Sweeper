"""Unit tests for the DTOP centerline segment producer (offline, fixture-based).

Exercises scripts/ingest_dtop_centerline_lrs.py end to end against an operator
centerline CSV fixture — no network, no registry surface. Every emitted row must
validate against schemas/roadwatch_segment.schema.json with a deterministic
segment_uid and the operator-provided Cell_ID carried through; rows lacking a
resolved Cell_ID are held (counted, not emitted), per the staging rule.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from moneysweep.validation.canonical_v1_schema import validate_row
from scripts.ingest_dtop_centerline_lrs import (
    OUTPUT_COLUMNS,
    _uid,
    build_segment,
    run,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "roadwatch_segment.schema.json").read_text(encoding="utf-8")
)

# Operator GIS export: two resolved rows (carry Cell_ID) + one unresolved (no cell).
CENTERLINE_ROWS = [
    {
        "route_id": "PR-52",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "0",
        "km_end": "10",
        "municipality": "Caguas",
        "Cell_ID": "R10_C20",
    },
    {
        "route_id": "PR-52",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "10",
        "km_end": "20",
        "municipality": "Caguas",
        "Cell_ID": "R11_C21",
    },
    # No resolved cell -> held_unresolved (not emitted).
    {
        "route_id": "PR-22",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "0",
        "km_end": "5",
        "municipality": "Bayamon",
        "Cell_ID": "",
    },
]

CENTERLINE_COLUMNS = [
    "route_id",
    "route_class",
    "direction",
    "km_start",
    "km_end",
    "municipality",
    "Cell_ID",
]


def _write_export(root: Path, rows: list[dict[str, str]], name: str = "export.csv") -> None:
    drop = root / "data" / "manual" / "dtop_centerline_lrs"
    drop.mkdir(parents=True, exist_ok=True)
    with (drop / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CENTERLINE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CENTERLINE_COLUMNS})


def _read_output(root: Path) -> list[dict[str, str]]:
    out = root / "data" / "staging" / "processed" / "pr_roadwatch_segments.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_emits_valid_segments_and_holds_unresolved(tmp_path: Path) -> None:
    _write_export(tmp_path, CENTERLINE_ROWS)

    result = run(root=tmp_path)
    assert result["status"] == "OK"
    assert result["rows"] == 2  # the two rows carrying a resolved Cell_ID
    assert result["held_unresolved"] == 1  # PR-22 row lacks a cell
    assert result["held_invalid"] == 0
    assert result["held_unknown_cell"] == 0

    rows = _read_output(tmp_path)
    assert rows and list(rows[0].keys()) == OUTPUT_COLUMNS

    for row in rows:
        assert validate_row(row, SCHEMA) == []
        assert row["source_id"] == "dtop_centerline_lrs"
        assert row["Cell_ID"]

    by_cell = {row["Cell_ID"]: row for row in rows}
    assert set(by_cell) == {"R10_C20", "R11_C21"}

    seg = by_cell["R10_C20"]
    # Deterministic segment_uid over route_id|km_start|km_end|direction.
    assert seg["segment_uid"] == _uid("seg_", "PR-52", "0", "10", "both")
    assert seg["length_km"] == "10"
    assert seg["crs"] == "EPSG:32161"
    assert seg["geometry_ref"] == "dtop_centerline_lrs:PR-52:0-10"
    assert seg["evidence_tier"] == "T2_operational_secondary"
    assert seg["confidence"] == "0.60"

    # PR-22 (no Cell_ID) was held, not emitted.
    assert all(row["route_id"] != "PR-22" for row in rows)


def test_defensive_column_mapping_and_defaults() -> None:
    # Alternate upstream column names + missing optionals exercise the fallbacks.
    seg = build_segment(
        {
            "ROUTE_ID": "PR-1",
            "from_km": "3",
            "to_km": "9",
            "CELL_ID": "R5_C5",
            "MUNICIPALITY": "Ponce",
        },
        "export.csv",
    )
    assert seg["route_id"] == "PR-1"
    assert seg["km_start"] == "3" and seg["km_end"] == "9"
    assert seg["length_km"] == "6"
    assert seg["Cell_ID"] == "R5_C5"
    assert seg["route_class"] == "unknown"
    assert seg["direction"] == "unknown"
    assert validate_row(seg, SCHEMA) == []


def test_no_export_is_empty_and_writes_header(tmp_path: Path) -> None:
    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0
    assert result["held_unresolved"] == 0

    # A header-only output is written even with no export, so the downstream
    # join builder reads zero segments rather than a stale file.
    out = tmp_path / "data" / "staging" / "processed" / "pr_roadwatch_segments.csv"
    assert out.read_text(encoding="utf-8").splitlines() == [",".join(OUTPUT_COLUMNS)]


def test_absent_export_clears_stale_output(tmp_path: Path) -> None:
    # A prior run emitted segments; the export is then removed.
    _write_export(tmp_path, CENTERLINE_ROWS)
    assert run(root=tmp_path)["rows"] == 2

    drop = tmp_path / "data" / "manual" / "dtop_centerline_lrs"
    for csv_file in drop.iterdir():
        csv_file.unlink()

    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    # Stale segments must not survive into the next run's output.
    assert _read_output(tmp_path) == []


def test_unknown_cell_is_held_not_emitted(tmp_path: Path) -> None:
    # A non-empty Cell_ID absent from the committed grid is an operator typo.
    row = {**CENTERLINE_ROWS[0], "Cell_ID": "R9999_C9999"}
    _write_export(tmp_path, [row])

    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0
    assert result["held_unknown_cell"] == 1
    assert _read_output(tmp_path) == []


def test_segment_uid_is_case_normalized() -> None:
    # Records differing only in capitalization must hash to the same segment_uid
    # (docs/ROADWATCH_CORRIDOR_MAPPING.md §4: strip + lowercase each component).
    upper = build_segment(
        {"route_id": "PR-52", "direction": "BOTH", "km_start": "0", "km_end": "10"},
        "export.csv",
    )
    lower = build_segment(
        {"route_id": " pr-52 ", "direction": "both", "km_start": "0", "km_end": "10"},
        "export.csv",
    )
    assert upper["segment_uid"] == lower["segment_uid"]


def test_all_unresolved_is_empty_with_header(tmp_path: Path) -> None:
    unresolved = [{**row, "Cell_ID": ""} for row in CENTERLINE_ROWS]
    _write_export(tmp_path, unresolved)

    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0
    assert result["held_unresolved"] == 3
    assert result["held_unknown_cell"] == 0

    out = tmp_path / "data" / "staging" / "processed" / "pr_roadwatch_segments.csv"
    assert out.read_text(encoding="utf-8").splitlines()[0].split(",") == OUTPUT_COLUMNS


def test_duplicate_segments_deduped(tmp_path: Path) -> None:
    dupes = [CENTERLINE_ROWS[0], dict(CENTERLINE_ROWS[0])]  # same uid twice
    _write_export(tmp_path, dupes)

    result = run(root=tmp_path)
    assert result["rows"] == 1
