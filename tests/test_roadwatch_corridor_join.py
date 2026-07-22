"""Unit tests for the RoadWatch corridor-join builder (offline, fixture-based).

Exercises scripts/build_roadwatch_corridor_join.py end to end against staged CSV
fixtures — no network, no registry surface. Every emitted row must validate
against schemas/roadwatch_corridor_join.schema.json and start `pending`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from moneysweep.validation.canonical_v1_schema import validate_row
from scripts.build_roadwatch_corridor_join import OUTPUT_COLUMNS, run

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "roadwatch_corridor_join.schema.json").read_text(encoding="utf-8")
)

SEGMENTS = [
    # route PR-52, two consecutive km-stationed segments
    {
        "segment_uid": "seg_a",
        "route_id": "PR-52",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "0",
        "km_end": "10",
        "length_km": "10",
        "municipality": "Caguas",
        "Cell_ID": "PRC-0001",
        "crs": "EPSG:32161",
    },
    {
        "segment_uid": "seg_b",
        "route_id": "PR-52",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "10",
        "km_end": "20",
        "length_km": "10",
        "municipality": "Caguas",
        "Cell_ID": "PRC-0002",
        "crs": "EPSG:32161",
    },
    # route PR-22, single segment
    {
        "segment_uid": "seg_c",
        "route_id": "PR-22",
        "route_class": "pr_primary",
        "direction": "both",
        "km_start": "0",
        "km_end": "5",
        "length_km": "5",
        "municipality": "Bayamon",
        "Cell_ID": "PRC-0010",
        "crs": "EPSG:32161",
    },
]

PROJECTS = [
    # km 2-8 overlaps seg_a by 6/10 = 60% (kept); no overlap with seg_b (dropped)
    {
        "project_id": "STIP-1",
        "project_name": "PR-52 resurfacing",
        "route_id": "PR-52",
        "km_start": "2",
        "km_end": "8",
        "funding_program": "STBG",
        "amount": "1000000",
    },
    # route only, no km -> route_only_promoted onto seg_c
    {
        "project_id": "STIP-2",
        "project_name": "PR-22 safety",
        "route_id": "PR-22",
        "km_start": "",
        "km_end": "",
        "funding_program": "HSIP",
        "amount": "250000",
    },
    # route with no segment -> no candidate
    {
        "project_id": "STIP-3",
        "project_name": "PR-99 ghost",
        "route_id": "PR-99",
        "km_start": "1",
        "km_end": "2",
        "funding_program": "NHPP",
        "amount": "500000",
    },
]


def _write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _stage(root: Path, segments: list[dict], projects: list[dict]) -> None:
    processed = root / "data" / "staging" / "processed"
    _write_csv(processed / "pr_roadwatch_segments.csv", segments, list(segments[0].keys()))
    _write_csv(
        processed / "pr_stip_tip_projects.csv",
        projects,
        [
            "project_id",
            "project_name",
            "route_id",
            "km_start",
            "km_end",
            "funding_program",
            "amount",
        ],
    )


def _read_output(root: Path) -> list[dict[str, str]]:
    out = root / "data" / "staging" / "processed" / "roadwatch_corridor_join_candidates.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_join_emits_valid_pending_candidates(tmp_path: Path) -> None:
    _stage(tmp_path, SEGMENTS, PROJECTS)

    result = run(root=tmp_path)
    assert result["status"] == "OK"
    assert result["rows"] == 2  # STIP-1->seg_a (km overlap), STIP-2->seg_c (route only)

    rows = _read_output(tmp_path)
    assert rows and list(rows[0].keys()) == OUTPUT_COLUMNS

    # Every row schema-valid, pending, with a non-empty Cell_ID.
    for row in rows:
        assert validate_row(row, SCHEMA) == []
        assert row["review_status"] == "pending"
        assert row["Cell_ID"]
        assert row["source_id"] == "roadwatch_corridor_join"

    by_project = {row["project_id"]: row for row in rows}

    km = by_project["STIP-1"]
    assert km["segment_uid"] == "seg_a"
    assert km["join_method"] == "route_km_measure"
    assert km["geo_reason_code"] == "roadwatch_route_km_overlap"
    assert km["overlap_pct"] == "60.0"
    assert km["confidence"] == "0.70"
    assert km["Cell_ID"] == "PRC-0001"

    route_only = by_project["STIP-2"]
    assert route_only["segment_uid"] == "seg_c"
    assert route_only["join_method"] == "route_only_promoted"
    assert route_only["geo_reason_code"] == "roadwatch_route_only_no_km"
    assert route_only["km_start"] == "" and route_only["km_end"] == ""

    # STIP-3 (route PR-99, no segment) produced nothing.
    assert "STIP-3" not in by_project


def test_below_overlap_threshold_is_dropped(tmp_path: Path) -> None:
    # 1 km project on a 10 km segment -> 10% overlap, below the 20% keep gate.
    projects = [
        {
            "project_id": "STIP-9",
            "project_name": "tiny",
            "route_id": "PR-52",
            "km_start": "0",
            "km_end": "1",
            "funding_program": "STBG",
            "amount": "1",
        }
    ]
    _stage(tmp_path, SEGMENTS, projects)
    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0


def test_invalid_km_range_is_skipped_not_route_only(tmp_path: Path) -> None:
    # Reversed km range (15 -> 5) is malformed, not a genuine route-only project;
    # it must be skipped, never promoted route-wide with blanked measures.
    projects = [
        {
            "project_id": "STIP-R",
            "project_name": "reversed extent",
            "route_id": "PR-52",
            "km_start": "15",
            "km_end": "5",
            "funding_program": "STBG",
            "amount": "1",
        }
    ]
    _stage(tmp_path, SEGMENTS, projects)
    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0


def test_no_matching_routes_is_empty_with_header(tmp_path: Path) -> None:
    projects = [
        {
            "project_id": "X",
            "project_name": "n",
            "route_id": "PR-99",
            "km_start": "1",
            "km_end": "2",
            "funding_program": "NHPP",
            "amount": "9",
        }
    ]
    _stage(tmp_path, SEGMENTS, projects)
    result = run(root=tmp_path)
    assert result["status"] == "EMPTY"
    # header still written even with zero rows
    out = tmp_path / "data" / "staging" / "processed" / "roadwatch_corridor_join_candidates.csv"
    assert out.read_text(encoding="utf-8").splitlines()[0].split(",") == OUTPUT_COLUMNS
