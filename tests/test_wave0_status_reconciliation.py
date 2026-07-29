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


def test_coverage_uses_current_certified_operator_denominator() -> None:
    status = _read("reports/current_status.json")
    coverage = status["materialization_coverage"]
    snapshot = coverage["local_operator_snapshot"]

    assert coverage["evidence_registry_total"] == coverage["current_registry_total"] == 151
    assert coverage["denominator_comparable"] is True
    assert coverage["regeneration_status"] == "CERTIFIED_OPERATOR_CORPUS"
    assert coverage["probe_ran"] is False
    assert coverage["registry_digest_parity"] is True
    assert coverage["status_count_parity"] is True
    assert snapshot["fully_materialized"] == 67
    assert snapshot["partially_materialized"] == 11
    assert snapshot["not_materialized"] == 73
    assert (
        snapshot["fully_materialized"]
        + snapshot["partially_materialized"]
        + snapshot["not_materialized"]
        == 151
    )
    assert snapshot["required_fully_materialized"] == 10
    assert snapshot["required_sources"] == 14


def test_status_preserves_historical_blob_reference() -> None:
    status = _read("reports/current_status.json")
    evidence = status["historical_status_evidence"]
    assert evidence["path_at_base"] == "reports/current_status.json"
    assert evidence["blob_sha"] == "b175df73deb6ecf5bbf0d0040b89ca75f5d1e10c"
    assert len(evidence["blob_sha"]) == 40


def test_normalized_roadmap_uses_current_denominator() -> None:
    text = (ROOT / "docs/ROAD_TO_100_NORMALIZED.md").read_text(encoding="utf-8")
    assert "151" in text
    assert "104/104" in text
    assert "67/151" in text
    assert "10/14" in text
    assert "#448" in text
    assert "NON_PRODUCTION_DIAGNOSTIC" in text


def test_issue_reconciliation_records_closed_supersession() -> None:
    status = _read("reports/current_status.json")
    assert status["issue_reconciliation"]["issue_258"].startswith("CLOSED_COMPLETED")
    assert status["issue_reconciliation"]["issue_87"].startswith("CLOSED_SUPERSEDED")
    assert status["issue_reconciliation"]["status_reconciliation_pr"] == 448
    assert status["issue_reconciliation"]["superseded_status_pr"] == 447
