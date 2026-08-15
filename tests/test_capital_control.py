from __future__ import annotations

from datetime import date
from decimal import Decimal

from moneysweep.capital_control import (
    HoldingObservation,
    IdentityStatus,
    PositionClass,
    RelationType,
    compare_issuers,
    effective_observations,
    validate_observation,
)


def obs(
    observation_id: str,
    issuer: str,
    holder: str,
    *,
    family: str | None = None,
    parent: str | None = None,
    seq: int = 0,
    pct: str = "1.0",
) -> HoldingObservation:
    return HoldingObservation(
        observation_id=observation_id,
        issuer_id=issuer,
        security_id=f"SEC-{issuer}",
        holder_legal_entity_id=holder,
        holder_reported_name_raw=holder,
        investor_family_id=family,
        ultimate_parent_id=parent,
        as_of_date=date(2026, 6, 30),
        report_date=date(2026, 8, 1),
        source_id="SEC",
        source_document_id=f"DOC-{observation_id}",
        position_class=PositionClass.FUND,
        relation_type=RelationType.FUND_HOLDING,
        identity_status=IdentityStatus.CERTIFIED,
        percent_issuer=Decimal(pct),
        amendment_sequence=seq,
    )


def test_amendment_supersession_is_whole_row_and_deterministic():
    old = obs("O1", "A", "H1", seq=0, pct="1.0")
    amended = obs("O2", "A", "H1", seq=1, pct="2.0")
    rows = effective_observations([amended, old])
    assert rows == [amended]
    assert rows[0].percent_issuer == Decimal("2.0")


def test_tied_top_amendments_fail_closed_instead_of_nearest_or_order_selection():
    a = obs("O1", "A", "H1", seq=1)
    b = obs("O2", "A", "H1", seq=1)
    assert effective_observations([a, b]) == []


def test_legal_holder_family_and_parent_are_distinct_identity_levels():
    rows = [
        obs("A1", "A", "BLACKROCK-FUND-ADVISORS", family="BLACKROCK", parent="BLK"),
        obs("A2", "A", "BLACKROCK-ADVISORS-LLC", family="BLACKROCK", parent="BLK"),
        obs("B1", "B", "BLACKROCK-ADVISORS-LLC", family="BLACKROCK", parent="BLK"),
    ]
    legal = compare_issuers(rows, "A", "B", identity_level="legal_holder")
    family = compare_issuers(rows, "A", "B", identity_level="investor_family")
    assert legal["intersection"] == ["BLACKROCK-ADVISORS-LLC"]
    assert legal["a_only"] == ["BLACKROCK-FUND-ADVISORS"]
    assert family["intersection"] == ["BLACKROCK"]
    assert family["a_only"] == []
    assert legal["union"] == sorted(set(legal["intersection"] + legal["a_only"] + legal["b_only"]))
    assert legal["symmetric_difference"] == sorted(legal["a_only"] + legal["b_only"])


def test_investment_adviser_does_not_imply_direct_equity():
    row = HoldingObservation(
        observation_id="BAD",
        issuer_id="A",
        security_id="SEC-A",
        holder_legal_entity_id="ADVISER",
        holder_reported_name_raw="Adviser LLC",
        as_of_date=date(2026, 6, 30),
        report_date=date(2026, 8, 1),
        source_id="SOURCE",
        source_document_id="DOC",
        position_class=PositionClass.INVESTMENT_ADVISER,
        relation_type=RelationType.DIRECT_EQUITY,
        identity_status=IdentityStatus.PROVISIONAL,
    )
    assert "investment adviser cannot imply direct equity without a distinct ownership observation" in validate_observation(row)


def test_percentage_bounds_fail_closed():
    row = obs("O1", "A", "H1", pct="101")
    assert "percent_issuer outside 0..100" in validate_observation(row)
