import json

from moneysweep.government_change_materialization import materialize_validated_source_update


def test_unconfigured_source_is_not_guessed(tmp_path):
    config = tmp_path / "config" / "government_organization_change_monitor.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": "government_organization_change_monitor_v1",
                "detector_version": "government_change_phrase_scan_v1",
                "scope_claim": "BOUNDED_NOT_EXHAUSTIVE",
                "bindings": [],
            }
        ),
        encoding="utf-8",
    )
    result = materialize_validated_source_update(
        source_id="unknown_source",
        run_id="RUN_1",
        output_hashes={},
        root=tmp_path,
    )
    assert result["status"] == "NOT_CONFIGURED"
    assert result["candidates"] == 0
