from datetime import date

import pytest

from moneysweep.capital_control.analytics import compare_sets, current_positions, rollup_positions
from moneysweep.capital_control.models import HoldingObservation, InvestorIdentity


def _row(observation_id: str, holder_id: str, issuer_id: str, as_of: date) -> HoldingObservation:
    return HoldingObservation(
        observation_id=observation_id,
        holder_id=holder_id,
        issuer_id=issuer_id,
        security_id="SEC_COMMON",
        position_class="DIRECT_EQUITY",
        as_of_date=as_of,
        report_date=as_of,
        source_id=f"SRC_CAP_{observation_id}",
        source_record_id=observation_id,
        identity_status="PASS",
        percent_issuer=1.0,
    )


def test_pairwise_set_math_closes() -> None:
    result = compare_sets(["a", "b"], ["b", "c"])
    assert result.intersection == frozenset({"b"})
    assert result.a_only == frozenset({"a"})
    assert result.b_only == frozenset({"c"})
    assert result.union == frozenset({"a", "b", "c"})
    assert result.symmetric_difference == frozenset({"a", "c"})
    assert len(result.intersection) + len(result.symmetric_difference) == len(result.union)


def test_current_positions_selects_newest_whole_row() -> None:
    old = _row("HOLD_old", "INV_a", "ISSUER_a", date(2026, 3, 31))
    new = _row("HOLD_new", "INV_a", "ISSUER_a", date(2026, 6, 30))
    selected = current_positions([old, new])
    assert selected == (new,)


def test_current_positions_tied_top_rows_fail_closed() -> None:
    first = _row("HOLD_a", "INV_a", "ISSUER_a", date(2026, 6, 30))
    second = _row("HOLD_b", "INV_a", "ISSUER_a", date(2026, 6, 30))
    with pytest.raises(ValueError, match="tied current observations"):
        current_positions([first, second])


def test_rollups_do_not_destroy_legal_holder_rows() -> None:
    observations = [
        _row("HOLD_a", "INV_a", "ISSUER_a", date(2026, 6, 30)),
        _row("HOLD_b", "INV_b", "ISSUER_a", date(2026, 6, 30)),
    ]
    identities = {
        "INV_a": InvestorIdentity(
            investor_id="INV_a",
            raw_name="Fund A",
            identity_level="FUND_OR_VEHICLE",
            identity_status="PASS",
            source_id="SRC_CAP_fixture",
            legal_entity_id="LE_a",
            investor_family_id="FAM_shared",
            ultimate_parent_id="PARENT_shared",
            binding_basis="AUTHORITATIVE_BINDING",
        ),
        "INV_b": InvestorIdentity(
            investor_id="INV_b",
            raw_name="Fund B",
            identity_level="FUND_OR_VEHICLE",
            identity_status="PASS",
            source_id="SRC_CAP_fixture",
            legal_entity_id="LE_b",
            investor_family_id="FAM_shared",
            ultimate_parent_id="PARENT_shared",
            binding_basis="AUTHORITATIVE_BINDING",
        ),
    }
    legal = rollup_positions(observations, identities, "LEGAL_HOLDER")
    family = rollup_positions(observations, identities, "INVESTOR_FAMILY")
    parent = rollup_positions(observations, identities, "ULTIMATE_PARENT")
    assert set(legal) == {"LE_a", "LE_b"}
    assert set(family) == {"FAM_shared"}
    assert set(parent) == {"PARENT_shared"}
    assert len(family["FAM_shared"]) == 2


def test_unbound_identity_cannot_drive_family_or_parent_rollup() -> None:
    observation = _row("HOLD_a", "INV_a", "ISSUER_a", date(2026, 6, 30))
    identities = {
        "INV_a": InvestorIdentity(
            investor_id="INV_a",
            raw_name="Fund A",
            identity_level="FUND_OR_VEHICLE",
            identity_status="PROVISIONAL",
            source_id="SRC_CAP_fixture",
            legal_entity_id="LE_candidate",
            investor_family_id="FAM_candidate",
            ultimate_parent_id="PARENT_candidate",
            binding_basis="HEURISTIC_DISCOVERY_ONLY",
        )
    }
    assert set(rollup_positions([observation], identities, "LEGAL_HOLDER")) == {"INV_a"}
    assert set(rollup_positions([observation], identities, "INVESTOR_FAMILY")) == {"INV_a"}
    assert set(rollup_positions([observation], identities, "ULTIMATE_PARENT")) == {"INV_a"}
