import pandas as pd

from moneysweep.political_finance.flow_graph import (
    build_political_finance_graph,
    classify_committee,
    find_flow_paths,
    normalize_name,
)


def test_classify_committee_types():
    assert classify_committee({"committee_type": "O"}) == "SUPER_PAC"
    assert classify_committee({"committee_type": "X"}) == "PARTY_COMMITTEE"
    assert classify_committee({"committee_type_full": "Joint fundraising committee"}) == "JOINT_FUNDRAISING_COMMITTEE"
    assert classify_committee({"organization_type": "527 organization"}) == "POLITICAL_527"


def test_unique_recipient_resolution_and_provenance():
    committees = pd.DataFrame([{"committee_id": "C1", "name": "Committee One", "committee_type": "O"}])
    disbursements = pd.DataFrame([{
        "committee_id": "C1", "committee_name": "Committee One",
        "recipient_name": "Acme, Inc.", "disbursement_amount": "2500",
        "disbursement_date": "2026-01-15", "transaction_id": "TX1",
    }])
    awards = pd.DataFrame([{"awardee_id": "A1", "awardee_name": "ACME INC"}])
    graph = build_political_finance_graph(
        committees=committees,
        disbursements=disbursements,
        entity_frames=[("awards", awards)],
    )
    assert graph["resolutions"].iloc[0]["resolved_entity_id"] == "awards:A1"
    edge = graph["edges"].iloc[0]
    assert edge["edge_type"] == "DISBURSED_TO"
    assert edge["target_entity_id"] == "awards:A1"
    assert edge["provenance"] == "fec_schedule_b:TX1"


def test_ambiguous_recipient_requires_review():
    disbursements = pd.DataFrame([{"committee_id": "C1", "recipient_name": "ACME", "transaction_id": "T1"}])
    entities = pd.DataFrame([
        {"entity_id": "1", "canonical_name": "ACME"},
        {"entity_id": "2", "canonical_name": "ACME"},
    ])
    graph = build_political_finance_graph(disbursements=disbursements, entity_frames=[("resolved", entities)])
    row = graph["resolutions"].iloc[0]
    assert bool(row["review_required"])
    assert row["resolution_method"] == "unresolved"


def test_dedup_and_multihop_paths():
    contributions = pd.DataFrame([{
        "contributor_name": "Donor A", "committee_id": "C1",
        "committee_name": "Committee", "amount": "100", "transaction_id": "R1",
    }])
    disbursements = pd.DataFrame([{
        "committee_id": "C1", "committee_name": "Committee",
        "recipient_name": "Vendor A", "disbursement_amount": "80", "transaction_id": "D1",
    }])
    graph = build_political_finance_graph(contributions=contributions, disbursements=disbursements)
    assert not graph["edges"]["edge_id"].duplicated().any()
    donor = graph["entities"].loc[graph["entities"]["entity_type"] == "DONOR", "entity_id"].iloc[0]
    paths = find_flow_paths(graph["edges"], donor, max_hops=4)
    assert paths["hop_count"].max() == 2
    assert normalize_name("Acme, Inc.") == "ACME INC"
