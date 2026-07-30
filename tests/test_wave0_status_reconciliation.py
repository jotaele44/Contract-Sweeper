from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

# This file mirrors long immutable status identifiers and generated-schema keys.
# Keep its assertion layout stable while Ruff linting and pytest remain active.
# fmt: off


def _read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_current_status_matches_authoritative_readiness() -> None:
    status = _read("reports/current_status.json")
    readiness = _read("reports/materialization_readiness.json")
    registry = status["source_registry_current"]
    assert registry["total_sources"] == readiness["total_sources"] == 151
    assert (
        registry["source_ids_sha256"]
        == readiness["source_count_provenance"]["source_ids_sha256"]
    )
    for key in (
        "total_sources",
        "automatable_total",
        "automatable_ready",
        "queued_excluded_total",
        "queued_excluded",
    ):
        assert status["materialization_readiness_truth"][key] == readiness[key]


def test_status_records_pr448_postmerge_state() -> None:
    status = _read("reports/current_status.json")
    assert status["schema_version"] == "moneysweep_current_status_v7"
    assert status["main_sha"] == "9e911203a05cf8f2e99c762161b7ec18de8cef73"
    assert status["premerge_base_sha"] == (
        "bd337fb092eb639cdb24b490bc90a8b07e9e51c4"
    )
    assert status["certified_input_head_sha"] == (
        "ab576462ded2f2ca590002011861322c9ece2a32"
    )

    merge = status["merge_record"]
    assert merge["pr_number"] == 448
    assert merge["state"] == "MERGED"
    assert merge["draft"] is False
    assert merge["merge_authorized"] is True
    assert merge["merge_completed"] is True
    assert merge["merge_method"] == "squash"
    assert merge["premerge_workflows"] == 17
    assert merge["premerge_workflows_successful"] == 17
    assert merge["main_identical_to_merge_commit"] is True

    certification = status["wave0_ci_certification"]["status_reconciliation_pr"]
    assert certification["state"] == "MERGED"
    assert certification["triggered_workflows"] == 17
    assert certification["successful_workflows"] == 17
    assert certification["status"] == "GREEN"
    assert certification["postmerge_main_identity_verified"] is True


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
    assert required["hud_drgr_authorized"]["expected_outputs"] == [
        "data/staging/processed/hud_drgr_activities.csv",
        "data/staging/processed/hud_drgr_projects.csv",
    ]
    derived = {
        row["file"]: row
        for row in adjudication["derived_output_adjudication"]
    }
    assert sum(row["rows"] for row in derived.values()) == 212930
    assert all(
        row["source_materialization_credit"] is False
        for row in derived.values()
    )
    assert derived["entity_master.csv"]["producer"] is None
    assert (
        derived["entity_master.csv"]["producer_status"]
        == "UNRESOLVED_STAGING_LINEAGE"
    )
    assert sum(row["producer_status"] == "CONFIRMED" for row in derived.values()) == 5


def test_adjudicated_row_buckets_have_exact_parity_without_double_counting() -> None:
    rows = _read("reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json")[
        "row_accounting"
    ]
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
    evidence = _read("reports/current_status.json")["historical_status_evidence"]
    assert evidence["path_at_base"] == "reports/current_status.json"
    assert evidence["blob_sha"] == "b175df73deb6ecf5bbf0d0040b89ca75f5d1e10c"


def test_roadmaps_record_completed_merge_without_opening_production() -> None:
    detailed = (ROOT / "docs/ROAD_TO_100.md").read_text(encoding="utf-8")
    normalized = (ROOT / "docs/ROAD_TO_100_NORMALIZED.md").read_text(
        encoding="utf-8"
    )
    for text in (detailed, normalized):
        assert "#448" in text
        assert "9e911203a05cf8f2e99c762161b7ec18de8cef73" in text
        assert "17/17" in text
        assert "NON_PRODUCTION_DIAGNOSTIC" in text
        assert "draft and unmerged" not in text
        assert "Unadjudicated orphan rows | 0" in text


def test_postmerge_preservation_flags_are_explicit() -> None:
    preservation = _read("reports/current_status.json")["preservation"]
    assert preservation["pr_448_draft"] is False
    assert preservation["pr_448_merge_authorized"] is True
    assert preservation["pr_448_merge_completed"] is True
    assert preservation["auto_merge_used"] is False
    assert preservation["direct_main_write_authorized"] is False
    assert preservation["live_fetch_authorized"] is False
    assert preservation["credential_automation_authorized"] is False
    assert preservation["data_promotion_authorized"] is False
    assert preservation["production_activation_authorized"] is False
    assert preservation["force_push_authorized"] is False
    assert preservation["history_rewrite_authorized"] is False


# fmt: on
