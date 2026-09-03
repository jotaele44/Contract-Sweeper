"""State-store tests for the source update controller."""

from __future__ import annotations

import json

import pytest

from moneysweep.update_controller.models import SourceUpdatePolicy
from moneysweep.update_controller.state import (
    append_jsonl,
    init_state,
    load_state,
    registry_changed,
    write_state,
)

pytestmark = pytest.mark.unit


def _pol(sid: str) -> SourceUpdatePolicy:
    return SourceUpdatePolicy(
        source_id=sid,
        trigger_type="schedule",
        enabled=True,
        runner=f"scripts/{sid}.py",
        freshness_sla_hours=192,
        timeout_minutes=60,
        max_retries=1,
        empty_result_policy="preserve_previous",
        cadence="weekly",
    )


def test_new_state_initializes_all_canonical_sources():
    from moneysweep.update_controller.policy import canonical_source_ids

    expected = len(canonical_source_ids())
    st = init_state()
    assert st["registry_snapshot"]["source_count"] == expected
    assert len(st["sources"]) == expected
    for row in st["sources"].values():
        assert row["last_status"] == "NEVER_RUN"


def test_atomic_state_write_leaves_no_tmp(tmp_path):
    st = {
        "schema_version": "source_update_state_v1",
        "registry_snapshot": {"source_count": 2, "source_ids_sha256": "x", "generated_at": ""},
        "sources": {"a": {"last_status": "NEVER_RUN"}},
    }
    p = tmp_path / "state.json"
    write_state(st, root=tmp_path, state_path=p)
    assert p.exists()
    assert not (tmp_path / "state.json.tmp").exists()
    reloaded = json.loads(p.read_text())
    assert reloaded["sources"]["a"]["last_status"] == "NEVER_RUN"


def test_jsonl_append(tmp_path):
    append_jsonl(tmp_path, "ledger.jsonl", {"a": 1})
    append_jsonl(tmp_path, "ledger.jsonl", {"a": 2})
    lines = (tmp_path / "ledger.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1]) == {"a": 2}


def test_registry_change_detected(monkeypatch):
    st = init_state()
    # tamper the stored hash → looks like the registry changed
    st["registry_snapshot"]["source_ids_sha256"] = "deadbeef"
    assert registry_changed(st) is True


def test_source_id_hash_is_deterministic():
    from moneysweep.update_controller.policy import registry_snapshot

    assert registry_snapshot()["source_ids_sha256"] == registry_snapshot()["source_ids_sha256"]


def test_unknown_historical_state_is_retired(tmp_path):
    policies = {"a": _pol("a")}
    seed = {
        "schema_version": "source_update_state_v1",
        "registry_snapshot": {"source_count": 1, "source_ids_sha256": "", "generated_at": ""},
        "sources": {
            "a": {"last_status": "SUCCESS_WITH_CHANGE"},
            "ghost": {"last_status": "SUCCESS_WITH_CHANGE"},
        },
    }
    p = tmp_path / "state.json"
    p.write_text(json.dumps(seed))
    loaded = load_state(root=tmp_path, state_path=p, policies=policies)
    assert loaded["sources"]["ghost"]["retired"] is True
    # canonical source preserved
    assert loaded["sources"]["a"]["last_status"] == "SUCCESS_WITH_CHANGE"
