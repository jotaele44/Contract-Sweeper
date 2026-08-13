from moneysweep.government_changes import evaluate_event


def sample(**updates):
    row = {
        "change_event_id": "EVT_1",
        "affected_entity_id": "GOV_TEST01",
        "event_type": "TRANSFER_OF_CONTRACTS",
        "effective_date": "2026-08-13",
        "status": "FUNCTIONS_PARTIALLY_TRANSFERRED",
        "source_provenance": [{"source_id": "SRC_1", "evidence_type": "ENACTED_LAW_OR_CONSTITUTION"}],
        "confidence": 1.0,
        "certification_state": "PASS",
        "predecessor_entities": [],
        "successor_entities": [],
        "contracts_transferred": ["C1"],
    }
    row.update(updates)
    return row


def test_material_transfer_requires_recompute_alert():
    result = evaluate_event(sample())
    assert result.severity == "S3"
    assert result.alert is True
    assert "CONTRACT_GRAPH" in result.invalidation_scopes


def test_announcement_without_effective_date_is_not_binding():
    result = evaluate_event(sample(effective_date=None, announcement_date="2026-08-13"))
    assert result.binding is False
    assert result.timeline_state == "FUNCTIONS_PARTIALLY_TRANSFERRED"
