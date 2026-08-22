from datetime import date, datetime, timedelta, timezone

import pytest

from moneysweep.capital_control.validation import (
    ValidationError,
    validate_holding_observation,
    validate_investor_identity,
    validate_source_manifest,
)


def _holding_payload() -> dict[str, object]:
    return {
        "observation_id": "HOLD_a",
        "holder_id": "INV_a",
        "issuer_id": "ISSUER_a",
        "position_class": "DIRECT_EQUITY",
        "as_of_date": date(2026, 6, 30),
        "report_date": date(2026, 8, 14),
        "source_id": "SRC_CAP_fixture",
        "source_record_id": "record-a",
        "identity_status": "PASS",
        "security_id": "SEC_1",
    }


def test_invalid_nonpass_binding_basis_is_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid binding_basis"):
        validate_investor_identity(
            {
                "investor_id": "INV_a",
                "raw_name": "Fund A",
                "identity_level": "FUND_OR_VEHICLE",
                "identity_status": "PROVISIONAL",
                "source_id": "SRC_CAP_fixture",
                "binding_basis": "NAME_ONLY",
            }
        )


def test_holding_rejects_string_date_and_invalid_semantic_state() -> None:
    payload = _holding_payload()
    payload["as_of_date"] = "2026-06-30"
    with pytest.raises(ValidationError, match="as_of_date must be a date"):
        validate_holding_observation(payload)

    payload = _holding_payload()
    payload["control_status"] = "MAYBE"
    with pytest.raises(ValidationError, match="invalid control_status"):
        validate_holding_observation(payload)


def test_holding_rejects_report_before_as_of_date() -> None:
    payload = _holding_payload()
    payload["report_date"] = date(2026, 6, 29)
    with pytest.raises(ValidationError, match="report_date cannot precede as_of_date"):
        validate_holding_observation(payload)


def test_supersession_reference_requires_amended_status() -> None:
    payload = _holding_payload()
    payload["supersedes_observation_id"] = "HOLD_prior"
    payload["amendment_status"] = "ORIGINAL"
    with pytest.raises(ValidationError, match="requires AMENDED status"):
        validate_holding_observation(payload)


def test_source_manifest_rejects_unknown_enums_and_non_utc_retrieval() -> None:
    base = {
        "source_id": "SRC_CAP_fixture",
        "source_family": "REGULATORY_HOLDINGS",
        "source_authority": "Fixture Authority",
        "retrieval_utc": datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
        "source_url_or_locator": "fixture://source",
        "byte_status": "REMOTE_ONLY",
        "canonicality": "CANONICAL",
    }
    bad_family = dict(base, source_family="WEB_SEARCH")
    with pytest.raises(ValidationError, match="invalid source_family"):
        validate_source_manifest(bad_family)

    non_utc = dict(
        base,
        retrieval_utc=datetime(
            2026,
            8,
            15,
            6,
            0,
            tzinfo=timezone(timedelta(hours=-4)),
        ),
    )
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        validate_source_manifest(non_utc)
