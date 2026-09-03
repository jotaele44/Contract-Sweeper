from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from moneysweep.capital_control import ingest
from moneysweep.capital_control.sec13f import (
    Sec13FBulkAdapter,
    Sec13FError,
    adjudicate_sec13f_filing_restatements,
)
from moneysweep.sec_equity_identity import SecIdentityError, require_binding
from scripts.download_sec import PR_DOMICILED
from scripts.download_sec_equity_v2 import _share_denominators
from scripts.rematerialize_sec_holdings_discovery_v2 import classify_identifier
from scripts.certify_bpop_sec13f_8q import (
    _freeze_identity_issues,
    _holder_identity_cardinality_closed,
    _partition_required_periods,
    _serialize_filing_lineage,
)

ROOT = Path(__file__).resolve().parents[1]


def _ticker_payload() -> dict[str, object]:
    return {
        "0": {"cik_str": 763901, "ticker": "BPOP", "title": "POPULAR, INC."},
        "1": {"cik_str": 1030469, "ticker": "OFG", "title": "OFG BANCORP"},
        "2": {"cik_str": 1559865, "ticker": "EVTC", "title": "EVERTEC, Inc."},
        "3": {"cik_str": 1318568, "ticker": "EVRI", "title": "EVERI HOLDINGS INC."},
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
    evri = require_binding(_ticker_payload(), ticker="EVRI", expected_cik="0001318568")
    assert evtc.cik != evri.cik
    with pytest.raises(SecIdentityError):
        require_binding(_ticker_payload(), ticker="EVRI", expected_cik="0001633931")


def test_legacy_sec_download_bindings_use_canonical_ciks() -> None:
    by_ticker = {item["ticker"]: item["cik"] for item in PR_DOMICILED}
    assert by_ticker["OFG"] == "0001030469"
    assert by_ticker["EVRI"] == "0001318568"


def test_certification_period_partition_preserves_every_candidate(tmp_path: Path) -> None:
    archive = tmp_path / "sec13f.zip"
    _write_zip(archive)
    rows = list(
        ingest(
            Sec13FBulkAdapter(
                archive,
                target_cusips=["733174700"],
                issuer_bindings={"733174700": "ISSUER_BPOP"},
            )
        ).observations
    )
    assert rows
    inside = rows[0]
    outside = replace(
        inside, observation_id=f"{inside.observation_id}_OLD", as_of_date=date(2020, 3, 31)
    )

    scoped, excluded = _partition_required_periods([inside, outside], [inside.as_of_date])

    assert scoped == (inside,)
    assert excluded == (outside,)
    assert len(scoped) + len(excluded) == 2


def test_holder_cardinality_uses_only_materialized_period_partition() -> None:
    in_scope = {"INV_CIK_0000763901"}
    all_discovered = in_scope | {"INV_CIK_0001318568"}

    assert _holder_identity_cardinality_closed(in_scope, in_scope) is True
    assert _holder_identity_cardinality_closed(in_scope, all_discovered) is False


def test_filing_restatement_supersedes_prior_retained_rows_as_a_set(tmp_path: Path) -> None:
    archive = tmp_path / "sec13f.zip"
    _write_zip(archive)
    seed = next(
        iter(
            ingest(
                Sec13FBulkAdapter(
                    archive,
                    target_cusips=["733174700"],
                    issuer_bindings={"733174700": "ISSUER_BPOP"},
                )
            ).observations
        )
    )

    def filing_row(suffix: str, accession: str, filed: date, raw_type: str):
        return replace(
            seed,
            observation_id=f"{seed.observation_id}_{suffix}",
            source_record_id=f"{accession}:{suffix}",
            report_date=filed,
            extra={
                **seed.extra,
                "accession_number": accession,
                "source_amendment_type": raw_type,
            },
        )

    original = [
        filing_row("O1", "0000763901-25-000001", date(2025, 2, 1), "ORIGINAL"),
        filing_row("O2", "0000763901-25-000001", date(2025, 2, 1), "ORIGINAL"),
    ]
    addition = [filing_row("A1", "0000763901-25-000002", date(2025, 2, 15), "NEW HOLDINGS")]
    restatement = [
        filing_row(f"R{index}", "0000763901-25-000003", date(2025, 3, 1), "RESTATEMENT")
        for index in range(1, 4)
    ]

    result = adjudicate_sec13f_filing_restatements([*original, *addition, *restatement])

    assert result.superseded_observation_ids == frozenset(
        row.observation_id for row in [*original, *addition]
    )
    assert result.active_observation_ids == frozenset(row.observation_id for row in restatement)
    assert result.lineages[0].state == "PRIOR_RETAINED_FILING_SUPERSEDED"
    assert result.lineages[0].prior_filing_accession_numbers == (
        "0000763901-25-000001",
        "0000763901-25-000002",
    )
    assert (
        json.loads(json.dumps(_serialize_filing_lineage(result.lineages[0])))["as_of_date"]
        == seed.as_of_date.isoformat()
    )


def test_filing_restatement_can_introduce_first_retained_target_row(tmp_path: Path) -> None:
    archive = tmp_path / "sec13f.zip"
    _write_zip(archive)
    seed = next(
        iter(
            ingest(
                Sec13FBulkAdapter(
                    archive,
                    target_cusips=["733174700"],
                    issuer_bindings={"733174700": "ISSUER_BPOP"},
                )
            ).observations
        )
    )
    restatement = replace(
        seed,
        amendment_status="UNKNOWN",
        extra={**seed.extra, "source_amendment_type": "RESTATEMENT"},
    )

    result = adjudicate_sec13f_filing_restatements([restatement])

    assert result.active_observation_ids == frozenset({restatement.observation_id})
    assert result.superseded_observation_ids == frozenset()
    assert result.lineages[0].state == "NO_PRIOR_TARGET_ROWS_RETAINED"


def test_freeze_identity_compares_archive_and_member_payloads() -> None:
    member = {"path": "INFOTABLE.tsv", "uncompressed_size": 7, "sha256": "a" * 64}
    freeze = {
        "archive_count": 1,
        "archives": [
            {"filename": "quarter.zip", "byte_size": 11, "sha256": "b" * 64, "members": [member]}
        ],
    }
    audit = {
        "archive": "quarter.zip",
        "byte_size": 11,
        "sha256": "b" * 64,
        "member_digests": [member],
    }

    assert _freeze_identity_issues(freeze, [audit], ["quarter.zip"]) == []
    changed = {**audit, "member_digests": [{**member, "sha256": "c" * 64}]}
    assert _freeze_identity_issues(freeze, [changed], ["quarter.zip"]) == [
        "quarter.zip: member path/size/SHA payload differs from frozen manifest"
    ]


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
    summary = "ACCESSION_NUMBER\tTABLEENTRYTOTAL\tTABLEVALUETOTAL\n0000000123-26-000001\t1\t1000\n"
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


def _write_same_cik_name_variation_zip(path: Path) -> None:
    submission = (
        "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
        "0000000123-26-000001\t2026-05-15\t13F-HR\t123\t2026-03-31\n"
        "0000000123-26-000002\t2026-05-16\t13F-HR\t123\t2026-03-31\n"
    )
    cover = (
        "ACCESSION_NUMBER\tREPORTCALENDARORQUARTER\tISAMENDMENT\tAMENDMENTTYPE\tFILINGMANAGER_NAME\n"
        "0000000123-26-000001\t2026-03-31\tN\t\tManager One LLC\n"
        "0000000123-26-000002\t2026-03-31\tN\t\tMANAGER ONE, L.L.C.\n"
    )
    summary = (
        "ACCESSION_NUMBER\tTABLEENTRYTOTAL\tTABLEVALUETOTAL\n"
        "0000000123-26-000001\t1\t1000\n"
        "0000000123-26-000002\t1\t1200\n"
    )
    info = (
        "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tVALUE\t"
        "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\tOTHERMANAGER\t"
        "VOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE\n"
        "0000000123-26-000001\t1\tPOPULAR INC\tCOM\t733174700\t100\t500\tSH\t\tSOLE\t\t500\t0\t0\n"
        "0000000123-26-000002\t2\tPOPULAR INC\tCOM\t733174700\t120\t600\tSH\t\tSOLE\t\t600\t0\t0\n"
    )
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


def test_same_cik_preserves_all_raw_manager_name_manifestations(tmp_path: Path) -> None:
    archive = tmp_path / "name-variation.zip"
    _write_same_cik_name_variation_zip(archive)
    adapter = Sec13FBulkAdapter(
        archive,
        target_cusips=("733174700",),
        issuer_bindings={"733174700": "ISSUER_CIK_0000763901"},
    )
    result = ingest(adapter)
    assert result.input_count == result.retained_count == 2
    assert {row.holder_id for row in result.observations} == {"INV_CIK_0000000123"}
    assert {row.extra["filing_manager_name_raw"] for row in result.observations} == {
        "Manager One LLC",
        "MANAGER ONE, L.L.C.",
    }
    investors = adapter.iter_investors()
    assert len(investors) == 1
    assert investors[0].investor_id == "INV_CIK_0000000123"
    assert investors[0].binding_basis == "STABLE_ID"


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
        (
            ROOT / "tests" / "fixtures" / "capital_control" / "sec_upload_baseline_v0_1.json"
        ).read_text(encoding="utf-8")
    )
    assert sum(item["rows"] for item in data["files"]) == 310
    assert data["authoritative_identity_bindings"]["BPOP"]["cik"] == "0000763901"
    assert data["authoritative_identity_bindings"]["OFG"]["cik"] == "0001030469"
    assert data["authoritative_identity_bindings"]["EVTC"]["cik"] == "0001559865"
    assert data["known_gaps"]["corporate_target_rows_in_uploaded_holdings"] == 0
