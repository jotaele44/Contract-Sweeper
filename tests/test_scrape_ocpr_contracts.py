"""Tests for the OCPR contract-registry scraper
(scripts.scrape_ocpr_contracts).

Covers the pure record-mapping transforms and the paginate/run chain with the
HTTP layer mocked out — no live network calls.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest
import requests

from scripts.ingest_ocpr_contracts import OUTPUT_COLUMNS
from scripts.scrape_ocpr_contracts import (
    _extract_document_url,
    _fetch_page,
    _normalize_row,
    _parse_dotnet_date,
    fetch_all_records,
    _run,
)

# ---------------------------------------------------------------------------
# Unit: pure transforms
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_dotnet_date_extracts_iso_date():
    assert _parse_dotnet_date("/Date(1260507600000)/") == "2009-12-11"
    assert _parse_dotnet_date(None) == ""
    assert _parse_dotnet_date("") == ""
    assert _parse_dotnet_date("not a date") == ""


@pytest.mark.unit
def test_extract_document_url_resolves_when_present():
    record = {"DocumentWithoutSocialSecurityId": "abc-123"}
    assert (
        _extract_document_url(record)
        == "https://consultacontratos.ocpr.gov.pr/contract/downloaddocument?code=abc-123"
    )


@pytest.mark.unit
def test_extract_document_url_blank_when_absent():
    assert _extract_document_url({}) == ""
    assert _extract_document_url({"DocumentWithoutSocialSecurityId": None}) == ""


@pytest.mark.unit
def test_normalize_row_maps_api_record_to_canonical_schema():
    record = {
        "ContractNumber": "010-00-0280",
        "EntityId": 4027,
        "EntityName": "Municipio de Fajardo",
        "AmountToPay": 535000.0,
        "AmountToReceive": None,
        "EffectiveDateFrom": "/Date(1260507600000)/",
        "EffectiveDateTo": "/Date(1260507600000)/",
        "Service": "COMPRA DE INMUEBLES",
        "ServiceGroup": "COMPRA, VENTA, ALQUILER Y/O DESARROLLO DE INMUEBLES",
        "CancellationDate": None,
        "DocumentWithoutSocialSecurityId": "0ba3f165-ddb6-45d8-b313-184fb6b78534",
        "Contractors": [{"Name": "WESTERNBANK PUERTO RICO", "SocialSecurity": None}],
    }
    row = _normalize_row(record)
    assert list(row.keys()) == OUTPUT_COLUMNS
    assert row["contract_number"] == "010-00-0280"
    assert row["contractor_name"] == "WESTERNBANK PUERTO RICO"
    assert row["contractor_id"] == ""
    assert row["agency"] == "Municipio de Fajardo"
    assert row["contract_amount"] == "535000.0"
    assert row["start_date"] == "2009-12-11"
    assert row["end_date"] == "2009-12-11"
    assert row["service_description"] == "COMPRA DE INMUEBLES"
    assert row["status"] == ""
    assert (
        row["document_url"]
        == "https://consultacontratos.ocpr.gov.pr/contract/downloaddocument?code=0ba3f165-ddb6-45d8-b313-184fb6b78534"
    )


@pytest.mark.unit
def test_normalize_row_joins_multiple_contractors():
    record = {
        "ContractNumber": "X-1",
        "Contractors": [{"Name": "ACME CORP"}, {"Name": "BETA LLC"}],
    }
    row = _normalize_row(record)
    assert row["contractor_name"] == "ACME CORP; BETA LLC"


@pytest.mark.unit
def test_normalize_row_marks_cancelled_status():
    record = {"ContractNumber": "X-2", "CancellationDate": "/Date(1600000000000)/"}
    row = _normalize_row(record)
    assert row["status"] == "Cancelado"


@pytest.mark.unit
def test_normalize_row_falls_back_to_receive_amount():
    record = {"ContractNumber": "X-3", "AmountToPay": None, "AmountToReceive": 42.0}
    row = _normalize_row(record)
    assert row["contract_amount"] == "42.0"


@pytest.mark.unit
def test_normalize_row_agency_falls_back_to_entity_id_when_name_missing():
    record = {"ContractNumber": "X-4", "EntityId": 999, "EntityName": None}
    row = _normalize_row(record)
    assert row["agency"] == "999"


# ---------------------------------------------------------------------------
# Unit: _fetch_page HTTP status / response handling (session.post mocked)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", json_ok=True):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self._json_ok = json_ok

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if not self._json_ok:
            raise ValueError("Expecting value")
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def post(self, *a, **k):
        self.calls += 1
        return self._responses[self.calls - 1]


@pytest.mark.unit
def test_fetch_page_retries_after_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("scripts.scrape_ocpr_contracts.time.sleep", lambda s: None)
    session = _FakeSession(
        [
            _FakeResponse(status_code=429),
            _FakeResponse(status_code=200, payload={"recordsTotal": 1, "data": []}),
        ]
    )
    result = _fetch_page(session, token="tok", start=0, length=100, logger=_NullLogger())
    assert result == {"recordsTotal": 1, "data": []}
    assert session.calls == 2


@pytest.mark.unit
def test_fetch_page_terminal_4xx_does_not_retry(monkeypatch):
    monkeypatch.setattr("scripts.scrape_ocpr_contracts.time.sleep", lambda s: None)
    session = _FakeSession([_FakeResponse(status_code=400, text="bad request")])
    result = _fetch_page(session, token="tok", start=0, length=100, logger=_NullLogger())
    assert result is None
    assert session.calls == 1


@pytest.mark.unit
def test_fetch_page_retries_on_non_json_200_then_gives_up(monkeypatch):
    """A redirect-turned-200 (e.g. bounced back to the HTML search page) must
    not crash the scrape — it should retry like any other transient failure
    and eventually surface as a clean page failure."""
    monkeypatch.setattr("scripts.scrape_ocpr_contracts.time.sleep", lambda s: None)
    session = _FakeSession([_FakeResponse(status_code=200, json_ok=False)] * 3)
    result = _fetch_page(session, token="tok", start=0, length=100, logger=_NullLogger())
    assert result is None
    assert session.calls == 3  # exhausted RETRY_POLICY.max_attempts, no crash


# ---------------------------------------------------------------------------
# Integration: pagination + full run chain (HTTP mocked)
# ---------------------------------------------------------------------------


def _fake_record(num):
    return {
        "ContractNumber": f"C-{num}",
        "EntityId": num,
        "EntityName": f"Agency {num}",
        "AmountToPay": 100.0,
        "EffectiveDateFrom": "/Date(1260507600000)/",
        "EffectiveDateTo": "/Date(1260507600000)/",
        "Contractors": [{"Name": f"Contractor {num}"}],
    }


@pytest.mark.integration
def test_fetch_all_records_paginates_until_records_total(monkeypatch):
    pages = [
        {"recordsTotal": 25, "data": [_fake_record(i) for i in range(10)]},
        {"recordsTotal": 25, "data": [_fake_record(i) for i in range(10, 20)]},
        {"recordsTotal": 25, "data": [_fake_record(i) for i in range(20, 25)]},
    ]
    calls = []

    def fake_fetch_page(session, token, start, length, logger):
        calls.append(start)
        return pages[len(calls) - 1]

    monkeypatch.setattr("scripts.scrape_ocpr_contracts._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(
        session=None, token="tok", logger=_NullLogger(), page_length=10
    )
    assert len(records) == 25
    assert calls == [0, 10, 20]
    assert truncated is False


@pytest.mark.integration
def test_fetch_all_records_handles_null_records_total_without_crashing(monkeypatch):
    def fake_fetch_page(session, token, start, length, logger):
        return {"recordsTotal": None, "data": []}

    monkeypatch.setattr("scripts.scrape_ocpr_contracts._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, token="tok", logger=_NullLogger())
    assert records == []
    assert truncated is False


@pytest.mark.integration
def test_fetch_all_records_respects_max_pages(monkeypatch):
    def fake_fetch_page(session, token, start, length, logger):
        return {"recordsTotal": 100000, "data": [_fake_record(start)]}

    monkeypatch.setattr("scripts.scrape_ocpr_contracts._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(
        session=None, token="tok", logger=_NullLogger(), page_length=1, max_pages=2
    )
    assert len(records) == 2
    assert truncated is False


@pytest.mark.integration
def test_fetch_all_records_flags_truncated_on_failed_page(monkeypatch):
    def fake_fetch_page(session, token, start, length, logger):
        return None

    monkeypatch.setattr("scripts.scrape_ocpr_contracts._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, token="tok", logger=_NullLogger())
    assert records == []
    assert truncated is True


@pytest.mark.integration
def test_run_materializes_processed_csv_from_scraped_records(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts._session_and_token",
        lambda logger: (requests.Session(), "tok"),
    )
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts.fetch_all_records",
        lambda session, token, logger, page_length=100, max_pages=None: (
            [_fake_record(1), _fake_record(2)],
            False,
        ),
    )
    result = _run(root=tmp_path, force=True)
    assert result["rows"] == 2
    assert result["errors"] == []

    out_path = tmp_path / "data" / "staging" / "processed" / "pr_ocpr_contracts.csv"
    assert out_path.exists()
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
    assert list(rows[0].keys()) == OUTPUT_COLUMNS
    assert {r["contract_number"] for r in rows} == {"C-1", "C-2"}


@pytest.mark.integration
def test_run_reports_error_when_scrape_was_truncated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts._session_and_token",
        lambda logger: (requests.Session(), "tok"),
    )
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts.fetch_all_records",
        lambda session, token, logger, page_length=100, max_pages=None: ([_fake_record(1)], True),
    )
    result = _run(root=tmp_path, force=True)
    assert result["rows"] == 1
    assert result["errors"], "a truncated scrape must surface an error even though rows > 0"


@pytest.mark.integration
def test_run_with_no_records_writes_empty_header_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts._session_and_token",
        lambda logger: (requests.Session(), "tok"),
    )
    monkeypatch.setattr(
        "scripts.scrape_ocpr_contracts.fetch_all_records",
        lambda session, token, logger, page_length=100, max_pages=None: ([], False),
    )
    result = _run(root=tmp_path, force=True)
    assert result["rows"] == 0
    out_path = tmp_path / "data" / "staging" / "processed" / "pr_ocpr_contracts.csv"
    assert out_path.exists()
    assert list(csv.DictReader(out_path.open(encoding="utf-8"))) == []


@pytest.mark.integration
def test_run_skips_scrape_when_cached_output_exists(tmp_path: Path, monkeypatch):
    out_path = tmp_path / "data" / "staging" / "processed" / "pr_ocpr_contracts.csv"
    out_path.parent.mkdir(parents=True)
    pd.DataFrame([_normalize_row(_fake_record(1))]).to_csv(out_path, index=False)

    def _boom(*a, **k):
        raise AssertionError("_session_and_token should not be called when cached")

    monkeypatch.setattr("scripts.scrape_ocpr_contracts._session_and_token", _boom)
    result = _run(root=tmp_path, force=False)
    assert result["rows"] == 1


class _NullLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass
