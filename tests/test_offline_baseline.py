from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

import pytest

from moneysweep.orchestrator.offline_baseline import (
    BaselineConfig,
    OfflineBaselineViolation,
    block_network,
    run_offline_baseline,
    sanitized_child_environment,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_network_guard_fails_closed() -> None:
    with block_network(), pytest.raises(OfflineBaselineViolation):
        socket.create_connection(("example.invalid", 443))


def test_child_environment_removes_credentials_and_proxies() -> None:
    env = sanitized_child_environment(
        {
            "FEC_API_KEY": "secret",
            "SERVICE_TOKEN": "secret",
            "HTTP_PROXY": "http://proxy.invalid",
            "SAFE_NAME": "kept",
        }
    )
    assert "FEC_API_KEY" not in env
    assert "SERVICE_TOKEN" not in env
    assert "HTTP_PROXY" not in env
    assert env["SAFE_NAME"] == "kept"
    assert env["MONEYSWEEP_OFFLINE_BASELINE"] == "1"


def test_baseline_is_deterministic_and_fail_closed(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    (inputs / "cor3_official_projects_export.xlsx").write_bytes(b"local-workbook")
    _write_csv(
        inputs / "entity_master(2).csv",
        ["entity_key", "award_count"],
        [{"entity_key": "alpha", "award_count": "1"}],
    )
    _write_csv(
        inputs / "pr_entity_profiles.csv",
        ["normalized_name", "award_count"],
        [{"normalized_name": "alpha", "award_count": "1"}],
    )

    config = BaselineConfig(
        input_dir=inputs,
        output_root=outputs,
        git_sha="abc123",
        generated_at="2026-07-31T20:57:00-04:00",
    )
    first = run_offline_baseline(config)
    second = run_offline_baseline(config)

    assert first["run_id"] == second["run_id"]
    assert second["immutable_status"] == "EXISTING_IDENTICAL"
    receipt = json.loads((Path(first["output_dir"]) / "run_receipt.json").read_text())
    assert receipt["classification"] == "CANON_BASELINE_PROVISIONAL"
    assert receipt["production_status"] == "NON_PRODUCTION_DIAGNOSTIC"
    assert receipt["canonical_certification"] is False
    assert receipt["required_source_credit"]["credit_changed"] is False
    assert receipt["network_access_authorized"] is False


def test_default_baseline_rerun_reuses_existing_timestamp(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    (inputs / "cor3_official_projects_export.xlsx").write_bytes(b"local-workbook")
    _write_csv(
        inputs / "entity_master(2).csv",
        ["entity_key", "award_count"],
        [{"entity_key": "alpha", "award_count": "1"}],
    )
    _write_csv(
        inputs / "pr_entity_profiles.csv",
        ["normalized_name", "award_count"],
        [{"normalized_name": "alpha", "award_count": "1"}],
    )

    config = BaselineConfig(input_dir=inputs, output_root=outputs, git_sha="abc123")
    first = run_offline_baseline(config)
    second = run_offline_baseline(config)

    assert first["run_id"] == second["run_id"]
    assert second["immutable_status"] == "EXISTING_IDENTICAL"


def test_strict_inputs_reject_empty_required_files(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    (inputs / "cor3_official_projects_export.xlsx").write_bytes(b"local-workbook")
    _write_csv(inputs / "entity_master(2).csv", ["entity_key"], [])
    _write_csv(inputs / "pr_entity_profiles.csv", ["normalized_name"], [{"normalized_name": "x"}])

    with pytest.raises(OfflineBaselineViolation, match="empty required local inputs"):
        run_offline_baseline(
            BaselineConfig(
                input_dir=inputs,
                output_root=outputs,
                git_sha="abc123",
                strict_inputs=True,
            )
        )


def test_repo_root_runs_stage_into_isolated_workspace(tmp_path: Path, monkeypatch) -> None:
    from moneysweep.orchestrator import _offline_baseline_runner as runner

    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    repo = tmp_path / "repo"
    repo.mkdir()
    existing = repo / "data" / "staging" / "processed" / "entity_master.csv"
    _write_csv(existing, ["entity_key"], [{"entity_key": "existing"}])
    inputs.mkdir()
    (inputs / "cor3_official_projects_export.xlsx").write_bytes(b"local-workbook")
    _write_csv(inputs / "entity_master(2).csv", ["entity_key"], [{"entity_key": "staged"}])
    _write_csv(
        inputs / "pr_entity_profiles.csv", ["normalized_name"], [{"normalized_name": "staged"}]
    )

    seen_workspace: dict[str, Path] = {}

    def fake_run_repo_stages(workspace_root: Path, _output_dir: Path) -> list[dict[str, str]]:
        seen_workspace["root"] = workspace_root
        assert (workspace_root / "data/staging/processed/entity_master.csv").read_text(
            encoding="utf-8"
        ) != existing.read_text(encoding="utf-8")
        return [{"stage": "stub", "status": "OK"}]

    monkeypatch.setattr(runner, "_run_repo_stages", fake_run_repo_stages)
    monkeypatch.setattr(
        runner,
        "source_coverage",
        lambda *_args, **_kwargs: {"required_fully_materialized": 10},
    )

    run_offline_baseline(
        BaselineConfig(input_dir=inputs, output_root=outputs, repo_root=repo, git_sha="abc123")
    )

    assert seen_workspace["root"] != repo
    with existing.open(encoding="utf-8") as handle:
        assert next(csv.DictReader(handle))["entity_key"] == "existing"


def test_absolute_operator_paths_are_not_written_to_manifest(tmp_path: Path) -> None:
    inputs = tmp_path / "operator" / "nested"
    outputs = tmp_path / "outputs"
    inputs.mkdir(parents=True)
    _write_csv(
        inputs / "entity_master(2).csv",
        ["entity_key"],
        [{"entity_key": "alpha"}],
    )
    _write_csv(
        inputs / "pr_entity_profiles.csv",
        ["normalized_name"],
        [{"normalized_name": "alpha"}],
    )
    (inputs / "cor3_official_projects_export.xlsx").write_bytes(b"x")

    result = run_offline_baseline(
        BaselineConfig(
            input_dir=inputs,
            output_root=outputs,
            git_sha="abc123",
            generated_at="2026-07-31T20:57:00-04:00",
        )
    )
    manifest_text = (Path(result["output_dir"]) / "input_manifest.json").read_text()
    assert str(tmp_path) not in manifest_text
