"""Unit tests for the STIP/TIP projects producer (offline, fixture-based).

Exercises scripts/ingest_stip_tip_projects.py end to end against an operator
export CSV fixture — no network, no registry surface. Emitted rows are
infrastructure_projects-shaped (plus the join keys route_id/km); rows missing the
identity/join subset are held. Includes an interlock test that feeds the emitted
projects file to the merged corridor-join builder.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from moneysweep.validation.canonical_v1_schema import validate_row
from scripts.ingest_stip_tip_projects import (
    OUTPUT_COLUMNS,
    REQUIRED_FIELDS,
    build_project,
    run,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "infrastructure_projects.schema.json").read_text(encoding="utf-8")
)

# Operator STIP/TIP export: two complete rows + one missing route_id (held).
PROJECT_ROWS = [
    {
        "project_id": "STIP-1",
        "project_name": "PR-52 resurfacing",
        "route_id": "PR-52",
        "km_start": "2",
        "km_end": "8",
        "municipality": "Caguas",
        "funding_program": "STBG",
        "amount": "1000000",
    },
    {
        "project_id": "STIP-2",
        "project_name": "PR-22 safety",
        "route_id": "PR-22",
        "km_start": "",
        "km_end": "",
        "municipality": "Bayamon",
        "funding_program": "HSIP",
        "amount": "250000",
    },
    # No route_id -> held_invalid (the join drops route-less projects anyway).
    {
        "project_id": "STIP-X",
        "project_name": "orphan",
        "route_id": "",
        "municipality": "Ponce",
        "funding_program": "NHPP",
        "amount": "500000",
    },
]

PROJECT_COLUMNS = [
    "project_id",
    "project_name",
    "route_id",
    "km_start",
    "km_end",
    "municipality",
    "funding_program",
    "amount",
]


def _write_export(root: Path, rows: list[dict[str, str]], name: str = "export.csv") -> None:
    drop = root / "data" / "manual" / "stip_tip_projects"
    drop.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(col for row in rows for col in row))
    with (drop / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _read_output(root: Path) -> list[dict[str, str]]:
    out = root / "data" / "staging" / "processed" / "pr_stip_tip_projects.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_emits_projects_and_holds_routeless(tmp_path: Path) -> None:
    _write_export(tmp_path, PROJECT_ROWS)

    result = run(root=tmp_path)
    assert result["status"] == "OK"
    assert result["rows"] == 2  # STIP-1 (km) + STIP-2 (route-only)
    assert result["held_invalid"] == 1  # STIP-X has no route_id

    rows = _read_output(tmp_path)
    assert rows and list(rows[0].keys()) == OUTPUT_COLUMNS

    by_id = {row["project_id"]: row for row in rows}
    assert set(by_id) == {"STIP-1", "STIP-2"}

    for row in rows:
        assert row["source_id"] == "stip_tip_projects"
        for field in REQUIRED_FIELDS:
            assert row[field], f"{field} must be non-empty on emitted rows"

    km = by_id["STIP-1"]
    assert (km["km_start"], km["km_end"]) == ("2", "8")
    assert km["asset_type"] == "roadway"
    assert km["owner_agency"] == "DTOP"
    assert km["status"] == "programmed"

    route_only = by_id["STIP-2"]
    assert (route_only["km_start"], route_only["km_end"]) == ("", "")

    assert "STIP-X" not in by_id


def test_interlock_with_corridor_join(tmp_path: Path) -> None:
    # The producer's output must satisfy the real join contract end to end.
    _write_export(tmp_path, PROJECT_ROWS)
    assert run(root=tmp_path)["rows"] == 2

    from scripts.build_roadwatch_corridor_join import run as join_run

    processed = tmp_path / "data" / "staging" / "processed"
    segments = [
        {
            "segment_uid": "seg_a",
            "route_id": "PR-52",
            "km_start": "0",
            "km_end": "10",
            "municipality": "Caguas",
            "Cell_ID": "R10_C20",
        }
    ]
    with (processed / "pr_roadwatch_segments.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(segments[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(segments)

    join_schema = json.loads(
        (ROOT / "schemas" / "roadwatch_corridor_join.schema.json").read_text(encoding="utf-8")
    )
    result = join_run(root=tmp_path)
    assert result["status"] == "OK"

    out = processed / "roadwatch_corridor_join_candidates.csv"
    with out.open(newline="", encoding="utf-8") as fh:
        candidates = list(csv.DictReader(fh))
    assert candidates
    by_project = {c["project_id"]: c for c in candidates}
    km = by_project["STIP-1"]
    assert km["join_method"] == "route_km_measure"
    assert km["Cell_ID"] == "R10_C20"
    assert validate_row(km, join_schema) == []


def test_defensive_mapping_and_project_id_fallback() -> None:
    # Alternate upstream column names; no project_id -> deterministic fallback.
    seg = build_project(
        {
            "ROUTE_ID": "PR-1",
            "PROJECT_NAME": "widening",
            "MUNICIPALITY": "Ponce",
            "FUNDING_PROGRAM": "NHPP",
            "AMOUNT": "42",
        },
        "export.csv",
    )
    assert seg["route_id"] == "PR-1"
    assert seg["project_id"].startswith("stip_")  # synthesized, stable
    assert seg["municipality"] == "Ponce"
    assert seg["funding_program"] == "NHPP"
    # The synthesized id is case/space-normalized: differing capitalization and
    # surrounding whitespace collapse to the same id (dedup robustness).
    again = build_project(
        {
            "route_id": " pr-1 ",
            "project_name": "Widening",
            "municipality": "Ponce",
            "funding_program": "NHPP",
            "amount": "42",
        },
        "export.csv",
    )
    assert seg["project_id"] == again["project_id"]


def test_invalid_km_range_becomes_route_only(tmp_path: Path) -> None:
    # Reversed km range must collapse to blanks (route-only), not a malformed pair.
    row = {**PROJECT_ROWS[0], "km_start": "15", "km_end": "5"}
    _write_export(tmp_path, [row])

    run(root=tmp_path)
    emitted = _read_output(tmp_path)
    assert len(emitted) == 1
    assert (emitted[0]["km_start"], emitted[0]["km_end"]) == ("", "")


def test_blank_point_geometry_is_preserved_not_fabricated(tmp_path: Path) -> None:
    _write_export(tmp_path, [PROJECT_ROWS[0]])
    run(root=tmp_path)
    row = _read_output(tmp_path)[0]
    # Route-corridor projects carry no point coordinates/dates — left blank.
    assert row["latitude"] == "" and row["longitude"] == ""
    assert row["start_date"] == "" and row["completion_date"] == ""


def test_no_export_is_empty_and_writes_header(tmp_path: Path) -> None:
    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0

    out = tmp_path / "data" / "staging" / "processed" / "pr_stip_tip_projects.csv"
    assert out.read_text(encoding="utf-8").splitlines() == [",".join(OUTPUT_COLUMNS)]


def test_absent_export_clears_stale_output(tmp_path: Path) -> None:
    _write_export(tmp_path, PROJECT_ROWS)
    assert run(root=tmp_path)["rows"] == 2

    drop = tmp_path / "data" / "manual" / "stip_tip_projects"
    for csv_file in drop.iterdir():
        csv_file.unlink()

    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert _read_output(tmp_path) == []


def test_duplicate_project_id_deduped(tmp_path: Path) -> None:
    _write_export(tmp_path, [PROJECT_ROWS[0], dict(PROJECT_ROWS[0])])
    result = run(root=tmp_path)
    assert result["rows"] == 1
