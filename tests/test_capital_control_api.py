from __future__ import annotations

import pandas as pd

from server.backend import capital_control as api


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observation_id": "OLD",
                "issuer_id": "A",
                "issuer_name": "Issuer A",
                "security_id": "A-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One",
                "investor_family_id": "F1",
                "ultimate_parent_id": "P1",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-01",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-OLD",
                "percent_issuer": "1",
                "amendment_sequence": "0",
            },
            {
                "observation_id": "NEW",
                "issuer_id": "A",
                "issuer_name": "Issuer A",
                "security_id": "A-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One",
                "investor_family_id": "F1",
                "ultimate_parent_id": "P1",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-02",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-NEW",
                "percent_issuer": "2",
                "amendment_sequence": "1",
            },
            {
                "observation_id": "B1",
                "issuer_id": "B",
                "issuer_name": "Issuer B",
                "security_id": "B-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One",
                "investor_family_id": "F1",
                "ultimate_parent_id": "P1",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-01",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-B1",
                "percent_issuer": "3",
                "amendment_sequence": "0",
            },
        ]
    ).fillna("")


def test_effective_api_frame_supersedes_old_position():
    effective, ties = api._effective(frame())
    assert ties == 0
    assert set(effective["observation_id"]) == {"NEW", "B1"}


def test_compare_endpoint_computes_full_set_diagnostics(monkeypatch):
    monkeypatch.setattr(api, "_data", frame)
    result = api.compare_issuers("A", "B", "legal_holder")
    assert result["intersection"] == ["H1"]
    assert result["aOnly"] == []
    assert result["bOnly"] == []
    assert result["union"] == ["H1"]
    assert result["symmetricDifference"] == []
    assert result["counts"]["intersection"] == 1


def test_holdings_endpoint_preserves_raw_holder_name(monkeypatch):
    monkeypatch.setattr(api, "_data", frame)
    rows = api.capital_control_holdings(issuer_id="A")
    assert len(rows) == 1
    assert rows[0]["observationId"] == "NEW"
    assert rows[0]["holderReportedNameRaw"] == "Holder One"
    assert rows[0]["percentIssuer"] == 2.0
