from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_current_status_matches_authoritative_readiness() -> None:
    status = _read("reports/current_status.json")
    readiness = _read("reports/materialization_readiness.json")

    assert status["source_registry_current"]["total_sources"] == readiness["total_sources"]
    assert (
        status["source_registry_current"]["source_ids_sha256"]
        == readiness["source_count_provenance"]["source_ids_sha256"]
    )

    expected_keys = (
        "total_sources",
        "automatable_total",
        "automatable_ready",
        "queued_excluded_total",
        "queued_excluded",
    )
    truth = status["materialization_readiness_truth"]
    for key in expected_keys:
        assert truth[key] == readiness[key]


def test_coverage_is_not_overstated_when_denominator_drifted() -> None:
    status = _read("reports/current_status.json")
    coverage = status["materialization_coverage"]

    assert coverage["evidence_registry_total"] != coverage["current_registry_total"]
    assert coverage["denominator_comparable"] is False
    assert coverage["regeneration_status"] == "FORMAL_NONCERTIFICATION"


def test_status_preserves_historical_snapshot() -> None:
    status = _read("reports/current_status.json")
    snapshot = ROOT / status["historical_status_snapshot"]
    assert snapshot.is_file()


def test_normalized_roadmap_uses_current_denominator() -> None:
    text = (ROOT / "docs/ROAD_TO_100_NORMALIZED.md").read_text(encoding="utf-8")
    assert "151" in text
    assert "104/104" in text
    assert "Not certified" in text
    assert "NON_PRODUCTION_DIAGNOSTIC" in text
