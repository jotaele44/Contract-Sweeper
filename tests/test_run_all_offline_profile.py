from __future__ import annotations

from moneysweep.orchestrator.cli import build_arg_parser


def test_cli_exposes_offline_baseline_profile() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--profile", "offline-baseline"])
    assert args.profile == "offline-baseline"
    assert args.offline_input_dir == "data/manual/offline_baseline"
    assert args.offline_output_root == "reports/offline_baseline"
