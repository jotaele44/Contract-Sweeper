
import pandas as pd
import pytest

from scripts import build_campaign_finance_entities as mod


@pytest.mark.unit
def test_builds_candidates_committees_and_recipient_resolution(tmp_path):
    processed = tmp_path / "data" / "staging" / "processed"
    processed.mkdir(parents=True)
    pd.DataFrame([
        {
            "cycle": "2024", "contributor_name": "DONOR X", "contribution_receipt_amount": "100",
            "contribution_receipt_date": "2024-01-01", "committee_id": "C1",
            "committee_name": "FRIENDS OF X", "candidate_id": "H1", "candidate_name": "CANDIDATE X",
            "is_individual": "False",
        }
    ]).to_csv(processed / "pr_fec_contributions.csv", index=False)
    pd.DataFrame([
        {"committee_id": "C1", "name": "FRIENDS OF X", "committee_type": "H", "state": "PR"}
    ]).to_csv(processed / "pr_fec_committees.csv", index=False)
    pd.DataFrame([
        {"cycle": "2024", "committee_id": "C1", "committee_name": "FRIENDS OF X",
         "recipient_name": "CANDIDATE X", "disbursement_amount": "50", "disbursement_date": "2024-02-01"}
    ]).to_csv(processed / "pr_fec_disbursements.csv", index=False)
    pd.DataFrame(columns=["committee_id", "candidate_id", "expenditure_amount"]).to_csv(
        processed / "pr_fec_independent_expenditures.csv", index=False
    )

    result = mod.run(root=tmp_path)
    assert result["candidates"] == 1
    assert result["committees"] == 1
    assert result["recipients"] == 1
    assert result["resolved_recipients"] == 1
    rec = pd.read_csv(processed / "pr_campaign_finance_recipient_resolution.csv")
    assert rec.iloc[0]["resolved_entity_type"] == "candidate"
    assert rec.iloc[0]["match_method"] == "exact_normalized_name"
