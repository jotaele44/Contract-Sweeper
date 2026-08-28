from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "moneysweep-ownership-capital" / "SKILL.md"
CASES = ROOT / "tests" / "skill_contract" / "fixtures" / "ownership_capital_adversarial.json"
FREEZE = ROOT / "data" / "manifests" / "capital_control" / "bpop_deep_dive_endpoint_v1.json"


def test_adversarial_matrix_is_complete_and_fail_closed() -> None:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    cases = {item["id"]: item for item in payload["cases"]}
    expected_blocked = {
        "OFG_REGRESSION_NOT_CERTIFICATION",
        "EVTC_EVRI_IDENTITY_COLLISION",
        "BRAND_FAMILY_AGGREGATION",
        "NEAREST_DATE_DENOMINATOR",
        "CURRENT_SHARE_DENOMINATOR",
        "MORNINGSTAR_EQUIVALENCE",
        "FAKE_ROW_LEVEL_RESTATEMENT_LINEAGE",
        "DUPLICATE_SOURCE_RECORD",
        "NAME_ONLY_HOLDER_BINDING",
    }
    assert expected_blocked <= set(cases)
    assert all(cases[case_id]["expected_state"] == "BLOCKED" for case_id in expected_blocked)
    assert cases["BPOP_CERTIFIED_SCOPE"]["expected_state"] == "PASS"
    assert all(item["required_reason"] for item in cases.values())


def test_skill_text_preserves_all_adversarial_boundaries() -> None:
    text = SKILL.read_text(encoding="utf-8")
    required = (
        "OFG and EVTC are real-source regression fixtures only",
        "Morningstar/provider `% Total Assets` remains a distinct manifestation",
        "Do not sum positions across reporting managers",
        "Nearest-date, current-share",
        "do not invent row-to-row predecessor identity",
        "duplicate `(ACCESSION_NUMBER, INFOTABLE_SK)`",
        "name-only holder/issuer identity promotion",
        "EVRI",
        "ownership_capital_adversarial.json",
    )
    missing = [fragment for fragment in required if fragment not in text]
    assert not missing, f"ownership skill lost adversarial boundaries: {missing}"


def test_frozen_deep_dive_endpoint_cannot_promote_regression_issuers() -> None:
    payload = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert payload["state"] == "PASS"
    assert payload["deep_dive_exact_green_head"] == "d90c8f629d242ed0efc11532bd551fd407e23c44"
    assert payload["deep_dive_merge_commit"] == "795fef0d208bee60a0d43b020bf4a5de59d55cec"
    assert (
        payload["provider_equivalence"][
            "morningstar_percent_total_assets_vs_sec_13f_reportable_portfolio_percent"
        ]
        == "OPEN"
    )
    assert (
        payload["aggregation_policy"] == "WHOLE_SOURCE_OBSERVATIONS_ONLY_NO_CROSS_HOLDER_SUMMATION"
    )
    assert payload["synthetic_row_identity"] == "FORBIDDEN"
    assert payload["issuer_promotion"] == {
        "BPOP": "PASS",
        "OFG": "NOT_CERTIFIED_REGRESSION_ONLY",
        "EVTC": "NOT_CERTIFIED_REGRESSION_ONLY",
    }
