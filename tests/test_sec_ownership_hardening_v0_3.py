from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from moneysweep.capital_control import ingest
from moneysweep.capital_control.sec13f import Sec13FBulkAdapter, Sec13FError
from moneysweep.sec_equity_identity import SecIdentityError, require_binding
from scripts.download_sec_equity_v2 import _share_denominators
from scripts.rematerialize_sec_holdings_discovery_v2 import classify_identifier

ROOT = Path(__file__).resolve().parents[1]


def _ticker_payload() -> dict[str, object]:
    return {
        "0": {"cik_str": 763901, "ticker": "BPOP", "title": "POPULAR, INC."},
        "1": {"cik_str": 1030469, "ticker": "OFG", "title": "OFG BANCORP"},
        "2": {"cik_str": 1559865, "ticker": "EVTC", "title": "EVERTEC, Inc."},
        "3": {"cik_str": 1633931, "ticker": "EVRI", "title": "TopBuild Corp"},
    }


def test_golden_ticker_cik_bindings_are_stable() -> None:
    payload = _ticker_payload()
    assert require_binding(payload, ticker="BPOP", expected_cik="0000763901").cik == "0000763901"
    assert require_binding(payload, ticker="OFG", expected_cik="0001030469").cik == "0001030469"
    assert require_binding(payload, ticker="EVTC", expected_cik="0001559865").cik == "0001559865"


def test_ofg_wrong_carver_binding_fails_closed() -> None:
    with pytest.raises(SecIdentityError):
        require_binding(_ticker_payload(), ticker="OFG", expected_cik="0001016178")


def test_evtc_is_not_satisfied_by_evri() -> None:
    evtc = require_binding(_ticker_payload(), ticker="EVTC", expected_cik="0001559865")
    evri = require_binding(_ticker_payload(), ticker="EVRI", expected_cik="0001633931")
    assert evtc.cik != evri.cik


def test_form13f_file_number_never_promotes_to_cik() -> None:
    cik, file_number, state = classify_identifier("['028-14486']")
    assert cik == ""
    assert file_number == "028-14486"
    assert state == "FORM13F_FILE_NUMBER"


def test_numeric_cik_is_preserved_as_separate_identifier_family() -> None:
    cik, file_number, state = classify_identifier("763901")
    assert cik == "0000763901"
    assert file_number == ""
    assert state == "CIK"


def test_share_denominator_uses_shares_unit_and_preserves_manifestation() -> None:
    facts = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2026-03-31",
                                "filed": "2026-04-30",
                                "form": "10-Q",
                                "fy": 2026,
                                "fp": "Q1",
                                "accn": "0000763901-26-000001",
                                "val": 65000000,
                            }
                        ]
                    }
                }
            }
        }
    }
    binding = require_binding(_ticker_payload(), ticker="BPOP", expected_cik="0000763901")
    rows = _share_denominators(binding, facts)
    assert len(rows) == 1
    assert rows[0]["shares_outstanding"] == 65000000
    assert rows[0]["unit"] == "shares"
    assert rows[0]["accession_number"] == "0000763901-26-000001"


def _write_zip(path: Path, *, duplicate_info: bool = False) -> None:
    submission = (
        "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
        "0000000123-26-000001\t2026-05-15\t13F-HR\t123\t2026-03-31\n"
    )
    cover = (
        "ACCESSION_NUMBER\tREPORTCALENDARORQUARTER\tISAMENDMENT\tAMENDMENTTYPE\tFILINGMANAGER_NAME\n"
        "0000000123-26-000001\t2026-03-31\tN\t\tManager One LLC\n"
    )
    summary = (
        "ACCESSION_NUMBER\tTABLEENTRYTOTAL\tTABLEVALUETOTAL\n"
        "0000000123-26-000001\t1\t1000\n"
    )
    header = (
        "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\t"
        "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\tOTHERMANAGER\t"
        "VOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE\n"
    )
    info_row = (
        "0000000123-26-000001\t1\tPOPULAR INC\tCOM\t733174700\t100\t500\tSH\t\tSOLE\t\t500\t0\t0\n"
    )
    info = header + info_row + (info_row if duplicate_info else "")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SUBMISSION.tsv", submission)
        zf.writestr("COVERPAGE.tsv", cover)
        zf.writestr("SUMMARYPAGE.tsv", summary)
        zf.writestr("INFOTABLE.tsv", info)


def test_sec13f_adapter_preserves_stable_ids_and_provider_separation(tmp_path: Path) -> None:
    archive = tmp_path / "fixture.zip"
    _write_zip(archive)
    adapter = Sec13FBulkAdapter(
        archive,
        target_cusips=("733174700",),
        issuer_bindings={"733174700": "ISSUER_CIK_0000763901"},
    )
    result = ingest(adapter)
    assert result.input_count == result.retained_count == 1
    row = result.observations[0]
    assert row.holder_id == "INV_CIK_0000000123"
    assert row.issuer_id == "ISSUER_CIK_0000763901"
    assert row.security_id == "CUSIP:733174700"
    assert row.extra["infotable_sk"] == "1"
    assert row.extra["percent_13f_reportable_value"] == 10.0
    assert row.extra["provider_percent_total_assets"] is None
    assert row.extra["provider_metric_equivalence"] == "OPEN"
    audit = adapter.audit()
    assert audit.raw_bytes_sha256 and len(audit.raw_bytes_sha256) == 64
    assert len(audit.member_digests) == 4


def test_sec13f_duplicate_compound_key_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    _write_zip(archive, duplicate_info=True)
    adapter = Sec13FBulkAdapter(
        archive,
        target_cusips=("733174700",),
        issuer_bindings={"733174700": "ISSUER_CIK_0000763901"},
    )
    with pytest.raises(Sec13FError):
        tuple(adapter.iter_records())


def test_uploaded_audit_baseline_is_frozen() -> None:
    data = json.loads(
        (ROOT / "tests" / "fixtures" / "capital_control" / "sec_upload_baseline_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    assert sum(item["rows"] for item in data["files"]) == 310
    assert data["authoritative_identity_bindings"]["BPOP"]["cik"] == "0000763901"
    assert data["authoritative_identity_bindings"]["OFG"]["cik"] == "0001030469"
    assert data["authoritative_identity_bindings"]["EVTC"]["cik"] == "0001559865"
    assert data["known_gaps"]["corporate_target_rows_in_uploaded_holdings"] == 0
