"""Completeness matrix: byte-identical regeneration + vocabulary/coverage gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_completeness_matrix import (
    CSV_FIELDS,
    OUT_CSV,
    OUT_JSON,
    build_matrix,
    build_summary,
    render_csv,
    render_json,
)
from moneysweep.runtime.source_registry import load_source_registry
from moneysweep.validation.completeness import (
    ACQUISITION_STATUSES,
    CERTIFICATION_STATUSES,
    COVERAGE_STATUSES,
    FRESHNESS_STATUSES,
    MATERIALITY_LABELS,
    MATERIALIZATION_STATUSES,
    RECONCILIATION_STATUSES,
    WIRED_STATUSES,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

ROWS = build_matrix(ROOT)


def test_matrix_regenerates_byte_identically():
    """The committed matrix must equal a live regeneration (clean-checkout
    deterministic, like materialization_readiness.json)."""
    committed_csv = (ROOT / OUT_CSV).read_text(encoding="utf-8")
    committed_json = (ROOT / OUT_JSON).read_text(encoding="utf-8")
    assert render_csv(ROWS) == committed_csv, (
        f"{OUT_CSV} is stale — regenerate with scripts/build_completeness_matrix.py"
    )
    assert render_json(build_summary(ROWS)) == committed_json, (
        f"{OUT_JSON} is stale — regenerate with scripts/build_completeness_matrix.py"
    )


def test_every_live_source_appears_exactly_once():
    ids = [r["source_id"] for r in ROWS]
    assert len(ids) == len(set(ids))
    live = {s["source_id"] for s in load_source_registry(ROOT).get("sources", [])}
    assert set(ids) == live


def test_all_dimensions_use_known_vocabularies():
    vocab = {
        "wired_status": set(WIRED_STATUSES),
        "acquisition_status": set(ACQUISITION_STATUSES),
        "materialization_status": set(MATERIALIZATION_STATUSES),
        "coverage_status": set(COVERAGE_STATUSES),
        "reconciliation_status": set(RECONCILIATION_STATUSES),
        "freshness_status": set(FRESHNESS_STATUSES),
        "certification_status": set(CERTIFICATION_STATUSES),
        "materiality_label": set(MATERIALITY_LABELS),
    }
    for row in ROWS:
        for field, allowed in vocab.items():
            assert row[field] in allowed, f"{row['source_id']}.{field}={row[field]!r}"


def test_complete_labels_require_a_contract():
    for row in ROWS:
        if row["materiality_label"] in ("validated_complete", "complete_stale"):
            assert row["has_contract"], (
                f"{row['source_id']} labeled {row['materiality_label']} without a contract"
            )
        if row["certification_status"] == "certified_complete":
            assert row["has_contract"], f"{row['source_id']} certified without a contract"


def test_csv_header_matches_declared_fields():
    with (ROOT / OUT_CSV).open(encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == list(CSV_FIELDS)


def test_summary_counts_reconcile():
    summary = json.loads((ROOT / OUT_JSON).read_text(encoding="utf-8"))
    assert summary["total_sources"] == len(ROWS)
    assert summary["contracted_sources"] == sum(1 for r in ROWS if r["has_contract"])
    for field in ("by_certification_status", "by_materiality_label"):
        assert sum(summary[field].values()) == len(ROWS)


def test_gap_report_carries_contract_columns():
    with (ROOT / "reports" / "gap_analysis_report.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    for col in ("materiality_label", "coverage_status", "certification_status"):
        assert col in rows[0], f"gap_analysis_report.csv missing appended column {col}"
    assert not any(r["source_status"] == "below_threshold" for r in rows), (
        "below_threshold is retired; under-min_rows is partially_materialized"
    )
