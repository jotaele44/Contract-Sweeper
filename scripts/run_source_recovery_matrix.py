#!/usr/bin/env python3
"""Typed GUI/CI entrypoint for the source-recovery matrix builder.

The legacy builder intentionally writes fixed files under ``reports/``.  This
adapter preserves its classification logic while making the repository root and
output directory explicit, so TheHub can execute it without hard-coded
filesystem coupling. ``--check`` builds into an isolated temporary directory and
compares bytes against the declared output directory; it never overwrites the
reference artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_source_recovery_matrix as builder  # noqa: E402

OUTPUT_NAMES = (
    "source_recovery_matrix.csv",
    "source_recovery_matrix.md",
    "materialization_readiness.json",
)


def _configure(root: Path, out: Path) -> None:
    builder.REPO_ROOT = root
    builder.OUT_CSV = out / OUTPUT_NAMES[0]
    builder.OUT_MD = out / OUTPUT_NAMES[1]
    builder.OUT_JSON = out / OUTPUT_NAMES[2]


def _build(root: Path, out: Path) -> dict[str, object]:
    _configure(root, out)
    rows = builder.build_rows(root)
    summary = builder.build_summary(rows)
    out.mkdir(parents=True, exist_ok=True)
    builder._write_csv(rows)
    builder._write_md(rows, summary)
    builder.OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "PASS",
        "row_count": len(rows),
        "automatable_ready": summary["automatable_ready"],
        "automatable_total": summary["automatable_total"],
        "queued_excluded_total": summary["queued_excluded_total"],
        "outputs": [str(out / name) for name in OUTPUT_NAMES],
    }


def _check(root: Path, expected_out: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="moneysweep-source-recovery-") as tmp:
        generated = Path(tmp)
        result = _build(root, generated)
        mismatches: list[str] = []
        for name in OUTPUT_NAMES:
            expected = expected_out / name
            candidate = generated / name
            if not expected.is_file():
                mismatches.append(f"missing expected output: {expected}")
                continue
            if expected.read_bytes() != candidate.read_bytes():
                mismatches.append(f"byte mismatch: {expected}")
        result["status"] = "PASS" if not mismatches else "FAIL"
        result["mismatches"] = mismatches
        result["outputs"] = [str(expected_out / name) for name in OUTPUT_NAMES]
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "reports")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    out = args.out.expanduser().resolve()
    try:
        result = _check(root, out) if args.check else _build(root, out)
    except Exception as exc:  # fail closed for manager/CI callers
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
