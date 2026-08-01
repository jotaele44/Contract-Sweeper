"""Build an immutable, local-only MoneySweep provisional baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from moneysweep.orchestrator._offline_baseline_core import (
    BaselineConfig,
    OfflineBaselineViolation,
    block_network,
    sanitized_child_environment,
)
from moneysweep.orchestrator._offline_baseline_runner import run_offline_baseline

__all__ = [
    "BaselineConfig",
    "OfflineBaselineViolation",
    "block_network",
    "run_offline_baseline",
    "sanitized_child_environment",
]

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--repo-root")
    parser.add_argument("--git-sha", default="UNKNOWN")
    parser.add_argument("--generated-at")
    parser.add_argument("--strict-inputs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_offline_baseline(
        BaselineConfig(
            input_dir=Path(args.input_dir),
            output_root=Path(args.output_root),
            repo_root=Path(args.repo_root) if args.repo_root else None,
            git_sha=args.git_sha,
            generated_at=args.generated_at,
            strict_inputs=args.strict_inputs,
        )
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
