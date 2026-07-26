"""Unit tests for the FHWA HPMS routes producer (offline, mocked HTTP).

Exercises scripts/ingest_fhwa_hpms_routes.py without network: the ArcGIS
resultOffset/exceededTransferLimit pagination, PR filtering, the DTOP-style
Cell_ID hold, and the no-network => EMPTY path. Mirrors
tests/test_census_and_ntd_producers.py.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from moneysweep.validation.canonical_v1_schema import validate_row
from scripts import ingest_fhwa_hpms_routes as hpms

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "roadwatch_segment.schema.json").read_text(encoding="utf-8")
)


def _resp(payload: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    r.raise_for_status = MagicMock()
    return r


def _attrs(**kwargs: object) -> dict:
    return {"attributes": kwargs}


def _read_output(root: Path) -> list[dict[str, str]]:
    out = root / "data" / "staging" / "processed" / "pr_hpms_routes.csv"
    with out.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_paginates_filters_and_holds_uncelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page1 = {
        "features": [
            _attrs(
                state_code=72,
                route_id="PR-52",
                begin_point=0,
                end_point=10,
                county_name="Caguas",
                objectid=101,
                Cell_ID="R10_C20",
            ),
            _attrs(
                state_code=72,
                route_id="PR-22",
                begin_point=0,
                end_point=5,
                county_name="Bayamon",
                objectid=102,
            ),  # no Cell_ID -> held
        ],
        "exceededTransferLimit": True,
    }
    page2 = {
        "features": [
            _attrs(
                state_code=48,
                route_id="US-1",
                begin_point=0,
                end_point=3,
                county_name="Travis",
                objectid=999,
                Cell_ID="R1_C1",
            ),  # non-PR -> dropped
        ],
        "exceededTransferLimit": False,
    }
    session = MagicMock()
    session.get.side_effect = [_resp(page1), _resp(page2)]
    monkeypatch.setattr(hpms, "_session", lambda: session)
    monkeypatch.setattr(hpms, "_sleep", lambda *_a: None)

    result = hpms.run(root=tmp_path)
    assert session.get.call_count == 2  # both pages consumed
    assert result["status"] == "OK"
    assert result["rows"] == 1  # PR-52 (celled) emitted
    assert result["held_unresolved"] == 1  # PR-22 has no Cell_ID

    rows = _read_output(tmp_path)
    assert rows and list(rows[0].keys()) == hpms.OUTPUT_COLUMNS
    seg = rows[0]
    assert seg["route_id"] == "PR-52"
    assert seg["Cell_ID"] == "R10_C20"
    assert seg["source_id"] == "fhwa_hpms_routes"
    assert validate_row(seg, SCHEMA) == []


def test_normalize_drops_non_pr_and_maps_fields() -> None:
    rows = hpms.normalize(
        [
            {"state_code": "72", "route_id": "PR-1", "begin_point": "0", "end_point": "4"},
            {"state_code": "06", "route_id": "CA-1", "begin_point": "0", "end_point": "4"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["route_id"] == "PR-1"


def test_no_network_is_empty_with_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("no network")
    monkeypatch.setattr(hpms, "_session", lambda: session)
    monkeypatch.setattr(hpms, "_sleep", lambda *_a: None)

    result = hpms.run(root=tmp_path)
    assert result["status"] == "EMPTY"
    assert result["rows"] == 0

    out = tmp_path / "data" / "staging" / "processed" / "pr_hpms_routes.csv"
    assert out.read_text(encoding="utf-8").splitlines() == [",".join(hpms.OUTPUT_COLUMNS)]
