"""Ingest Centinelas intake drops into MoneySweep export-stream candidates.

Reads the Centinelas (``centinelas-pr``) JSON payloads dropped into this repo's
``intake/`` folder, keeps the finance-relevant (FINANCIAL/POLITICAL) ones, and
writes them as **pre-official located-finance candidates** in the export-stream
shape (``funding_awards.jsonl`` / ``transactions.jsonl``) that
``scripts/run_contract_finance_geo_reasoning.py`` and
``scripts/build_contract_finance_bundle.py`` consume via ``--export-dir``.

This is the MoneySweep end of the Centinelas → MoneySweep handoff; the money
anchor then shares the located finance with the SpiderWeb spatial overlay.

Usage:
  python3 scripts/ingest_centinelas_signals.py
  python3 scripts/ingest_centinelas_signals.py --intake-dir intake --output-dir exports/centinelas_intake
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.runtime.centinelas_intake import (  # noqa: E402
    REPO_ROOT,
    default_intake_dir,
    ingest_centinelas_drops,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "exports" / "centinelas_intake"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def run(
    intake_dir: Path | str | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    *,
    root: Path | str = REPO_ROOT,
) -> dict:
    output_dir = Path(output_dir)
    result = ingest_centinelas_drops(intake_dir, root=root)
    _write_jsonl(output_dir / "funding_awards.jsonl", result["awards"])
    _write_jsonl(output_dir / "transactions.jsonl", result["flows"])
    return {
        "status": result["status"],
        "award_count": len(result["awards"]),
        "transaction_count": len(result["flows"]),
        "output_dir": str(output_dir),
        "funding_awards": str(output_dir / "funding_awards.jsonl"),
        "transactions": str(output_dir / "transactions.jsonl"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--intake-dir",
        default=None,
        help=f"Centinelas drop folder (default: {default_intake_dir()})",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for the export-stream JSONL candidates.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args.intake_dir, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
