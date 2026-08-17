from pathlib import Path

from scripts.ingest_centinelas_signals import _project_fiscal_assertions


def test_project_fiscal_assertion_preserves_candidate_set_without_identity_promotion(tmp_path: Path):
    drop = tmp_path / "los-rosales.json"
    payload = {
        "item_id": "los-rosales-observed-banner",
        "project_lead": {
            "lead_id": "prjlead_fixture",
            "origin_item_id": "los-rosales-observed-banner",
            "source_title_raw": "RESIDENCIAL LOS ROSALES",
            "identity_effect": "NONE",
        },
    }
    awards = [
        {
            "award_id": "CS-CENT-los-rosales-observed-banner",
            "centinelas_item_id": "los-rosales-observed-banner",
            "amount": 56432.84,
            "location": {"municipality_name": "Yabucoa"},
        }
    ]
    rows = _project_fiscal_assertions([(drop, payload)], awards)
    assert len(rows) == 1
    row = rows[0]
    assert row["lead_id"] == "prjlead_fixture"
    assert row["candidate_count"] == 1
    assert row["unresolved_cardinality"] == 1
    assert row["candidates"] == awards
    assert row["binding_state"] == "UNRESOLVED"
    assert row["identity_effect"] == "NONE"
    assert row["independent_binding_evidence"] == []
