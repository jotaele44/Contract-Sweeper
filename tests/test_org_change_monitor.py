import pytest

from moneysweep.government_change_detection import candidate_types, detect_candidates
from moneysweep.government_changes import (
    ChangeEventError,
    evaluate_event,
    evaluate_events,
)


def sample(**updates):
    row = {
        "change_event_id": "EVT_1",
        "affected_entity_id": "GOV_TEST01",
        "event_type": "TRANSFER_OF_CONTRACTS",
        "effective_date": "2026-08-13",
        "status": "FUNCTIONS_PARTIALLY_TRANSFERRED",
        "source_provenance": [
            {
                "source_assertion_id": "ASSERT_1",
                "evidence_type": "ENACTED_LAW_OR_CONSTITUTION",
            }
        ],
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
    assert result.binding is True
    assert "CONTRACT_GRAPH" in result.invalidation_scopes


def test_announcement_without_effective_date_is_not_binding():
    result = evaluate_event(sample(effective_date=None, announcement_date="2026-08-13"))
    assert result.binding is False
    assert result.timeline_state == "FUNCTIONS_PARTIALLY_TRANSFERRED"


def test_proposal_only_cannot_establish_effective_dissolution():
    with pytest.raises(ChangeEventError):
        evaluate_event(
            sample(
                event_type="DISSOLUTION",
                status="DISSOLVED",
                source_provenance=[
                    {
                        "source_assertion_id": "ASSERT_BILL",
                        "evidence_type": "LEGISLATIVE_PROPOSAL",
                    }
                ],
            )
        )


def test_rename_does_not_establish_successor_identity():
    with pytest.raises(ChangeEventError):
        evaluate_event(
            sample(
                event_type="RENAMING",
                predecessor_entities=["GOV_TEST01"],
                successor_entities=["GOV_TEST02"],
            )
        )


def test_duplicate_change_event_ids_fail_closed():
    with pytest.raises(ChangeEventError):
        evaluate_events([sample(), sample()])


def test_bounded_detection_flags_english_and_spanish_without_promoting_identity():
    rows = detect_candidates(
        text="The agency will be dissolved. Luego habrá transferencia de funciones.",
        source_assertion_id="ASSERT_2",
        affected_entity_id="GOV_TEST01",
    )
    assert {"DISSOLUTION", "TRANSFER_OF_FUNCTIONS"} <= candidate_types(rows)
    assert rows
    assert all(row["certification_state"] == "CANDIDATE_NOT_IDENTITY" for row in rows)
    assert all(row["scope_claim"] == "BOUNDED_NOT_EXHAUSTIVE" for row in rows)


def test_detection_is_deterministic_and_preserves_raw_match():
    kwargs = {
        "text": "Privatization is proposed.",
        "source_assertion_id": "ASSERT_3",
        "affected_entity_id": "GOV_TEST01",
    }
    first = detect_candidates(**kwargs)
    second = detect_candidates(**kwargs)
    assert first == second
    assert first[0]["raw_match"] == "Privatization"
