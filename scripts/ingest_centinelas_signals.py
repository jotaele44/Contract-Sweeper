"""Ingest Centinelas drops into MoneySweep candidates and project assertions.

Project assertions are deliberately non-identity-bearing unless MoneySweep has an
independent authoritative binding. The shared ``lead_id`` is correlation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.runtime.centinelas_intake import (  # noqa: E402
    REPO_ROOT,
    default_intake_dir,
    ingest_centinelas_drops,
    load_drops,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "exports" / "centinelas_intake"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def _project_fiscal_assertions(
    drops: list[tuple[Path, dict[str, Any]]], awards: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build a complete candidate-set packet for each Centinelas project lead.

    MoneySweep's pre-official Centinelas awards are discovery candidates, not an
    authoritative award identity. Therefore they remain ``UNRESOLVED`` here. A
    future official-source adapter may add independently sourced binding evidence
    without changing this contract.
    """
    awards_by_item: dict[str, list[dict[str, Any]]] = {}
    for award in awards:
        awards_by_item.setdefault(str(award.get("centinelas_item_id") or ""), []).append(award)

    rows: list[dict[str, Any]] = []
    for path, payload in drops:
        lead = payload.get("project_lead")
        if not isinstance(lead, dict) or not lead.get("lead_id"):
            continue
        lead_id = str(lead["lead_id"])
        item_id = str(lead.get("origin_item_id") or payload.get("item_id") or path.stem)
        candidates = sorted(
            awards_by_item.get(item_id, []), key=lambda r: str(r.get("award_id") or "")
        )
        rows.append(
            {
                "assertion_schema": "project_fiscal_assertion/v1",
                "assertion_id": _stable_id("prjfis_", lead_id, "moneysweep-pr"),
                "lead_id": lead_id,
                "producer": "moneysweep-pr",
                "identity_effect": "NONE",
                "binding_state": "UNRESOLVED",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "independent_binding_evidence": [],
                "unresolved_cardinality": len(candidates),
                "lead_snapshot": lead,
                "provenance": {
                    "source_drop": str(path),
                    "origin_item_id": item_id,
                    "method": "centinelas_pre_official_candidate_enumeration",
                },
            }
        )
    return sorted(rows, key=lambda r: r["assertion_id"])


def run(
    intake_dir: Path | str | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    *,
    root: Path | str = REPO_ROOT,
) -> dict:
    output_dir = Path(output_dir)
    resolved_intake = Path(intake_dir) if intake_dir is not None else default_intake_dir(root)
    result = ingest_centinelas_drops(resolved_intake, root=root)
    assertions = _project_fiscal_assertions(load_drops(resolved_intake), result["awards"])
    _write_jsonl(output_dir / "funding_awards.jsonl", result["awards"])
    _write_jsonl(output_dir / "transactions.jsonl", result["flows"])
    _write_jsonl(output_dir / "project_fiscal_assertions.jsonl", assertions)
    return {
        "status": result["status"],
        "award_count": len(result["awards"]),
        "transaction_count": len(result["flows"]),
        "project_fiscal_assertion_count": len(assertions),
        "output_dir": str(output_dir),
        "funding_awards": str(output_dir / "funding_awards.jsonl"),
        "transactions": str(output_dir / "transactions.jsonl"),
        "project_fiscal_assertions": str(output_dir / "project_fiscal_assertions.jsonl"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--intake-dir", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args.intake_dir, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
