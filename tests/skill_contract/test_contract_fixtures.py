"""Blueprint §10 minimum test fixtures, grounded in real repo state.

Each fixture is a scenario the packet must handle correctly. Where the scenario
is a skill *behavior*, we assert the contract that governs it (registry
stop_conditions / modes / policies); where it reduces to existing pipeline
logic, we assert that logic directly. No skill execution or network."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _skills() -> dict[str, dict]:
    reg = yaml.safe_load((ROOT / "skill-registry.yaml").read_text(encoding="utf-8"))
    return {s["skill_id"]: s for s in reg["skills"]}


def _activation() -> dict:
    return yaml.safe_load((ROOT / "activation-matrix.yaml").read_text(encoding="utf-8"))


SKILLS = _skills()


def _has(skill_id: str, field: str, needle: str) -> bool:
    return any(needle in str(x).lower() for x in SKILLS[skill_id].get(field, []))


# 1. Strict preflight with a structural defect must stop before pipeline execution.
def test_fixture_01_structural_defect_stops_execution():
    from scripts.pipeline_preflight import STRUCTURAL_STATUSES

    assert STRUCTURAL_STATUSES  # the concept exists
    assert _has("moneysweep-run-preflight", "stop_conditions", "structural")


# 2. Missing API key only must be reported as limited readiness, not structural failure.
def test_fixture_02_missing_key_is_not_structural():
    from scripts.pipeline_preflight import STRUCTURAL_STATUSES

    assert "missing_key_limited" not in STRUCTURAL_STATUSES
    assert _has("moneysweep-run-preflight", "evidence_requirements", "missing")


# 3. Manual file with unknown schema must inventory/hash and stop before promotion.
def test_fixture_03_manual_unknown_schema_stops_before_promotion():
    sid = "moneysweep-ingest-manual-source"
    assert _has(sid, "stop_conditions", "schema")
    assert _has(sid, "stop_conditions", "promotion")
    assert _has(sid, "evidence_requirements", "sha256")


# 4. Source-count narrative mismatch must use readiness truth and raise a contradiction.
def test_fixture_04_count_mismatch_uses_readiness_truth():
    from scripts.validate_skills import check_coverage_accounting

    assert check_coverage_accounting(ROOT) == []  # readiness self-reconciles
    assert _has("moneysweep-recover-source-coverage", "stop_conditions", "disagreement")


# 5. Semantic-duplicate source must be excluded from the automatable denominator.
def test_fixture_05_semantic_duplicate_excluded():
    from scripts.build_source_recovery_matrix import SEMANTIC_DUPLICATES, build_rows

    assert SEMANTIC_DUPLICATES
    rows = {r["source_id"]: r for r in build_rows()}
    for sid in SEMANTIC_DUPLICATES:
        assert rows[sid]["path_type"] == "semantic_duplicate"
        assert rows[sid]["automatable"] is False


# 6. Due-source plan with a DAG dependency: parent precedes derived source.
def test_fixture_06_dag_parent_precedes_child():
    from scripts.build_source_recovery_matrix import REQUIRED_DAG

    assert REQUIRED_DAG.get("prasa_contracts_master") == ["prasa"]
    assert _has("moneysweep-plan-source-updates", "evidence_requirements", "dag")


# 7. Centinelas signal without an official record must remain pre-official.
def test_fixture_07_centinelas_stays_preofficial():
    assert _has("moneysweep-process-centinelas-handoff", "stop_conditions", "official")


# 8. Export is test-mode only; a synthetic test package never becomes production.
def test_fixture_08_export_is_test_mode_only():
    export = SKILLS["moneysweep-build-federation-export"]
    assert export["default_mode"] == "offline_write"
    # federation.json declares no production export command, so a promotion mode
    # is NOT advertised as executable (would be a contract lie).
    assert "promotion" not in export["allowed_modes"]
    assert export["synthetic_data_policy"] == "reject_in_production"


# 9. Production export containing synthetic data must fail.
def test_fixture_09_synthetic_rejected_in_production():
    for sid, skill in SKILLS.items():
        assert skill.get("synthetic_data_policy") == "reject_in_production", sid


# 10. Cross-producer correlation must route to the Hub.
def test_fixture_10_cross_producer_routes_to_hub():
    negatives = _activation()["negative"]
    hub_routed = [c for c in negatives if c.get("expect") == "route_to_hub"]
    assert any("correlate" in c["prompt"].lower() for c in hub_routed)
