from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

import pytest

from moneysweep.capital_control.ingestion import ingest
from moneysweep.capital_control.validation import ValidationError


class FixtureAdapter:
    def __init__(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        source_id: str = "SRC_CAP_fixture",
        record_count: int | None = None,
    ) -> None:
        self._rows = tuple(rows)
        self._source_id = source_id
        self._record_count = len(self._rows) if record_count is None else record_count

    def iter_records(self) -> Iterable[Mapping[str, Any]]:
        return iter(self._rows)

    def source_manifest(self) -> Mapping[str, Any]:
        return {
            "source_id": self._source_id,
            "source_family": "REGULATORY_HOLDINGS",
            "source_authority": "Fixture Authority",
            "retrieval_utc": datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
            "source_url_or_locator": "fixture://holdings",
            "byte_status": "REMOTE_ONLY",
            "record_count": self._record_count,
            "canonicality": "CANONICAL",
        }


def _row(observation_id: str, source_record_id: str, source_id: str = "SRC_CAP_fixture") -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "holder_id": "INV_holder",
        "issuer_id": "ISSUER_a",
        "position_class": "DIRECT_EQUITY",
        "as_of_date": date(2026, 6, 30),
        "report_date": date(2026, 8, 14),
        "source_id": source_id,
        "source_record_id": source_record_id,
        "identity_status": "PASS",
        "security_id": "SEC_1",
        "amendment_status": "ORIGINAL",
    }


def test_ingest_closes_row_count_and_preserves_whole_rows() -> None:
    rows = [_row("HOLD_a", "record-a"), _row("HOLD_b", "record-b")]
    result = ingest(FixtureAdapter(rows))
    assert result.input_count == 2
    assert result.retained_count == 2
    assert [row.observation_id for row in result.observations] == ["HOLD_a", "HOLD_b"]
    assert len(result.fingerprints) == 2
    assert len(set(result.fingerprints)) == 2


def test_ingest_fails_closed_on_manifest_count_mismatch() -> None:
    with pytest.raises(ValidationError, match="record count mismatch"):
        ingest(FixtureAdapter([_row("HOLD_a", "record-a")], record_count=2))


def test_ingest_fails_closed_on_source_binding_mismatch() -> None:
    with pytest.raises(ValidationError, match="does not match manifest"):
        ingest(FixtureAdapter([_row("HOLD_a", "record-a", "SRC_CAP_other")]))


def test_ingest_fails_closed_on_duplicate_source_record() -> None:
    rows = [_row("HOLD_a", "same"), _row("HOLD_b", "same")]
    with pytest.raises(ValidationError, match="duplicate source_record_id"):
        ingest(FixtureAdapter(rows))
