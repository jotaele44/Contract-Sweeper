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
