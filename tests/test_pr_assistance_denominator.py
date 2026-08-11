"""Contract tests for the Puerto Rico financial-assistance denominator lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.download_pr_assistance_denominator import ASSISTANCE_FILTER_CODES, _payload, aggregate

pytestmark = pytest.mark.unit


def test_endpoint_filter_denominator_is_all_legacy_financial_assistance_codes():
    assert ASSISTANCE_FILTER_CODES == [
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
    ]


def test_recipient_and_place_of_performance_are_independent_nexus_filters():
    recipient = _payload(2026, "recipient")["filters"]
    pop = _payload(2026, "pop")["filters"]
    assert recipient["recipient_locations"] == [{"country": "USA", "state": "PR"}]
    assert "place_of_performance_locations" not in recipient
    assert pop["place_of_performance_locations"] == [{"country": "USA", "state": "PR"}]
    assert "recipient_locations" not in pop
    assert recipient["prime_award_types"] == pop["prime_award_types"] == ASSISTANCE_FILTER_CODES


def _write_sam(path: Path) -> str:
    frame = pd.DataFrame(
        [
            {
                "Program Title": "Program One",
                "Program Number": "01.001",
                "Federal Agency (030)": "Agency A",
                "Types of Assistance (060)": "PROJECT GRANTS",
            },
            {
                "Program Title": "Program Two",
                "Program Number": "01.002",
                "Federal Agency (030)": "Agency B",
                "Types of Assistance (060)": "DIRECT PAYMENTS FOR SPECIFIED USE",
            },
        ]
    )
    frame.to_csv(path, index=False, encoding="cp1252")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(path: Path, *, fy: int, nexus: str, rows: int) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "pr_assistance_shard_receipt_v1",
                "fiscal_year": fy,
                "nexus": nexus,
                "status": "complete",
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )


def test_aggregate_deduplicates_hard_award_keys_and_classifies_full_program_denominator(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    sam = tmp_path / "sam.csv"
    sam_hash = _write_sam(sam)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "source": {"sha256": sam_hash},
                "denominator": {"financial_program_rows": 2},
            }
        ),
        encoding="utf-8",
    )

    recipient = pd.DataFrame(
        [
            {
                "assistance_listing_number": "01.001",
                "assistance_award_unique_key": "ASST_TEST_1",
                "moneysweep_pr_nexus_evidence": "recipient",
                "moneysweep_source_fiscal_year": "2026",
            }
        ]
    )
    pop = recipient.copy()
    pop["moneysweep_pr_nexus_evidence"] = "pop"
    recipient.to_csv(raw / "pr_assistance_recipient_fy2026.csv", index=False)
    pop.to_csv(raw / "pr_assistance_pop_fy2026.csv", index=False)
    _write_receipt(raw / "pr_assistance_recipient_fy2026.receipt.json", fy=2026, nexus="recipient", rows=1)
    _write_receipt(raw / "pr_assistance_pop_fy2026.receipt.json", fy=2026, nexus="pop", rows=1)

    out = tmp_path / "out"
    coverage = aggregate(raw, out, snapshot, sam, 2026, 2026)
    assert coverage["financial_program_denominator"] == 2
    assert coverage["programs_classified"] == 2
    assert coverage["program_classification_pct"] == 100.0
    assert coverage["deduplicated_prime_awards"] == 1
    assert coverage["confirmed_program_numbers"] == 1
    assert coverage["pr_nexus_state_counts"] == {
        "confirmed_pr_activity": 1,
        "unresolved": 1,
    }
    assert coverage["global_fain_backfill_allowed"] is False

    awards = pd.read_csv(out / "pr_assistance_prime_awards_native_dedup.csv", dtype=str)
    assert len(awards) == 1
    assert awards.iloc[0]["moneysweep_pr_nexus_evidence_set"] == "pop;recipient"

    ledger = pd.read_csv(out / "pr_financial_program_pr_nexus_adjudication.csv", dtype=str)
    states = dict(zip(ledger["program_number"], ledger["pr_nexus_state"], strict=True))
    assert states == {"01.001": "confirmed_pr_activity", "01.002": "unresolved"}


def test_aggregate_fails_closed_when_any_fiscal_year_nexus_shard_is_missing(tmp_path):
    sam = tmp_path / "sam.csv"
    sam_hash = _write_sam(sam)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"source": {"sha256": sam_hash}, "denominator": {"financial_program_rows": 2}}),
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_receipt(raw / "only_one.receipt.json", fy=2026, nexus="recipient", rows=0)
    with pytest.raises(RuntimeError, match="incomplete shard denominator"):
        aggregate(raw, tmp_path / "out", snapshot, sam, 2026, 2026)
