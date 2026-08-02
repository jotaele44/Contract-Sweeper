"""Focused tests for the authorized local HUD DRGR producer contract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.ingest_hud_drgr_exports import _looks_like_hud_drgr, run


def _make_tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "manual" / "hud_drgr").mkdir(parents=True)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "normalized").mkdir(parents=True)
    (tmp_path / "data" / "staging" / "processed").mkdir(parents=True)
    return tmp_path


def test_empty_manual_drop_returns_manual_required_and_writes_contract_outputs(tmp_path):
    root = _make_tmp_root(tmp_path)
    result = run(root=root, force=True)
    assert result == {
        "activity_rows": 0,
        "project_rows": 0,
        "drawdown_rows": 0,
        "appropriation_rows": 0,
        "status": "manual_required",
    }
    for name in (
        "hud_drgr_activities.parquet",
        "hud_drgr_projects.parquet",
        "hud_drgr_drawdowns.parquet",
        "hud_drgr_appropriations.parquet",
    ):
        parquet = root / "data" / "normalized" / name
        assert parquet.exists() or parquet.with_suffix(".csv").exists()
    for name in ("hud_drgr_activities.csv", "hud_drgr_projects.csv"):
        assert (root / "data" / "staging" / "processed" / name).exists()


def test_activity_export_materializes_activity_and_project_csvs(tmp_path):
    root = _make_tmp_root(tmp_path)
    pd.DataFrame(
        {
            "Activity ID": ["A-1", "A-2"],
            "Project ID": ["P-1", "P-1"],
            "Grant Number": ["B-17-DM-72-0001", "B-17-DM-72-0001"],
            "Activity Name": ["Planning", "Construction"],
            "Responsible Organization": ["Municipio de San Juan", "Municipio de San Juan"],
            "Municipality": ["San Juan", "San Juan"],
            "Total Budget": ["100", "200"],
            "Amount Drawn": ["25", "50"],
            "Amount Remaining": ["75", "150"],
        }
    ).to_csv(root / "data" / "manual" / "hud_drgr" / "drgr_activities.csv", index=False)
    result = run(root=root, force=True)
    assert result["activity_rows"] == 2
    assert result["project_rows"] == 1
    activities = pd.read_csv(root / "data" / "staging" / "processed" / "hud_drgr_activities.csv")
    projects = pd.read_csv(root / "data" / "staging" / "processed" / "hud_drgr_projects.csv")
    assert len(activities) == 2
    assert projects.loc[0, "project_id"] == "P-1"
    assert projects.loc[0, "activity_count"] == 2
    assert projects.loc[0, "total_budget"] == 300


def test_cached_run_backfills_registry_csvs_and_real_counts(tmp_path):
    root = _make_tmp_root(tmp_path)
    pd.DataFrame(
        {"Activity ID": ["A-1"], "Project ID": ["P-1"], "Activity Name": ["Planning"]}
    ).to_csv(root / "data" / "manual" / "hud_drgr" / "hud_activities.csv", index=False)
    run(root=root, force=True)
    for name in ("hud_drgr_activities.csv", "hud_drgr_projects.csv"):
        (root / "data" / "staging" / "processed" / name).unlink()
    result = run(root=root, force=False)
    assert result["status"] == "CACHED"
    assert result["activity_rows"] == 1
    assert result["project_rows"] == 1
    assert (root / "data" / "staging" / "processed" / "hud_drgr_activities.csv").exists()
    assert (root / "data" / "staging" / "processed" / "hud_drgr_projects.csv").exists()


def test_unrelated_raw_files_are_ignored(tmp_path):
    root = _make_tmp_root(tmp_path)
    unrelated = root / "data" / "raw" / "follow_the_money"
    unrelated.mkdir(parents=True)
    pd.DataFrame({"x": [1, 2, 3]}).to_csv(unrelated / "funding_flows_sf133.csv", index=False)
    result = run(root=root, force=True)
    assert result["status"] == "manual_required"


def test_looks_like_hud_drgr_filter():
    assert _looks_like_hud_drgr(Path("data/manual/hud_drgr/something.xlsx"))
    assert _looks_like_hud_drgr(Path("data/raw/HUD DRGR (all PR grantees).xls"))
    assert _looks_like_hud_drgr(Path("data/raw/anywhere/cdbg_dr_export.csv"))
    assert not _looks_like_hud_drgr(Path("data/raw/follow_the_money/funding_flows_sf133.csv"))
    assert not _looks_like_hud_drgr(Path("data/raw/FEC/efile-2026.csv"))
