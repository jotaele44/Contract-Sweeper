"""MoneySweep command-line parser with the fail-closed offline baseline profile."""

from __future__ import annotations

import argparse

from moneysweep.orchestrator.cli_legacy import build_arg_parser as _build_legacy_parser


def build_arg_parser() -> argparse.ArgumentParser:
    parser = _build_legacy_parser()
    profile_action = next(action for action in parser._actions if action.dest == "profile")
    profile_action.choices = ("full", "incremental", "offline-baseline")
    profile_action.help = (
        "Run the legacy full pipeline, due registry sources, or the deterministic "
        "local-only provisional baseline"
    )
    parser.add_argument(
        "--offline-input-dir",
        default="data/manual/offline_baseline",
        help="Local operator dropzone used only by --profile offline-baseline",
    )
    parser.add_argument(
        "--offline-output-root",
        default="reports/offline_baseline",
        help="Immutable receipt root used only by --profile offline-baseline",
    )
    parser.add_argument(
        "--offline-git-sha",
        default=None,
        help="Explicit code identity; defaults to git rev-parse HEAD",
    )
    parser.add_argument(
        "--offline-generated-at",
        default=None,
        help="Fixed ISO-8601 timestamp for byte-reproducible receipts",
    )
    parser.add_argument(
        "--offline-strict-inputs",
        action="store_true",
        help="Fail before staging when a core local baseline input is absent",
    )
    return parser
