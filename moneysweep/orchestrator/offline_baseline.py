"""Build an immutable, local-only MoneySweep provisional baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from moneysweep.orchestrator._offline_baseline_core import (
    BaselineConfig,
    LocalCorpusConfig,
    OfflineBaselineViolation,
    block_network,
    certify_record_conservation,
    inventory_local_corpus,
    sanitized_child_environment,
)
from moneysweep.orchestrator._offline_baseline_runner import run_offline_baseline

__all__ = [
    "BaselineConfig",
    "LocalCorpusConfig",
    "OfflineBaselineViolation",
    "block_network",
    "certify_record_conservation",
    "inventory_local_corpus",
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
    parser.add_argument(
        "--inventory-local-corpus",
        action="store_true",
        help=(
            "freeze/hash/classify every supported file under --input-dir; do not materialize "
            "records or award canonical source credit"
        ),
    )
    parser.add_argument(
        "--local-bindings",
        help=(
            "optional JSON file whose top-level 'bindings' object maps exact corpus-relative "
            "paths to existing source_ids, semantic_class, and evidence_class"
        ),
    )
    return parser


def _read_bindings(path: str | None) -> dict[str, dict[str, object]]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    bindings = payload.get("bindings", {}) if isinstance(payload, dict) else {}
    if not isinstance(bindings, dict):
        raise OfflineBaselineViolation("local binding file must contain an object named 'bindings'")
    result: dict[str, dict[str, object]] = {}
    for key, value in bindings.items():
        if not isinstance(value, dict):
            raise OfflineBaselineViolation(f"local binding for {key!r} must be an object")
        result[str(key)] = dict(value)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.inventory_local_corpus:
        output_root = Path(args.output_root)
        output_path = output_root / "local_corpus_manifest.json"
        result = inventory_local_corpus(
            LocalCorpusConfig(
                input_dir=Path(args.input_dir),
                output_path=output_path,
                bindings=_read_bindings(args.local_bindings),
                generated_at=args.generated_at,
            )
        )
        print(json.dumps(result, indent=2))
        return 0 if result["certification"]["file_conservation"] == "PASS" else 1

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
