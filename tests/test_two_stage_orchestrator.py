from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import run_all
from moneysweep.orchestrator.cli import build_arg_parser
from moneysweep.orchestrator.two_stage import TwoStageConfig, run_discovery


def test_cli_exposes_new_profiles_without_removing_legacy_profiles() -> None:
    parser = build_arg_parser()
    action = next(item for item in parser._actions if item.dest == "profile")
    assert set(action.choices) == {
        "full",
        "incremental",
        "offline-baseline",
        "discovery",
        "corpus",
        "two-stage",
    }


def test_discovery_profile_is_deterministic_and_blocks_promotion(tmp_path: Path) -> None:
    config = TwoStageConfig(
        profile="discovery",
        repo_root=tmp_path,
        output_root=tmp_path / "out",
        discovery_seeds=("ACME, INC.",),
        generated_at="2026-08-24T18:00:00-04:00",
    )
    first = run_discovery(config)
    first_bytes = (tmp_path / "out" / "discovery_stage_packet.json").read_bytes()
    second = run_discovery(config)
    second_bytes = (tmp_path / "out" / "discovery_stage_packet.json").read_bytes()

    assert first_bytes == second_bytes
    assert first["production_promotion"] == "BLOCKED"
    assert second["production_promotion"] == "BLOCKED"
    payload = json.loads(first_bytes)
    assert payload["case_id"].startswith("discovery-")
    assert payload["subject_seeds"] == ["ACME, INC."]


def test_legacy_profile_still_delegates_to_run_all_legacy(monkeypatch) -> None:
    calls: list[list[str]] = []
    fake = types.ModuleType("run_all_legacy")

    def fake_main() -> int:
        calls.append(list(sys.argv[1:]))
        return 37

    fake.main = fake_main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "run_all_legacy", fake)

    result = run_all.main(["--profile", "incremental"])
    assert result == 37
    assert calls == [["--profile", "incremental"]]
