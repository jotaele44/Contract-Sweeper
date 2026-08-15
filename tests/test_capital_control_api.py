from __future__ import annotations

import pandas as pd

from server.backend import main as api


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observation_id": "OLD",
                "issuer_id": "A",
                "issuer_name": "Issuer A",
                "security_id": "A-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One RAW",
                "investor_family_id": "F1",
                "investor_family_name": "Family One",
                "ultimate_parent_id": "P1",
                "ultimate_parent_name": "Parent One",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-01",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-OLD",
                "source_url": "https://example.test/old",
                "retrieval_utc": "2026-08-15T10:00:00Z",
                "percent_issuer": "1",
                "market_value": "100",
                "amendment_sequence": "0",
            },
            {
                "observation_id": "NEW",
                "issuer_id": "A",
                "issuer_name": "Issuer A",
                "security_id": "A-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One RAW",
                "investor_family_id": "F1",
                "investor_family_name": "Family One",
                "ultimate_parent_id": "P1",
                "ultimate_parent_name": "Parent One",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-02",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-NEW",
                "source_url": "https://example.test/new",
                "retrieval_utc": "2026-08-15T10:01:00Z",
                "percent_issuer": "2",
                "market_value": "200",
                "amendment_sequence": "1",
            },
            {
                "observation_id": "B1",
                "issuer_id": "B",
                "issuer_name": "Issuer B",
                "security_id": "B-COMMON",
                "holder_legal_entity_id": "H1",
                "holder_reported_name_raw": "Holder One RAW",
                "investor_family_id": "F1",
                "investor_family_name": "Family One",
                "ultimate_parent_id": "P1",
                "ultimate_parent_name": "Parent One",
                "as_of_date": "2026-06-30",
                "report_date": "2026-08-01",
                "position_class": "FUND",
                "relation_type": "FUND_HOLDING",
                "identity_status": "CERTIFIED",
                "source_id": "SEC",
                "source_document_id": "DOC-B1",
                "source_url": "https://example.test/b1",
                "retrieval_utc": "2026-08-15T10:02:00Z",
                "percent_issuer": "3",
                "market_value": "300",
                "amendment_sequence": "0",
            },
        ]
    ).fillna("")


def test_edges_capital_view_supersedes_and_preserves_raw_holder(monkeypatch):
    monkeypatch.setattr(api, "_capital_data", frame)
    rows = api.edges(view="capital_control", issuer_id="A")
    assert len(rows) == 1
    assert rows[0]["observationId"] == "NEW"
    assert rows[0]["holderReportedNameRaw"] == "Holder One RAW"
    assert rows[0]["investorFamilyId"] == "F1"
    assert rows[0]["ultimateParentId"] == "P1"
    assert rows[0]["percentIssuer"] == 2.0
    assert rows[0]["marketValue"] == 200.0
    assert rows[0]["sourceDocumentId"] == "DOC-NEW"


def test_edges_capital_view_filters_without_name_identity_promotion(monkeypatch):
    monkeypatch.setattr(api, "_capital_data", frame)
    rows = api.edges(view="capital_control", q="Family One")
    assert {row["observationId"] for row in rows} == {"NEW", "B1"}
    assert {row["holderLegalEntityId"] for row in rows} == {"H1"}


def test_regular_edges_behavior_remains_available():
    rows = api.edges()
    assert isinstance(rows, list)
    if rows:
        assert "edgeId" in rows[0]
        assert "edgeType" in rows[0]
