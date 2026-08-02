import pandas as pd

from moneysweep.political_finance.completion import (
    build_affiliation_edges,
    build_transfer_edges,
    correlate_temporal_activity,
    materialization_accounting,
)


def test_authorized_and_affiliated_edges():
    candidates = pd.DataFrame(
        [{"candidate_id": "H1", "principal_campaign_committee_id": "C1", "record_id": "R1"}]
    )
    committees = pd.DataFrame(
        [{"committee_id": "C1", "affiliated_committee_id": "C2", "record_id": "R2"}]
    )
    edges = build_affiliation_edges(candidates, committees)
    assert set(edges["edge_type"]) == {"AUTHORIZED_COMMITTEE_OF", "AFFILIATED_WITH"}
    assert not edges["edge_id"].duplicated().any()
    assert edges["provenance"].str.contains(":").all()


def test_schedule_b_transfer_requires_known_committee():
    disbursements = pd.DataFrame(
        [
            {
                "committee_id": "C1",
                "recipient_committee_id": "C2",
                "transaction_id": "T1",
                "disbursement_amount": "50",
            },
            {"committee_id": "C1", "recipient_committee_id": "UNKNOWN", "transaction_id": "T2"},
        ]
    )
    edges = build_transfer_edges(disbursements, ["C1", "C2"])
    assert len(edges) == 1
    assert edges.iloc[0]["edge_type"] == "TRANSFERRED_TO"
    assert edges.iloc[0]["target_entity_id"] == "fec_committee:C2"


def test_temporal_contract_correlation_is_not_causal():
    entities = pd.DataFrame([{"entity_id": "donor_1", "canonical_name": "Acme Inc"}])
    edges = pd.DataFrame(
        [
            {
                "source_entity_id": "donor_1",
                "target_entity_id": "fec_committee:C1",
                "transaction_date": "2025-01-01",
            }
        ]
    )
    awards = pd.DataFrame(
        [{"awardee_id": "A1", "awardee_name": "ACME INC", "award_date": "2025-06-01"}]
    )
    result = correlate_temporal_activity(edges, entities, awards, pd.DataFrame())
    assert len(result) == 1
    assert result.iloc[0]["relationship_type"] == "POLITICAL_ACTIVITY_PRECEDES_AWARD"
    assert "temporal_window_days=" in result.iloc[0]["evidence"]


def test_accounted_zero_rows():
    accounting = materialization_accounting(
        {"schedule_e": pd.DataFrame()}, {"edges": pd.DataFrame([{"x": 1}])}
    )
    zero = accounting.loc[accounting["dataset"] == "schedule_e"].iloc[0]
    assert zero["status"] == "accounted_zero"
    assert accounting.loc[accounting["dataset"] == "edges", "status"].iloc[0] == "nonzero"
