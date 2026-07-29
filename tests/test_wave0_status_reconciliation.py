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

    assert (
        status["source_registry_current"]["total_sources"]
        == readiness["total_sources"]
    )
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

    assert (
        coverage["evidence_registry_total"]
        == coverage["current_registry_total"]
        == 151
    )
    assert coverage["denominator_comparable"] is True
    assert (
        coverage["regeneration_status"]
        == "CERTIFIED_OPERATOR_CORPUS_WITH_OWNERSHIP_ADJUDICATION"
    )
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


def test_gap_and_output_ownership_adjudication_is_complete() -> None:
    adjudication = _read("reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json")

    required = {
        row["source_id"]: row
        for row in adjudication["required_source_adjudication"]
    }
    assert set(required) == {
        "cor3",
        "hud_drgr_authorized",
        "pr_cabilderos",
        "prasa",
    }
    assert all(row["materialization_credit"] is False for row in required.values())
    assert all(row["freshness_certified"] is False for row in required.values())

    derived = {
        row["file"]: row for row in adjudication["derived_output_adjudication"]
    }
    assert set(derived) == {
        "entity_master.csv",
        "pr_entity_profiles.csv",
        "high_value_unresolved.csv",
        "pr_report_builder_master.csv",
        "pr_entity_gaps.csv",
        "sam_entities.csv",
    }
    assert all(row["classification"] == "DERIVED_OUTPUT" for row in derived.values())
    assert all(
        row["source_materialization_credit"] is False for row in derived.values()
    )
    assert sum(row["rows"] for row in derived.values()) == 212930


def test_adjudicated_row_buckets_have_exact_parity_and_no_double_counting() -> None:
    adjudication = _read("reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json")
    rows = adjudication["row_accounting"]

    assert rows["registry_declared_rows"] == 849898
    assert rows["derived_output_rows"] == 212930
    assert rows["intermediate_rows"] == 120737
    assert rows["unadjudicated_orphan_rows"] == 0
    assert (
        rows["registry_declared_rows"]
        + rows["derived_output_rows"]
        + rows["intermediate_rows"]
        + rows["unadjudicated_orphan_rows"]
        == rows["total_rows_on_disk"]
        == 1183565
    )
    assert rows["parity"] is True
    assert rows["double_counting_detected"] is False


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
