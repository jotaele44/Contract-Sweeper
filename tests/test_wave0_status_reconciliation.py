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
    registry = status["source_registry_current"]
    assert registry["total_sources"] == readiness["total_sources"] == 151
    assert registry["source_ids_sha256"] == readiness["source_count_provenance"]["source_ids_sha256"]
    for key in (
        "total_sources", "automatable_total", "automatable_ready",
        "queued_excluded_total", "queued_excluded",
    ):
        assert status["materialization_readiness_truth"][key] == readiness[key]


def test_status_records_current_base_and_last_certified_head() -> None:
    status = _read("reports/current_status.json")
    assert status["schema_version"] == "moneysweep_current_status_v6"
    assert status["base_sha"] == "bd337fb092eb639cdb24b490bc90a8b07e9e51c4"
    certification = status["wave0_ci_certification"]["status_reconciliation_pr"]
    assert certification["last_certified_head_sha"] == "b1f088c98c8175298b856a5df8215c77fa933877"
    assert certification["triggered_workflows"] == 16
    assert certification["status"] == "GREEN"
    assert status["current_head_authority"].startswith("GitHub PR #448")


def test_coverage_uses_current_certified_operator_denominator() -> None:
    coverage = _read("reports/current_status.json")["materialization_coverage"]
    snapshot = coverage["local_operator_snapshot"]
    assert coverage["evidence_registry_total"] == 151
    assert coverage["current_registry_total"] == 151
    assert coverage["denominator_comparable"] is True
    assert coverage["probe_ran"] is False
    assert coverage["registry_digest_parity"] is True
    assert coverage["status_count_parity"] is True
    assert snapshot["fully_materialized"] == 67
    assert snapshot["partially_materialized"] == 11
    assert snapshot["not_materialized"] == 73
    assert snapshot["required_fully_materialized"] == 10
    assert snapshot["required_sources"] == 14
    assert snapshot["unadjudicated_orphan_rows"] == 0
    assert snapshot["unresolved_lineage_rows_within_derived_outputs"] == 104280


def test_gap_and_output_ownership_adjudication_is_honest() -> None:
    adjudication = _read("reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json")
    required = {row["source_id"]: row for row in adjudication["required_source_adjudication"]}
    assert set(required) == {"cor3", "hud_drgr_authorized", "pr_cabilderos", "prasa"}
    assert all(row["materialization_credit"] is False for row in required.values())
    assert required["hud_drgr_authorized"]["expected_outputs"] == [
        "data/staging/processed/hud_drgr_activities.csv",
        "data/staging/processed/hud_drgr_projects.csv",
    ]
    derived = {row["file"]: row for row in adjudication["derived_output_adjudication"]}
    assert sum(row["rows"] for row in derived.values()) == 212930
    assert all(row["source_materialization_credit"] is False for row in derived.values())
    assert derived["entity_master.csv"]["producer"] is None
    assert derived["entity_master.csv"]["producer_status"] == "UNRESOLVED_STAGING_LINEAGE"
    assert sum(row["producer_status"] == "CONFIRMED" for row in derived.values()) == 5


def test_adjudicated_row_buckets_have_exact_parity_without_double_counting() -> None:
    rows = _read("reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json")["row_accounting"]
    assert rows["registry_declared_rows"] == 849898
    assert rows["derived_output_rows"] == 212930
    assert rows["intermediate_rows"] == 120737
    assert rows["unadjudicated_orphan_rows"] == 0
    assert (
        rows["registry_declared_rows"] + rows["derived_output_rows"]
        + rows["intermediate_rows"] + rows["unadjudicated_orphan_rows"]
        == rows["total_rows_on_disk"] == 1183565
    )
    assert rows["parity"] is True
    assert rows["double_counting_detected"] is False


def test_status_preserves_historical_blob_reference() -> None:
    evidence = _read("reports/current_status.json")["historical_status_evidence"]
    assert evidence["path_at_base"] == "reports/current_status.json"
    assert evidence["blob_sha"] == "b175df73deb6ecf5bbf0d0040b89ca75f5d1e10c"


def test_normalized_roadmap_has_no_stale_orphan_claim() -> None:
    text = (ROOT / "docs/ROAD_TO_100_NORMALIZED.md").read_text(encoding="utf-8")
    assert "151" in text
    assert "104/104" in text
    assert "67/151" in text
    assert "10/14" in text
    assert "Unadjudicated orphan rows | 0" in text
    assert "unresolved lineage" in text.lower()
    assert "34ef3b9352493d0b6ba4eb821d7ea544bec0933b" not in text


def test_issue_reconciliation_records_closed_supersession() -> None:
    reconciliation = _read("reports/current_status.json")["issue_reconciliation"]
    assert reconciliation["issue_258"].startswith("CLOSED_COMPLETED")
    assert reconciliation["issue_87"].startswith("CLOSED_SUPERSEDED")
    assert reconciliation["status_reconciliation_pr"] == 448
    assert reconciliation["superseded_status_pr"] == 447
