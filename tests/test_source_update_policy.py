"""Policy resolution + schema/consistency tests for the source update controller."""

from __future__ import annotations

import pytest

from moneysweep.update_controller.models import TriggerType
from moneysweep.update_controller.policy import (
    build_effective_policies,
    canonical_source_ids,
    load_schema,
    policy_hash,
    validate_effective_policy,
    validate_policy,
)

pytestmark = pytest.mark.unit

POLICIES = build_effective_policies()
SCHEMA = load_schema()
CANONICAL = set(canonical_source_ids())
REPORT = validate_policy()


def test_exactly_one_effective_policy_per_source():
    assert set(POLICIES) == CANONICAL
    assert len(POLICIES) == len(CANONICAL) == 143


def test_policy_validation_has_no_errors():
    assert REPORT["ok"], REPORT["errors"]
    assert REPORT["policy_coverage"] == "143/143"


def test_no_orphan_policy_overrides():
    assert not any("orphan policy" in e for e in REPORT["errors"])


def test_every_trigger_type_is_recognized():
    allowed = {t.value for t in TriggerType}
    for pol in POLICIES.values():
        assert pol.trigger_type in allowed
    dist = REPORT["trigger_distribution"]
    assert sum(dist.values()) == 143
    # all six trigger types are represented
    assert all(dist[t.value] >= 1 for t in TriggerType)


def test_schema_validates_every_effective_policy():
    for sid, pol in POLICIES.items():
        errs = validate_effective_policy(pol.to_dict(), SCHEMA)
        assert errs == [], f"{sid}: {errs}"


def test_disabled_policies_are_not_enabled():
    for pol in POLICIES.values():
        if pol.trigger_type == "disabled":
            assert pol.enabled is False
            assert pol.notes, f"{pol.source_id}: disabled policy needs notes"


def test_scheduled_policies_have_cadence():
    for pol in POLICIES.values():
        if pol.trigger_type == "schedule":
            assert pol.cadence, f"{pol.source_id}: schedule requires cadence"


def test_dependency_policies_have_parents():
    for pol in POLICIES.values():
        if pol.trigger_type == "dependency":
            assert pol.depends_on, f"{pol.source_id}: dependency requires parents"


def test_file_drop_policies_have_paths_patterns_and_hash():
    for pol in POLICIES.values():
        if pol.trigger_type in ("file_drop", "on_drop"):
            assert pol.watch_paths, f"{pol.source_id}: needs watch_paths"
            assert pol.filename_patterns, f"{pol.source_id}: needs filename_patterns"
            assert pol.dedupe_method == "sha256"


def test_secret_names_match_authentication():
    # sam_entities declares SAM_API_KEY; api_key sources carry their env var
    sam = POLICIES["sam_entities"]
    assert "SAM_API_KEY" in sam.required_secrets


def test_policy_hash_is_deterministic():
    again = build_effective_policies()
    assert policy_hash(POLICIES) == policy_hash(again)


def test_known_overrides_take_effect():
    assert POLICIES["ocpr_contracts"].execution_backend == "self_hosted"
    assert POLICIES["ocpr_contracts"].trigger_type == "schedule"
    assert POLICIES["centinelas_pre_official_signals"].trigger_type == "on_drop"
    assert POLICIES["prasa_contracts_master"].trigger_type == "dependency"
    assert POLICIES["prasa_contracts_master"].depends_on == ["prasa"]
    assert POLICIES["hacienda_sut_ivu"].trigger_type == "disabled"
