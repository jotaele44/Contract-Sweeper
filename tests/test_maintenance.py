"""MoneySweep maintenance adapter: repo-specific checks + shared-package wiring.

Generic detection/runner behavior now lives in thehub-pr's shared
`prii_maintenance` package (thehub-pr/packages/prii_maintenance/tests/); this
file keeps only the checks genuinely specific to moneysweep-pr
(`maintenance/adapters/local.py`) plus a smoke test proving the CLI shim's
dependency-injection wiring (`prii_maintenance.run_maintenance(...,
local_checks=local.run_checks)`) actually invokes this repo's adapter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maintenance.adapters import local  # noqa: E402
from prii_maintenance import run_maintenance  # noqa: E402
from prii_maintenance import state as state_mod  # noqa: E402

EXPORT_DIR = "data/exports/canonical_v1_federation"


def _federation(root, **outputs):
    fed = {"program_id": "moneysweep-pr", "canonical_outputs": outputs}
    (root / "federation.json").write_text(json.dumps(fed), encoding="utf-8")
    return state_mod.collect_repo_state(root)


def _write_readiness(root, **fields):
    base = {
        "automatable_ready": 95,
        "automatable_total": 95,
        "queued_excluded": {"manual_export": 39, "scraper_needed": 2},
        "queued_excluded_total": 41,
    }
    base.update(fields)
    path = root / "reports" / "materialization_readiness.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base), encoding="utf-8")


def _write_export(root, *, gate, entities):
    d = root / EXPORT_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"gate": gate}), encoding="utf-8")
    (d / "entities.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entities) + "\n", encoding="utf-8"
    )


def test_readiness_missing_is_error(tmp_path):
    state = _federation(tmp_path)
    findings = local.check_source_registry_freshness("moneysweep-pr", tmp_path, state)
    assert any(f.category == "source_staleness" and f.severity == "error" for f in findings)


def test_readiness_reconciles_no_finding(tmp_path):
    _write_readiness(tmp_path)
    state = _federation(tmp_path)
    assert local.check_source_registry_freshness("moneysweep-pr", tmp_path, state) == []


def test_readiness_count_mismatch_is_warning(tmp_path):
    _write_readiness(tmp_path, automatable_ready=90)  # != total 95
    state = _federation(tmp_path)
    findings = local.check_source_registry_freshness("moneysweep-pr", tmp_path, state)
    assert any(f.severity == "warning" for f in findings)


def test_synthetic_blocks_in_production(tmp_path):
    _write_export(tmp_path, gate="PRODUCTION", entities=[{"entity_id": "E1", "synthetic": True}])
    state = _federation(tmp_path)
    findings = local.check_synthetic_leakage("moneysweep-pr", tmp_path, state)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_synthetic_allowed_in_diagnostic(tmp_path):
    _write_export(
        tmp_path,
        gate="NON_PRODUCTION_DIAGNOSTIC",
        entities=[{"entity_id": "E1", "synthetic": True}],
    )
    state = _federation(tmp_path)
    assert local.check_synthetic_leakage("moneysweep-pr", tmp_path, state) == []


def test_vendor_duplicate_ids_warning(tmp_path):
    _write_export(
        tmp_path,
        gate="NON_PRODUCTION_DIAGNOSTIC",
        entities=[{"entity_id": "E1"}, {"entity_id": "E1"}],
    )
    state = _federation(tmp_path)
    findings = local.check_vendor_duplicate_ids("moneysweep-pr", tmp_path, state)
    assert len(findings) == 1
    assert findings[0].category == "duplicate"


# ---- shared-package wiring smoke test ----


def test_run_maintenance_invokes_local_adapter_and_is_not_blocked_when_clean(tmp_path):
    """Prove the CLI shim's local_checks injection actually reaches this repo's
    adapter through the shared prii_maintenance package."""
    _write_readiness(tmp_path)
    _federation(tmp_path)

    report = run_maintenance(
        root=tmp_path,
        mode="audit",
        write=False,
        program_id="moneysweep-pr",
        local_checks=local.run_checks,
    )

    assert report.promotion_blocked is False
