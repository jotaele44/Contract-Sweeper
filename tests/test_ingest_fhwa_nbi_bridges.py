"""Unit tests for the FHWA NBI bridges producer (offline, mocked HTTP).

Exercises scripts/ingest_fhwa_nbi_bridges.py without network: the delimited parse,
PR filtering (state code 72), the point->zero-length-segment encoding, the
DTOP-style Cell_ID hold, and the no-network => EMPTY path.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from moneysweep.validation.canonical_v1_schema import validate_row
from scripts import ingest_fhwa_nbi_bridges as nbi

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "roadwatch_segment.schema.json").read_text(encoding="utf-8")
)

NBI_BODY = (
    "STATE_CODE_001,ROUTE_NUMBER_005D,KILOPOINT_011,STRUCTURE_NUMBER_008,"
    "COUNTY_CODE_003,LAT_016,LONG_017,Cell_ID\n"
    "72,PR-52,5.2,BR-001,Caguas,18.20,-66.00,R10_C20\n"  # PR + celled -> emitted
    "72,PR-22,3.1,BR-002,Bayamon,18.40,-66.10,\n"  # PR, no cell -> held
    "48,US-1,1.0,BR-999,Travis,30.20,-97.70,R1_C1\n"  # non-PR -> dropped
)


def _resp_text(body: str) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = body
    r.raise_for_status = MagicMock()
    return r


def _read_output(root: Path) -> list[dict[str, str]]:
    out = root / "data" / "staging" / "processed" / "pr_nbi_bridges.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_parses_filters_and_encodes_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get.return_value = _resp_text(NBI_BODY)
    monkeypatch.setattr(nbi, "_session", lambda: session)

    result = nbi.run(root=tmp_path)
    assert result["status"] == "OK"
    assert result["rows"] == 1  # PR-52 structure (celled)
    assert result["held_unresolved"] == 1  # PR-22 has no Cell_ID

    rows = _read_output(tmp_path)
    assert rows and list(rows[0].keys()) == nbi.OUTPUT_COLUMNS
    seg = rows[0]
    assert seg["route_id"] == "PR-52"
    assert seg["Cell_ID"] == "R10_C20"
    # Point structure -> zero-length segment.
    assert seg["km_start"] == seg["km_end"] == "5.2"
    assert seg["length_km"] == "0"
    assert seg["geometry_ref"] == "BR-001"
    # Lat/long carried as extra columns for the future nbi_structure_point snap.
    assert seg["latitude"] == "18.20" and seg["longitude"] == "-66.00"
    assert validate_row(seg, SCHEMA) == []


def test_normalize_drops_non_pr() -> None:
    rows = nbi.normalize(
        [
            {"STATE_CODE_001": "72", "ROUTE_NUMBER_005D": "PR-9", "KILOPOINT_011": "1.0"},
            {"STATE_CODE_001": "36", "ROUTE_NUMBER_005D": "NY-9", "KILOPOINT_011": "1.0"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["route_id"] == "PR-9"


def test_no_network_is_empty_with_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("no network")
    monkeypatch.setattr(nbi, "_session", lambda: session)

    result = nbi.run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0

    out = tmp_path / "data" / "staging" / "processed" / "pr_nbi_bridges.csv"
    assert out.read_text(encoding="utf-8").splitlines() == [",".join(nbi.OUTPUT_COLUMNS)]
