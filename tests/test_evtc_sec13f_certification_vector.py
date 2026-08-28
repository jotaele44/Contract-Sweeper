from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / "data" / "manifests" / "capital_control" / "evtc_sec13f_certification_vector_v1.json"


def test_evtc_vector_starts_open_and_cannot_inherit_bpop_pass() -> None:
    payload = json.loads(VECTOR.read_text(encoding="utf-8"))
    assert payload["state"] == "OPEN"
    assert payload["promotion_state"] == "BLOCKED_UNTIL_ZERO_RESIDUE_PASS"
    assert payload["parent_main_sha"] == "f4b5d11806b4d0341dcb1d16bc6e17f122f01600"
    assert payload["parent_bpop_certification"].endswith("NOT_INHERITED")
    assert payload["issuer"] == {
        "ticker": "EVTC",
        "canonical_name": "EVERTEC, Inc.",
        "issuer_id": "ISSUER_CIK_0001559865",
        "cik": "0001559865",
        "cusip": "30040P103",
    }
    assert payload["negative_identity_gate"]["forbidden_ticker"] == "EVRI"
    assert payload["provider_equivalence"] == "OPEN"
    assert payload["synthetic_row_identity"] == "FORBIDDEN"
    assert payload["deep_dive_promotion"] == "NOT_ELIGIBLE"
    assert payload["blockers"]


def test_evtc_vector_requires_independent_zero_residue_gates() -> None:
    payload = json.loads(VECTOR.read_text(encoding="utf-8"))
    gates = set(payload["required_gates"])
    required = {
        "define_exact_EVTC_period_denominator",
        "verify_EVTC_stable_issuer_binding",
        "verify_EVRI_does_not_satisfy_EVTC_identity",
        "preserve_whole_source_observations",
        "filing_level_amendment_lineage_closed",
        "exact_historical_share_denominator_each_certified_period",
        "issuer_percentage_arithmetic_closed",
        "provider_equivalence_OPEN",
        "zero_unresolved_residue_inside_claim",
        "independent_exact_head_CI_PASS",
    }
    assert required <= gates
