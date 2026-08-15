from __future__ import annotations

import pandas as pd

from server.backend import main as api


def row(
    observation_id: str,
    issuer: str,
    holder: str,
    *,
    family: str = "",
    parent: str = "",
    seq: str = "0",
    pct: str = "1.0",
) -> dict[str, str]:
    return {
        "observation_id": observation_id,
        "issuer_id": issuer,
        "issuer_name": f"Issuer {issuer}",
        "security_id": f"SEC-{issuer}",
        "holder_legal_entity_id": holder,
        "holder_reported_name_raw": holder,
        "investor_family_id": family,
        "ultimate_parent_id": parent,
        "as_of_date": "2026-06-30",
        "report_date": "2026-08-01",
        "position_class": "FUND",
        "relation_type": "FUND_HOLDING",
        "identity_status": "CERTIFIED",
        "source_id": "SEC",
        "source_document_id": f"DOC-{observation_id}",
        "percent_issuer": pct,
        "amendment_sequence": seq,
    }


def test_amendment_supersession_is_whole_row_and_deterministic():
    frame = pd.DataFrame([
        row("O2", "A", "H1", seq="1", pct="2.0"),
        row("O1", "A", "H1", seq="0", pct="1.0"),
    ])
    effective, ties = api._capital_effective(frame)
    assert ties == 0
    assert effective["observation_id"].tolist() == ["O2"]
    assert effective["percent_issuer"].tolist() == ["2.0"]


def test_tied_top_amendments_fail_closed_instead_of_order_selection():
    frame = pd.DataFrame([
        row("O1", "A", "H1", seq="1"),
        row("O2", "A", "H1", seq="1"),
    ])
    effective, ties = api._capital_effective(frame)
    assert effective.empty
    assert ties == 1


def test_legal_holder_family_and_parent_are_distinct_identity_levels():
    frame = pd.DataFrame([
        row("A1", "A", "BLACKROCK-FUND-ADVISORS", family="BLACKROCK", parent="BLK"),
        row("A2", "A", "BLACKROCK-ADVISORS-LLC", family="BLACKROCK", parent="BLK"),
        row("B1", "B", "BLACKROCK-ADVISORS-LLC", family="BLACKROCK", parent="BLK"),
    ])
    legal = api._capital_compare(frame, "A", "B", "legal_holder")
    family = api._capital_compare(frame, "A", "B", "investor_family")
    parent = api._capital_compare(frame, "A", "B", "ultimate_parent")

    assert legal["intersection"] == ["BLACKROCK-ADVISORS-LLC"]
    assert legal["aOnly"] == ["BLACKROCK-FUND-ADVISORS"]
    assert legal["bOnly"] == []
    assert family["intersection"] == ["BLACKROCK"]
    assert family["aOnly"] == []
    assert parent["intersection"] == ["BLK"]
    assert legal["union"] == sorted(
        set(legal["intersection"] + legal["aOnly"] + legal["bOnly"])
    )
    assert legal["symmetricDifference"] == sorted(legal["aOnly"] + legal["bOnly"])


def test_unknown_identity_level_fails_closed():
    frame = pd.DataFrame([row("O1", "A", "H1")])
    try:
        api._capital_compare(frame, "A", "B", "normalized_name")
    except ValueError as exc:
        assert "unsupported identity_level" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsupported identity level must not be accepted")
