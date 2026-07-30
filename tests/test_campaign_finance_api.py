import pandas as pd
import pytest

pytest.importorskip("fastapi")

from server.backend import campaign_finance as api


@pytest.mark.unit
def test_summary_and_contributions_are_graceful_without_files(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PROCESSED", tmp_path)
    api._CACHE.clear()
    summary = api.campaign_finance_summary()
    assert summary["totalContributionRows"] == 0
    page = api.campaign_finance_contributions(source="all", limit=100, offset=0)
    assert page == {"rows": [], "total": 0, "limit": 100, "offset": 0}


@pytest.mark.unit
def test_contribution_endpoint_unifies_fec_and_oce(tmp_path, monkeypatch):
    pd.DataFrame(
        [
            {
                "contributor_name": "DONOR A",
                "contribution_receipt_amount": "100",
                "contribution_receipt_date": "2024-01-01",
                "committee_name": "PAC A",
                "cycle": "2024",
                "is_individual": "True",
                "committee_id": "C1",
                "candidate_id": "",
            }
        ]
    ).to_csv(tmp_path / "pr_fec_contributions.csv", index=False)
    pd.DataFrame(
        [
            {
                "donor_name": "DONOR B",
                "amount": "200",
                "contribution_date": "2024-02-01",
                "candidate_or_committee": "COMITE B",
                "party": "PIP",
                "cycle": "2024",
            }
        ]
    ).to_csv(tmp_path / "pr_oce_donations.csv", index=False)
    monkeypatch.setattr(api, "PROCESSED", tmp_path)
    api._CACHE.clear()
    page = api.campaign_finance_contributions(source="all", limit=100, offset=0)
    assert page["total"] == 2
    assert {row["source"] for row in page["rows"]} == {"fec", "oce"}
    assert sum(row["amount"] for row in page["rows"]) == 300
