from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from moneysweep.capital_control import apply_supersession, ingest
from moneysweep.capital_control.sec13f import (
    Sec13FBulkAdapter,
    Sec13FError,
    adjudicate_sec13f_restatements,
)
from moneysweep.query.adapters.capital_control import Sec13FCapitalControlAdapter
from moneysweep.query.entity_types import EntityIdentifier, EntityQuery


def _tsv(fieldnames: list[str], rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _archive(
    path: Path,
    *,
    accession: str = "0000000001-26-000001",
    cik: str = "102909",
    manager: str = "Vanguard Test Manager",
    cusip: str = "733174700",
    issuer: str = "POPULAR INC",
    period: str = "31-MAR-2026",
    filing_date: str = "15-MAY-2026",
    is_amendment: str = "N",
    amendment_type: str = "",
    infotable_sk: str = "1",
    shares: str = "100",
    value: str = "2500",
    table_value_total: str = "10000",
    duplicate_info_key: bool = False,
) -> Path:
    submission_fields = ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"]
    cover_fields = [
        "ACCESSION_NUMBER",
        "REPORTCALENDARORQUARTER",
        "ISAMENDMENT",
        "AMENDMENTTYPE",
        "FILINGMANAGER_NAME",
    ]
    summary_fields = ["ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"]
    info_fields = [
        "ACCESSION_NUMBER",
        "INFOTABLE_SK",
        "NAMEOFISSUER",
        "TITLEOFCLASS",
        "CUSIP",
        "FIGI",
        "VALUE",
        "SSHPRNAMT",
        "SSHPRNAMTTYPE",
        "PUTCALL",
        "INVESTMENTDISCRETION",
        "OTHERMANAGER",
        "VOTING_AUTH_SOLE",
        "VOTING_AUTH_SHARED",
        "VOTING_AUTH_NONE",
    ]
    submission_type = "13F-HR/A" if is_amendment.upper() in {"Y", "YES", "1", "TRUE"} else "13F-HR"
    info = {
        "ACCESSION_NUMBER": accession,
        "INFOTABLE_SK": infotable_sk,
        "NAMEOFISSUER": issuer,
        "TITLEOFCLASS": "COM",
        "CUSIP": cusip,
        "FIGI": "",
        "VALUE": value,
        "SSHPRNAMT": shares,
        "SSHPRNAMTTYPE": "SH",
        "PUTCALL": "",
        "INVESTMENTDISCRETION": "SOLE",
        "OTHERMANAGER": "",
        "VOTING_AUTH_SOLE": shares,
        "VOTING_AUTH_SHARED": "0",
        "VOTING_AUTH_NONE": "0",
    }
    info_rows = [info, dict(info)] if duplicate_info_key else [info]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            _tsv(
                submission_fields,
                [{
                    "ACCESSION_NUMBER": accession,
                    "FILING_DATE": filing_date,
                    "SUBMISSIONTYPE": submission_type,
                    "CIK": cik,
                    "PERIODOFREPORT": period,
                }],
            ),
        )
        zf.writestr(
            "COVERPAGE.tsv",
            _tsv(
                cover_fields,
                [{
                    "ACCESSION_NUMBER": accession,
                    "REPORTCALENDARORQUARTER": period,
                    "ISAMENDMENT": is_amendment,
                    "AMENDMENTTYPE": amendment_type,
                    "FILINGMANAGER_NAME": manager,
                }],
            ),
        )
        zf.writestr(
            "SUMMARYPAGE.tsv",
            _tsv(
                summary_fields,
                [{
                    "ACCESSION_NUMBER": accession,
                    "TABLEENTRYTOTAL": "1",
                    "TABLEVALUETOTAL": table_value_total,
                }],
            ),
        )
        zf.writestr("INFOTABLE.tsv", _tsv(info_fields, info_rows))
    return path


def _adapter(path: Path, **kwargs) -> Sec13FBulkAdapter:
    return Sec13FBulkAdapter(
        path,
        target_cusips=("733174700", "30040P103", "67103X102"),
        issuer_bindings={
            "733174700": "ISSUER_SEC_CIK_0000763901",
            "30040P103": "ISSUER_SEC_CIK_0001559865",
            "67103X102": "ISSUER_SEC_CIK_0001030469",
        },
        **kwargs,
    )


@pytest.mark.unit
def test_sec13f_archive_is_frozen_and_provider_metric_stays_separate(tmp_path):
    path = _archive(tmp_path / "fixture.zip")
    adapter = _adapter(path)
    result = ingest(adapter)
    assert result.input_count == result.retained_count == 1
    row = result.observations[0]
    assert row.issuer_id == "ISSUER_SEC_CIK_0000763901"
    assert row.security_id == "CUSIP:733174700"
    assert row.shares == 100
    assert row.market_value == 2500
    assert row.extra["percent_13f_reportable_value"] == 25.0
    assert row.extra["provider_percent_total_assets"] is None
    assert row.extra["provider_metric_equivalence"] == "OPEN"
    manifest = result.manifest
    assert manifest.byte_status == "FROZEN"
    assert manifest.raw_bytes_size == path.stat().st_size
    assert manifest.raw_bytes_sha256 is not None and len(manifest.raw_bytes_sha256) == 64
    audit = adapter.audit()
    assert {item.path for item in audit.member_digests} == {
        "SUBMISSION.tsv",
        "COVERPAGE.tsv",
        "SUMMARYPAGE.tsv",
        "INFOTABLE.tsv",
    }
    assert all(len(item.sha256) == 64 for item in audit.member_digests)


