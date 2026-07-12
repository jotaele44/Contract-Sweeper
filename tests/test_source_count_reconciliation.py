"""Drift gate: every committed source-count surface must equal the readiness truth.

History (see reports/gap_closure/baseline_contradictions.md finding 1): four
committed surfaces disagreed — 144 (live) vs 143 (federation.json) vs 141
(reconciliation file) vs 136 (current_status.json's readiness-truth block) —
because only reports/materialization_readiness.json was test-pinned. This gate
pins the other three to the same committed bytes AND to the live recompute, so
a stale snapshot fails CI even when the code agrees with itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_source_recovery_matrix import (
    build_registry_snapshot,
    build_rows,
    build_summary,
)
from moneysweep.runtime.source_registry import load_source_registry

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

COUNT_KEYS = (
    "total_sources",
    "automatable_total",
    "automatable_ready",
    "queued_excluded_total",
    "queued_excluded",
)


def _read(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _counts(block: dict, total_key: str = "total_sources") -> dict:
    return {
        "total_sources": block.get(total_key),
        "automatable_total": block.get("automatable_total"),
        "automatable_ready": block.get("automatable_ready"),
        "queued_excluded_total": block.get("queued_excluded_total"),
        "queued_excluded": block.get("queued_excluded"),
    }


def _readiness_truth() -> dict:
    return _counts(_read("reports/materialization_readiness.json"))


def test_committed_readiness_matches_live_recompute():
    live = _counts(build_summary(build_rows()))
    assert _readiness_truth() == live, (
        "reports/materialization_readiness.json is stale — regenerate with "
        "scripts/build_source_recovery_matrix.py"
    )


def test_federation_source_truth_matches_readiness():
    fed = _counts(_read("federation.json").get("source_truth", {}))
    assert fed == _readiness_truth(), (
        "federation.json source_truth drifted from reports/materialization_readiness.json"
    )


def test_reconciliation_file_matches_readiness():
    rec = _counts(
        _read("reports/federation_source_status_reconciliation.json"),
        total_key="canonical_source_count",
    )
    assert rec == _readiness_truth(), (
        "reports/federation_source_status_reconciliation.json drifted from "
        "reports/materialization_readiness.json"
    )


def test_current_status_readiness_truth_matches_readiness():
    block = _read("reports/current_status.json").get("materialization_readiness_truth", {})
    assert _counts(block) == _readiness_truth(), (
        "reports/current_status.json materialization_readiness_truth drifted "
        "from reports/materialization_readiness.json"
    )


def test_current_status_registry_snapshot_matches_live():
    block = _read("reports/current_status.json").get("source_registry_current", {})
    live = build_registry_snapshot(load_source_registry(ROOT).get("sources", []))
    assert block.get("total_sources") == live["source_count"]
    assert block.get("source_ids_sha256") == live["source_ids_sha256"]
