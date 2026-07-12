"""Gap-closure Phase 0 baseline: frozen artifacts stay internally reconciled.

The baseline is a one-shot snapshot (see scripts/build_gap_closure_baseline.py)
— these tests assert internal consistency of the committed artifacts, NOT byte
regeneration (the working tree moves on; the baseline does not).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_gap_closure_baseline import (
    BASELINE_DIR,
    INVENTORY_CLASSIFICATIONS,
    LEDGER_FIELDS,
    verify_baseline,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / BASELINE_DIR

ABSENT_DATASET_GAPS = {
    "GAP-001": "donaciones_pr",
    "GAP-002": "pr_cabilderos",
    "GAP-003": "cor3",
    "GAP-004": "ocpr_contracts",
    "GAP-005": "oficina_contralor",
    "GAP-006": "fpds_report_builder",
    "GAP-007": "sam_entities",
    "GAP-008": "usaspending_prime",
}


def _manifest() -> dict:
    return json.loads((OUT_DIR / "baseline_manifest.json").read_text(encoding="utf-8"))


def _csv_rows(name: str) -> list[dict]:
    with (OUT_DIR / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_all_baseline_artifacts_exist():
    for rel in _manifest()["outputs"]:
        assert (ROOT / rel).exists(), f"declared baseline output missing: {rel}"


def test_baseline_internally_reconciled():
    assert verify_baseline(ROOT) == []


def test_source_status_covers_registry_once():
    manifest = _manifest()
    rows = _csv_rows("baseline_source_status.csv")
    ids = [r["source_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate source_id in baseline status"
    assert len(rows) == manifest["registry"]["source_count"]


def test_inventory_classifications_are_known():
    rows = _csv_rows("baseline_file_inventory.csv")
    assert rows, "baseline file inventory is empty"
    assert {r["classification"] for r in rows} <= INVENTORY_CLASSIFICATIONS
    assert {r["presence"] for r in rows} <= {"disk", "manifest_only"}


def test_ledger_schema_and_absent_datasets():
    rows = _csv_rows("unresolved_gap_ledger.csv")
    assert rows and list(rows[0].keys()) == list(LEDGER_FIELDS)
    by_id = {r["gap_id"]: r for r in rows}
    assert len(by_id) == len(rows), "duplicate gap_id in ledger"
    for gap_id, source_id in ABSENT_DATASET_GAPS.items():
        row = by_id.get(gap_id)
        assert row is not None, f"missing ledger row {gap_id} ({source_id})"
        assert row["source_id"] == source_id
        assert row["gap_type"] == "dataset_absent"
    for r in rows:
        assert r["status"] in {"open", "resolved", "rejected"}, r["gap_id"]
        if r["status"] != "open":
            assert r["resolved_by"], f"{r['gap_id']} resolved without resolved_by"


def test_baseline_registry_snapshot_matches_manifest_counts():
    manifest = _manifest()
    assert manifest["schema_version"] == "gap_closure_baseline_v1"
    assert manifest["ledger"]["rows"] >= len(ABSENT_DATASET_GAPS)
    assert manifest["registry"]["source_ids_sha256"]
    assert len(manifest["baseline_commit"]) == 40
