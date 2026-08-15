from datetime import date

import pytest

from moneysweep.capital_control.models import HoldingObservation
from moneysweep.capital_control.supersession import apply_supersession


def _row(observation_id: str, source_record_id: str, supersedes: str | None = None) -> HoldingObservation:
    return HoldingObservation(
        observation_id=observation_id,
        holder_id="INV_holder",
        issuer_id="ISSUER_a",
        security_id="CUSIP_1",
        position_class="DIRECT_EQUITY",
        as_of_date=date(2026, 6, 30),
        report_date=date(2026, 8, 14),
        source_id="SRC_CAP_fixture",
        source_record_id=source_record_id,
        identity_status="PASS",
        amendment_status="AMENDED" if supersedes else "ORIGINAL",
        supersedes_observation_id=supersedes,
    )


def test_amendment_supersedes_original_without_deleting_it() -> None:
    original = _row("HOLD_original", "record-original")
    amended = _row("HOLD_amended", "record-amended", "HOLD_original")
    result = apply_supersession([original, amended])
    assert [row.observation_id for row in result.active] == ["HOLD_amended"]
    assert [row.observation_id for row in result.superseded] == ["HOLD_original"]
    assert result.superseded[0].identity_status == "SUPERSEDED"


def test_duplicate_source_record_fails_closed() -> None:
    with pytest.raises(ValueError):
        apply_supersession([_row("HOLD_a", "same"), _row("HOLD_b", "same")])
