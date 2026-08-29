from pathlib import Path

import pytest

from tools.certify_production import build_report

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCOPE_SHA = "ba0c0d11a011669a5d487dc116274491449d4b72"


def _gates(report: dict) -> dict[str, dict]:
    return {gate["id"]: gate for gate in report["gates"]}


def test_current_main_audit_is_fail_closed_and_denominator_exact() -> None:
    report = build_report(
        root=ROOT,
        scope_sha=SCOPE_SHA,
        run_preflight=False,
        generated_at="2026-08-28T22:30:00-04:00",
    )
    gates = _gates(report)

    assert report["scope"]["commit_sha"] == SCOPE_SHA
    assert report["scope"]["registry_total_sources"] == 162
    assert report["scope"]["registry_required_sources"] == 16
    assert report["scope"]["registry_source_ids_sha256"] == (
        "353995f4595fde0f7643ff8d9987154bcd230abe30037cdcbe6e3abd7f4233d1"
    )
    assert len(report["source_universe"]["source_ledger"]) == 162
    assert report["certification_state"] == "NON_PRODUCTION_DIAGNOSTIC"
    assert report["production_eligible"] is False

    assert gates["G0_SCOPE_FREEZE"]["state"] == "PASS"
    assert gates["G1_CONTROL_PLANE_RECONCILIATION"]["state"] == "PASS"
    assert gates["G2_STRICT_PREFLIGHT"]["state"] == "OPEN"
    assert gates["G3_REQUIRED_SOURCE_MATERIALIZATION"]["state"] == "FAIL"
    assert gates["G4_FULL_SOURCE_CLASSIFICATION"]["state"] == "PASS"
    assert gates["G5_AUTOMATABLE_EXECUTION"]["state"] == "FAIL"
    assert gates["G6_SOURCE_VALIDATION_AND_COVERAGE_CONTRACTS"]["state"] == "FAIL"
    assert gates["G7_ENTITY_RESOLUTION"]["state"] == "FAIL"
    assert gates["G8_PROVENANCE_AND_LINEAGE"]["state"] == "BLOCKED"
    assert gates["G9_CANONICAL_MASTER_INVARIANTS"]["state"] == "BLOCKED"
    assert gates["G10_FRESHNESS_AND_UNIVERSE_COMPLETENESS"]["state"] == "FAIL"
    assert gates["G11_PRODUCTION_EXPORT_AND_FEDERATION"]["state"] == "BLOCKED"
    assert gates["G12_RELEASE_CERTIFICATION"]["state"] == "BLOCKED"


def test_required_source_residue_is_exact_for_current_registry() -> None:
    report = build_report(root=ROOT, scope_sha=SCOPE_SHA, run_preflight=False)
    gate = _gates(report)["G3_REQUIRED_SOURCE_MATERIALIZATION"]

    assert gate["evidence"]["required_status_counts"] == {
        "fully_materialized": 8,
        "not_materialized": 7,
        "partially_materialized": 1,
    }
    assert {row["source_id"] for row in gate["evidence"]["required_blockers"]} == {
        "usaspending_prime",
        "cor3",
        "hud_drgr_authorized",
        "prasa",
        "oficina_contralor",
        "pr_cabilderos",
        "campaign_finance_entities",
        "campaign_finance_materialization_gate",
    }


def test_current_completeness_and_entity_residue_are_not_promoted() -> None:
    report = build_report(root=ROOT, scope_sha=SCOPE_SHA, run_preflight=False)
    gates = _gates(report)

    completeness = report["source_universe"]["completeness_matrix"]
    assert completeness["total_sources"] == 162
    assert completeness["by_materialization_status"] == {
        "fully_materialized": 11,
        "not_materialized": 149,
        "partially_materialized": 2,
    }
    assert completeness["contracted_sources"] == 23
    assert completeness["by_coverage_status"] == {
        "below_contract": 4,
        "meets_contract": 2,
        "uncontracted": 139,
        "unverifiable": 17,
    }

    assert gates["G7_ENTITY_RESOLUTION"]["evidence"]["open_review_count"] == 24
    assert gates["G8_PROVENANCE_AND_LINEAGE"]["evidence"]["coverage_audit_total_sources"] == 144
    assert gates["G8_PROVENANCE_AND_LINEAGE"]["evidence"]["current_registry_total_sources"] == 162
    assert gates["G9_CANONICAL_MASTER_INVARIANTS"]["evidence"]["canonical_graph_gate"] == (
        "NON_PRODUCTION_DIAGNOSTIC"
    )
    assert gates["G11_PRODUCTION_EXPORT_AND_FEDERATION"]["evidence"]["production_status"] == (
        "NON_PRODUCTION_DIAGNOSTIC"
    )
