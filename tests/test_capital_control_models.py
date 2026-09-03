from datetime import date, datetime, timezone

import pytest

from moneysweep.capital_control.validation import (
    ValidationError,
    validate_holding_observation,
    validate_investor_identity,
    validate_source_manifest,
)


def test_pass_identity_requires_binding_evidence() -> None:
    with pytest.raises(ValidationError):
        validate_investor_identity(
            {
                "investor_id": "INV_blackrock_advisors",
                "raw_name": "BlackRock Advisors LLC",
                "identity_level": "LEGAL_ENTITY",
                "identity_status": "PASS",
                "source_id": "SRC_CAP_fixture",
                "binding_basis": "HEURISTIC_DISCOVERY_ONLY",
            }
        )


def test_holding_requires_security_and_source_record() -> None:
    with pytest.raises(ValidationError):
        validate_holding_observation(
            {
                "observation_id": "HOLD_1",
                "holder_id": "INV_1",
                "issuer_id": "ISSUER_1",
                "position_class": "DIRECT_EQUITY",
                "as_of_date": date(2026, 6, 30),
                "report_date": date(2026, 8, 14),
                "source_id": "SRC_CAP_fixture",
                "source_record_id": "",
                "identity_status": "PASS",
            }
        )


def test_frozen_source_requires_bytes_and_hash() -> None:
    with pytest.raises(ValidationError):
        validate_source_manifest(
            {
                "source_id": "SRC_CAP_fixture",
                "source_family": "REGULATORY_HOLDINGS",
                "source_authority": "Fixture Authority",
                "retrieval_utc": datetime(2026, 8, 15, tzinfo=timezone.utc),
                "source_url_or_locator": "fixture://source",
                "byte_status": "FROZEN",
            }
        )
