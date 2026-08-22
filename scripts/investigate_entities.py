#!/usr/bin/env python3
"""Run a bounded Money Sweep investigation for one or more selected entities.

Examples:
  python scripts/investigate_entities.py PREPA Genera Arcadis --mode FULL
  python scripts/investigate_entities.py ENT_ORG_... --bind ENT_ORG_...:uei:ABC123 --remote

``--bind`` attaches an external identifier only to an explicit canonical
``ENT_*`` id. It never resolves a raw name by external-id proximity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from moneysweep.investigate import investigate
from moneysweep.investigate.models import InvestigationLimits
from moneysweep.query import EntityIdentifier
from moneysweep.query.entity_types import EntityKind, SUPPORTED_KINDS


def _bindings(values: list[str]) -> dict[str, tuple[EntityIdentifier, ...]]:
    out: dict[str, list[EntityIdentifier]] = {}
    for value in values:
        try:
            entity_id, kind, identifier = value.split(":", 2)
        except ValueError as exc:
            raise ValueError("--bind must be ENT_ID:kind:value") from exc
        if not entity_id.startswith("ENT_"):
            raise ValueError("--bind requires a canonical ENT_* id")
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"unsupported --bind identifier kind: {kind}")
        out.setdefault(entity_id, []).append(
            EntityIdentifier(kind=cast(EntityKind, kind), value=identifier)
        )
    return {entity_id: tuple(items) for entity_id, items in out.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets", nargs="+", help="Canonical names, authoritative aliases, or ENT_* ids"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--mode",
        action="append",
        default=[],
        help="PROFILE, LINEAGE, CORRELATION, RELATIONSHIP, CONVERGENCE, or FULL",
    )
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-edges", type=int, default=250)
    parser.add_argument("--max-local-matches", type=int, default=500)
    parser.add_argument(
        "--bind", action="append", default=[], help="Attach external id as ENT_ID:kind:value"
    )
    parser.add_argument("--remote", action="store_true", help="Enable on-demand source adapters")
    parser.add_argument(
        "--source", action="append", default=[], help="Restrict remote adapter source_ids"
    )
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--output", help="Write JSON result to this path; stdout is always emitted")
    args = parser.parse_args(argv)

    try:
        bindings = _bindings(args.bind)
        result = investigate(
            args.targets,
            root=args.root,
            modes=args.mode or ("PROFILE",),
            limits=InvestigationLimits(
                max_depth=args.depth,
                max_nodes=args.max_nodes,
                max_edges=args.max_edges,
            ),
            external_identifiers=bindings,
            remote=args.remote,
            source_ids=args.source or None,
            force_refresh=args.force_refresh,
            max_local_matches=args.max_local_matches,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 2

    payload = result.to_dict()
    payload["status"] = "OPEN" if result.review_items else "PASS"
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if not result.review_items else 3


if __name__ == "__main__":
    raise SystemExit(main())
