"""Denominator and acceptance-topology tests for federal financial ontology v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "reference" / "federal_financial_program_denominator_20260810.json"
REGISTRY = ROOT / "registries" / "federal_financial_ontology_v1.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_sam_program_denominator_is_frozen_and_unique():
    snap = _json(SNAPSHOT)
    d = snap["denominator"]
    assert snap["source"]["sha256"] == "2daa2ac413acd04ade6d26d9a127e7519bdd721a803984ccf90c44ade19476a3"
    assert d["assistance_listing_rows"] == 2864
    assert d["unique_program_numbers"] == 2864
    assert d["duplicate_program_numbers"] == 0


def test_financial_denominator_partitions_complete_assistance_denominator():
    d = _json(SNAPSHOT)["denominator"]
    assert d["financial_program_rows"] == 2811
    assert d["nonfinancial_assistance_rows"] == 53
    assert d["financial_program_rows"] + d["nonfinancial_assistance_rows"] == d["assistance_listing_rows"]


def test_pr_nexus_baseline_is_100_percent_classified_but_not_promoted():
    snap = _json(SNAPSHOT)
    d = snap["denominator"]
    counts = snap["initial_pr_nexus_policy"]["initial_state_counts"]
    assert sum(counts.values()) == d["financial_program_rows"]
    assert counts["requires_award_level_test"] == 2811
    assert counts["confirmed_pr_activity"] == 0
    assert snap["initial_pr_nexus_policy"]["eligibility_alone_never_promotes_confirmed_activity"] is True
    assert snap["certification"]["global_fain_backfill_allowed"] is False


def test_nonfinancial_exclusion_inventory_is_lossless():
    snap = _json(SNAPSHOT)
    excluded = snap["nonfinancial_assistance_rows_by_type"]
    assert sum(excluded.values()) == snap["denominator"]["nonfinancial_assistance_rows"] == 53


def test_eight_acceptance_topologies_are_declared_without_special_case_target():
    r = _json(REGISTRY)
    expected = {
        "doe_40101d_formula_grant",
        "fema_financial_assistance",
        "hud_block_grant",
        "sba_direct_loan",
        "loan_guarantee",
        "direct_payment",
        "insurance_or_indemnity",
        "federal_procurement",
    }
    assert set(r["acceptance_topologies"]) == expected
    assert r["certification_targets"]["special_case_schema_mutations"] == 0


def test_fain_backfill_is_blocked_until_program_population_gate_closes():
    r = _json(REGISTRY)
    snap = _json(SNAPSHOT)
    assert r["bridge_to_existing_contract"]["global_fain_backfill_gate"] == "blocked_until_ontology_certified"
    assert snap["certification"]["award_level_pr_activity_population_complete"] is False