@pytest.mark.unit
def test_sec13f_duplicate_source_primary_key_fails_closed(tmp_path):
    path = _archive(tmp_path / "duplicate.zip", duplicate_info_key=True)
    adapter = _adapter(path)
    with pytest.raises(Sec13FError, match="duplicate key"):
        tuple(adapter.iter_records())


@pytest.mark.unit
def test_vanguard_reporting_ciks_remain_distinct_legal_holders(tmp_path):
    first = _archive(tmp_path / "v1.zip", cik="2100121", manager="Vanguard Portfolio Management LLC")
    second = _archive(
        tmp_path / "v2.zip",
        accession="0000000002-26-000002",
        cik="2100119",
        manager="Vanguard Capital Management",
    )
    first_investor = _adapter(first).iter_investors()[0]
    second_investor = _adapter(second).iter_investors()[0]
    assert first_investor.investor_id != second_investor.investor_id
    assert first_investor.binding_basis == second_investor.binding_basis == "STABLE_ID"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cusip", "issuer_id"),
    [
        ("733174700", "ISSUER_SEC_CIK_0000763901"),
        ("30040P103", "ISSUER_SEC_CIK_0001559865"),
        ("67103X102", "ISSUER_SEC_CIK_0001030469"),
    ],
)
def test_bpop_evtc_ofg_bind_only_from_authoritative_cusip_registry(tmp_path, cusip, issuer_id):
    path = _archive(tmp_path / f"{cusip}.zip", cusip=cusip)
    row = ingest(_adapter(path)).observations[0]
    assert row.issuer_id == issuer_id
    assert row.identity_status == "PASS"


@pytest.mark.unit
def test_restatement_requires_unique_structural_prior_target(tmp_path):
    original = _archive(tmp_path / "original.zip", filing_date="15-MAY-2026")
    amended = _archive(
        tmp_path / "amended.zip",
        accession="0000000001-26-000002",
        filing_date="20-MAY-2026",
        is_amendment="Y",
        amendment_type="RESTATEMENT",
        shares="110",
        value="2700",
    )
    old = ingest(_adapter(original)).observations[0]
    new = ingest(_adapter(amended)).observations[0]
    assert new.amendment_status == "UNKNOWN"
    adjudicated = adjudicate_sec13f_restatements((old, new))
    assert adjudicated.issues == ()
    updated = next(row for row in adjudicated.observations if row.observation_id == new.observation_id)
    assert updated.amendment_status == "AMENDED_RESTATEMENT"
    assert updated.supersedes_observation_id == old.observation_id
    supersession = apply_supersession(adjudicated.observations)
    assert len(supersession.active) == 1
    assert len(supersession.superseded) == 1
    assert supersession.superseded[0].amendment_status == "SUPERSEDED"


@pytest.mark.unit
def test_restatement_tie_remains_unresolved(tmp_path):
    old1 = ingest(_adapter(_archive(tmp_path / "old1.zip", accession="a-1"))).observations[0]
    old2 = ingest(_adapter(_archive(tmp_path / "old2.zip", accession="a-2"))).observations[0]
    new = ingest(
        _adapter(
            _archive(
                tmp_path / "new.zip",
                accession="a-3",
                filing_date="20-MAY-2026",
                is_amendment="Y",
                amendment_type="RESTATEMENT",
            )
        )
    ).observations[0]
    adjudicated = adjudicate_sec13f_restatements((old1, old2, new))
    assert len(adjudicated.issues) == 1
    unresolved = next(row for row in adjudicated.observations if row.observation_id == new.observation_id)
    assert unresolved.amendment_status == "UNKNOWN"
    assert unresolved.supersedes_observation_id is None


@pytest.mark.unit
def test_additive_amendment_does_not_supersede_prior_row(tmp_path):
    path = _archive(
        tmp_path / "addition.zip",
        is_amendment="Y",
        amendment_type="NEW HOLDINGS",
    )
    row = ingest(_adapter(path)).observations[0]
    assert row.amendment_status == "AMENDED_ADDITION"
    assert row.supersedes_observation_id is None


@pytest.mark.unit
def test_materialized_entity_adapter_matches_exact_cusip_only(tmp_path):
    target = tmp_path / "data/staging/processed/capital_control"
    target.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "security_cusip": "733174700",
                "issuer_id": "ISSUER_SEC_CIK_0000763901",
                "holder_id": "INV_CIK_0000010290",
                "observation_id": "HOLD_A",
            },
            {
                "security_cusip": "30040P103",
                "issuer_id": "ISSUER_SEC_CIK_0001559865",
                "holder_id": "INV_CIK_0000010291",
                "observation_id": "HOLD_B",
            },
        ]
    ).to_csv(target / "sec13f_holdings.csv", index=False)
    adapter = Sec13FCapitalControlAdapter(root=tmp_path)
    query = EntityQuery(identifiers=(EntityIdentifier(kind="cusip", value="733174700"),))
    frame = adapter.fetch(query)
    assert list(frame["observation_id"]) == ["HOLD_A"]
    assert frame.iloc[0]["identity_match_state"] == "STABLE_SECURITY_ID"


@pytest.mark.unit
def test_golden_case_registry_preserves_negative_identity_and_raw_normalized_fixtures():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "registries/capital_control_golden_cases.json").read_text(encoding="utf-8"))
    by_ticker = {item["ticker"]: item for item in data["issuers"]}
    assert by_ticker["BPOP"]["cusip"] == "733174700"
    assert len(by_ticker["BPOP"]["required_periods"]) == 8
    assert "EVRI" in by_ticker["EVTC"]["forbidden_name_only_merge"]
    assert by_ticker["OFG"]["raw_address_fixture"] == "254 MU?OZ RIVERA AVENUE"
    assert by_ticker["OFG"]["normalized_address_fixture"] == "254 Muñoz Rivera Avenue"
