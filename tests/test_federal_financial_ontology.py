"""Contract tests for the federal financial ontology v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registries" / "federal_financial_ontology_v1.json"
SCHEMA = ROOT / "schemas" / "federal_financial_ontology.schema.json"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_authoritative_award_type_denominator_is_complete():
    r = _registry()
    groups = r["award_type_groups"]
    assert set(groups) == {
        "contracts",
        "loans",
        "idvs",
        "grants",
        "other_financial_assistance",
        "direct_payments",
    }
    codes = [code for group in groups.values() for code in group]
    assert len(codes) == 33
    assert len(codes) == len(set(codes))


def test_procurement_and_assistance_are_separate_branches():
    r = _registry()
    assert r["scope"]["root"] == "federal_financial_flow"
    assert set(r["scope"]["separates"]) == {
        "federal_financial_assistance",
        "federal_procurement",
        "federal_account_non_award_spending",
    }


def test_required_object_kinds_are_present():
    assert set(_registry()["object_kinds"]) >= {
        "program",
        "award",
        "award_action",
        "subaward",
        "entity",
        "account",
        "project",
        "financial_flow",
        "identifier",
        "program_pr_nexus",
        "coverage_audit",
    }


def test_identifier_scopes_are_not_conflated():
    schemes = {row["id"]: row["scope"] for row in _registry()["identifier_schemes"]}
    assert schemes["federal_assistance_id"] == "program"
    assert schemes["fain"] == "assistance_award"
    assert schemes["piid"] == "procurement_award"
    assert schemes["uei"] == "entity"
    assert schemes["subaward_number"] == "subaward"
    assert schemes["modification_number"] == "award_action"
    assert schemes["treasury_account_symbol"] == "account"
    assert schemes["fain"] != schemes["uei"]
    assert schemes["federal_assistance_id"] != schemes["fain"]


def test_federal_assistance_id_is_temporal_and_keeps_legacy_aliases():
    row = next(x for x in _registry()["identifier_schemes"] if x["id"] == "federal_assistance_id")
    assert row["temporal"] is True
    assert set(row["historical_aliases"]) == {"cfda_number", "aln"}


def test_pr_nexus_does_not_equate_eligibility_with_activity():
    states = set(_registry()["pr_nexus_states"])
    assert "confirmed_pr_activity" in states
    assert "pr_eligible_no_activity_recovered" in states
    assert "requires_award_level_test" in states


def test_existing_award_identity_is_preserved():
    bridge = _registry()["bridge_to_existing_contract"]
    assert bridge["legacy_award_id_policy"] == "preserve_existing_award_id_unchanged"
    assert bridge["global_fain_backfill_gate"] == "blocked_until_ontology_certified"


def test_certification_targets_are_fail_closed():
    targets = _registry()["certification_targets"]
    assert targets["instrument_ontology_coverage_pct"] == 100
    assert targets["identifier_ontology_coverage_pct"] == 100
    assert targets["program_denominator_classification_pct"] == 100
    assert targets["unadjudicated_identifier_conflicts"] == 0
    assert targets["special_case_schema_mutations"] == 0


def test_schema_is_strict_draft_2020_12_and_matches_registry_vocabularies():
    r = _registry()
    s = _schema()
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["additionalProperties"] is False
    assert set(s["properties"]["object_kind"]["enum"]) == set(r["object_kinds"])
    identifier_enum = set(s["properties"]["identifier_scheme"]["enum"])
    identifier_enum.discard(None)
    assert identifier_enum == {x["id"] for x in r["identifier_schemes"]}
