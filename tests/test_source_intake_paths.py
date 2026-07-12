"""Pandas-free tests for source-intake dropzone path + dataset reconciliation.

These exercise :mod:`scripts.source_intake_paths` directly. The module is
deliberately stdlib-only so the ACT/ACUDEN dropzone reconciliation — the defect
where a shared combined extract was not attributed to its per-source dataset —
is testable without the pipeline's pandas/openpyxl dependencies.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.config import PROJECT_ROOT
from scripts.source_intake_paths import (
    DATASET_PARTITION_COLUMN,
    SHARED_EXTRACT_DATASET_FILTERS,
    discover_tabular_files,
    dropzone_has_tabular_data,
)

pytestmark = pytest.mark.unit

# Mirrors the ACT/ACUDEN SourceSpec dropzone + committed extract without
# importing the pandas-backed controller module.
ACT_TRANSITION_DROPZONE = "data/raw/act_transition"
COMMITTED_EXTRACT_NAME = "transition_contracts_extracted.csv"


def test_discover_tabular_files_selects_only_tabular(tmp_path: Path):
    (tmp_path / "keep.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "sheet.xlsx").write_bytes(b"stub")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    (tmp_path / "~lock.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()

    found = {p.name for p in discover_tabular_files(tmp_path)}
    assert found == {"keep.csv", "sheet.xlsx"}


def test_discover_tabular_files_missing_dir_is_empty(tmp_path: Path):
    assert discover_tabular_files(tmp_path / "does-not-exist") == []
    assert dropzone_has_tabular_data(tmp_path / "does-not-exist") is False


def test_act_acuden_dropzone_resolves_to_present_extract():
    """The reconciliation fix: the ACT/ACUDEN dropzone points at the folder that
    actually holds the committed extract, so readiness detects it as present."""
    dropzone = PROJECT_ROOT / ACT_TRANSITION_DROPZONE
    assert dropzone.is_dir(), f"dropzone missing: {ACT_TRANSITION_DROPZONE}"
    names = {p.name for p in discover_tabular_files(dropzone)}
    assert COMMITTED_EXTRACT_NAME in names, (
        f"{COMMITTED_EXTRACT_NAME} not discovered under {ACT_TRANSITION_DROPZONE}; "
        f"found {sorted(names)}"
    )
    assert dropzone_has_tabular_data(dropzone) is True


def test_shared_extract_partition_tokens_present_in_extract():
    """ACT and ACUDEN share one combined extract; each declared dataset token
    must actually appear in the extract's partition column so the per-source
    filter selects real rows rather than silently emptying."""
    extract = PROJECT_ROOT / ACT_TRANSITION_DROPZONE / COMMITTED_EXTRACT_NAME
    assert extract.is_file(), f"committed extract missing: {extract}"

    with extract.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert DATASET_PARTITION_COLUMN in reader.fieldnames, (
            f"{DATASET_PARTITION_COLUMN} column absent from extract header {reader.fieldnames}"
        )
        present_tokens = {(row.get(DATASET_PARTITION_COLUMN) or "").strip() for row in reader}

    for source_id, token in SHARED_EXTRACT_DATASET_FILTERS.items():
        assert token in present_tokens, (
            f"dataset token {token!r} for {source_id} not found in extract "
            f"(present: {sorted(present_tokens)})"
        )


def test_shared_extract_filter_covers_act_and_acuden():
    assert SHARED_EXTRACT_DATASET_FILTERS == {
        "act_transition_contracts": "ACT_2020",
        "acuden_2024_transition": "ACUDEN_2024",
    }
