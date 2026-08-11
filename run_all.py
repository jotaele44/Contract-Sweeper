"""MoneySweep pipeline profile dispatcher.

The legacy full and incremental pipeline remains byte-identical in
``run_all_legacy.py``. The ``offline-baseline`` profile is intercepted here so it
cannot fall through into any downloader or credentialed stage.
"""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent


def _profile_value(argv: Sequence[str]) -> str | None:
    for index, value in enumerate(argv):
        if value.startswith("--profile="):
            return value.split("=", 1)[1]
        if value == "--profile" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _current_git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


@contextmanager
def _argv_context(argv: Sequence[str]) -> Iterator[None]:
    original = sys.argv
    sys.argv = [original[0], *argv]
    try:
        yield
    finally:
        sys.argv = original


def _run_offline_baseline(argv: Sequence[str]) -> int:
    from moneysweep.orchestrator.cli import build_arg_parser
    from moneysweep.orchestrator.offline_baseline import BaselineConfig, run_offline_baseline

    args = build_arg_parser().parse_args(list(argv))
    result = run_offline_baseline(
        BaselineConfig(
            input_dir=PROJECT_ROOT / args.offline_input_dir,
            output_root=PROJECT_ROOT / args.offline_output_root,
            repo_root=PROJECT_ROOT,
            git_sha=args.offline_git_sha or _current_git_sha(),
            generated_at=args.offline_generated_at,
            strict_inputs=args.offline_strict_inputs,
        )
    )
    print(json.dumps(result, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _profile_value(arguments) == "offline-baseline":
        return _run_offline_baseline(arguments)

    from run_all_legacy import main as legacy_main

    if argv is None:
        return legacy_main()
    with _argv_context(arguments):
        return legacy_main()


if __name__ == "__main__":
    raise SystemExit(main())
