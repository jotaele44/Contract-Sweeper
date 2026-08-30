from __future__ import annotations

from datetime import date

import pytest

from scripts.certify_bpop_sec13f_8q import _select_bpop_denominators
from scripts.certify_sec13f_issuer import SUPPORTED_ISSUERS, _select_exact_denominators

pytestmark = pytest.mark.unit


def test_bpop_denominator_selector_preserves_legacy_semantics() -> None:
    periods = (date(2025, 3, 31), date(2025, 6, 30))
    rows = [
        {
            "ticker": "BPOP",
            "as_of_date": "2025-03-31",
            "shares_outstanding": "100",
            "accession_number": "a",
            "concept": "EntityCommonStockSharesOutstanding",
        },
        {
            "ticker": "BPOP",
            "as_of_date": "2025-06-30",
            "shares_outstanding": "110",
            "accession_number": "b",
            "concept": "EntityCommonStockSharesOutstanding",
        },
        {
            "ticker": "OFG",
            "as_of_date": "2025-03-31",
            "shares_outstanding": "999",
            "accession_number": "c",
            "concept": "EntityCommonStockSharesOutstanding",
        },
    ]
    legacy, legacy_ledger = _select_bpop_denominators(rows, periods)
    generalized, generalized_ledger = _select_exact_denominators(rows, "BPOP", periods)
    assert generalized == legacy
    assert [item["selected_value"] for item in generalized_ledger] == [
        item["selected_value"] for item in legacy_ledger
    ]
    assert [item["state"] for item in generalized_ledger] == [
        item["state"] for item in legacy_ledger
    ]


def test_exact_denominator_fails_closed_on_conflict_or_malformed_value() -> None:
    periods = (date(2025, 3, 31),)
    conflicting = [
        {
            "ticker": "OFG",
            "as_of_date": "2025-03-31",
            "shares_outstanding": "100",
            "accession_number": "a",
            "concept": "x",
        },
        {
            "ticker": "OFG",
            "as_of_date": "2025-03-31",
            "shares_outstanding": "101",
            "accession_number": "b",
            "concept": "x",
        },
    ]
    selected, ledger = _select_exact_denominators(conflicting, "OFG", periods)
    assert selected == {}
    assert ledger[0]["state"] == "UNRESOLVED"
    assert ledger[0]["selected_value"] is None

    malformed = [
        {
            "ticker": "EVTC",
            "as_of_date": "2025-03-31",
            "shares_outstanding": "not-a-number",
            "accession_number": "a",
            "concept": "x",
        }
    ]
    selected, ledger = _select_exact_denominators(malformed, "EVTC", periods)
    assert selected == {}
    assert ledger[0]["state"] == "UNRESOLVED"
    assert ledger[0]["malformed_values"] == ["not-a-number"]


def test_issuer_profiles_preserve_independent_identity_controls() -> None:
    assert SUPPORTED_ISSUERS["BPOP"]["issuer_id"] == "ISSUER_CIK_0000763901"
    assert SUPPORTED_ISSUERS["OFG"]["issuer_id"] == "ISSUER_CIK_0001030469"
    assert "CIK:0001016178" in SUPPORTED_ISSUERS["OFG"]["negative_identity"]
    assert SUPPORTED_ISSUERS["EVTC"]["issuer_id"] == "ISSUER_CIK_0001559865"
    assert "TICKER:EVRI" in SUPPORTED_ISSUERS["EVTC"]["negative_identity"]
    assert "NEAR_NAME_ONLY" in SUPPORTED_ISSUERS["EVTC"]["negative_identity"]
