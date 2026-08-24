"""MoneySweep command-line parser with fail-closed special profiles."""

from __future__ import annotations

import argparse

from moneysweep.orchestrator.cli_legacy import build_arg_parser as _build_legacy_parser


def build_arg_parser() -> argparse.ArgumentParser:
    parser = _build_legacy_parser()
    profile_action = next(action for action in parser._actions if action.dest == "profile")
    profile_action.choices = (
        "full",
        "incremental",
        "offline-baseline",
        "discovery",
        "corpus",
        "two-stage",
    )
    profile_action.help = (
        "Run the legacy full pipeline, due registry sources, deterministic local baseline, "
        "or the non-production two-stage discovery/corpus control plane"
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
    parser.add_argument(
        "--discovery-seed",
        action="append",
        default=[],
        help="Raw Stage-1 subject seed; repeat for multiple seeds",
    )
    parser.add_argument(
        "--discovery-packet",
        default=None,
        help="Existing DiscoveryStagePacket JSON required by corpus or Stage-2 resume",
    )
    parser.add_argument(
        "--two-stage-output-root",
        default="reports/two_stage",
        help="Non-production output root for discovery/two-stage receipts",
    )
    parser.add_argument(
        "--two-stage-generated-at",
        default=None,
        help="Fixed ISO-8601 timestamp for deterministic two-stage packet fixtures",
    )
    return parser
