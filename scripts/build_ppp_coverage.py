"""
Build the PPP coverage truth file — what moneysweep-pr knows about every known
Puerto Rico public-private partnership, and how far each one has got.

Written because "do we have all the PPPs?" had no answerable form. PPP facts were
spread across a canonical projects table, a staging concession export, a
transition-report extract, and a source registry, with no single place saying
which concessions exist, which are canonical, and which are located well enough
for a spatial producer to place on a map.

Everything here is derived from committed tables, never hand-maintained — the
same discipline as reports/materialization_readiness.json. A concession is
listed as covered only if it actually resolves to a canonical project row.

Output: reports/ppp_coverage.json
        (docs/PPP_REGISTRY.md is the prose companion and is hand-written)

Usage:
  python3 scripts/build_ppp_coverage.py [--check]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS = "data/canonical_v1/projects.csv"
P3_STAGING = "data/staging/processed/pr_p3_contracts.csv"
CONCESSION_CONTRACTS = "data/staging/processed/pr_ppp_concession_contracts.csv"
OUT = "reports/ppp_coverage.json"

# Concessions known to exist in Puerto Rico, independent of whether this repo has
# ingested them yet. This is the denominator: a concession absent from every
# committed table still belongs here, listed as not covered, because a coverage
# report that only counts what was already ingested cannot show a gap.
KNOWN_CONCESSIONS = [
    {
        "concession": "PREPA transmission and distribution operation",
        "operator": "LUMA Energy",
        "aliases": ["LUMA"],
        "sector": "energy",
        "spatial_extent": "islandwide",
    },
    {
        "concession": "PREPA generation operation",
        "operator": "Genera PR",
        "aliases": ["Genera"],
        "sector": "energy",
        "spatial_extent": "islandwide",
    },
    {
        "concession": "PR-22 and PR-5 toll road concession",
        "operator": "Autopistas Metropolitanas de Puerto Rico",
        "aliases": ["Metropistas"],
        "sector": "transport",
        "spatial_extent": "corridor",
    },
    {
        "concession": "Luis Muñoz Marín Airport concession",
        "operator": "Aerostar Airport Holdings",
        "aliases": ["Aerostar", "Luis Muñoz Marín"],
        "sector": "transport",
        "spatial_extent": "site",
    },
    {
        "concession": "Teodoro Moscoso Bridge toll concession",
        "operator": "Autopistas de Puerto Rico y Compañía",
        "aliases": ["Teodoro Moscoso"],
        "sector": "transport",
        "spatial_extent": "site",
    },
    {
        "concession": "PRASA operation and maintenance agreement",
        "operator": "Veolia Water Puerto Rico",
        "aliases": ["Veolia", "PRASA O&M"],
        "sector": "water",
        "spatial_extent": "islandwide",
    },
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _norm(value: str) -> str:
    return " ".join((value or "").upper().split())


def build_report(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or REPO_ROOT)
    projects = _read_csv(root / PROJECTS)
    staging = _read_csv(root / P3_STAGING)
    contracts = _read_csv(root / CONCESSION_CONTRACTS)

    ppp_projects = [p for p in projects if p.get("project_type") == "ppp"]
    contracts_by_operator: dict[str, list[dict[str, str]]] = {}
    for c in contracts:
        contracts_by_operator.setdefault(_norm(c.get("concessionaire", "")), []).append(c)

    entries: list[dict[str, Any]] = []
    for known in KNOWN_CONCESSIONS:
        # The operator is named differently across surfaces — a project may be
        # titled "Metropistas Toll Road Concession" while the entity is
        # "Autopistas Metropolitanas de Puerto Rico" — so match on the operator
        # plus its declared aliases.
        keys = [_norm(known["operator"])] + [_norm(a) for a in known.get("aliases", [])]

        def _mentions(text: str) -> bool:
            norm = _norm(text)
            return any(k in norm for k in keys)

        matched = [
            p for p in ppp_projects if _mentions(p.get("notes", "")) or _mentions(p.get("project_name", ""))
        ]
        op_contracts = [
            c for key in keys for c in contracts_by_operator.get(key, [])
        ]
        contract_value = sum(
            float(c["contract_value"]) for c in op_contracts if c.get("contract_value")
        )
        # A municipality on an island-wide or corridor project records an
        # administrative seat, not the asset. canonical_v1_bridge withholds those
        # from the federated row, so reporting them as "located" here would
        # overstate what any downstream consumer actually receives.
        federated = [
            p for p in matched if p.get("municipality_id") and p.get("spatial_extent") == "site"
        ]
        entries.append(
            {
                **known,
                "canonical": bool(matched),
                "canonical_project_ids": sorted(p["project_id"] for p in matched),
                "in_p3_staging": any(
                    _mentions(s.get("concessionaire_name", "")) for s in staging
                ),
                "contract_rows": len(op_contracts),
                "contract_value_documented": round(contract_value, 2),
                # Only a site-extent concession can resolve to a point. The rest
                # are honestly unlocatable at municipality granularity, which is
                # a property of the asset, not a data gap to be closed.
                "locatable": known["spatial_extent"] == "site",
                "has_municipality": any(p.get("municipality_id") for p in matched),
                "federates_location": bool(federated),
            }
        )

    covered = [e for e in entries if e["canonical"]]
    locatable = [e for e in entries if e["locatable"]]
    return {
        "producer_script": "scripts/build_ppp_coverage.py",
        "source_inputs": [PROJECTS, P3_STAGING, CONCESSION_CONTRACTS],
        "known_concessions": len(entries),
        "canonical_concessions": len(covered),
        "concessions_with_documented_contracts": sum(1 for e in entries if e["contract_rows"]),
        "locatable_concessions": len(locatable),
        "concessions_federating_a_location": sum(1 for e in entries if e["federates_location"]),
        "canonical_ppp_project_rows": len(ppp_projects),
        "blocked_sources": [
            {
                "source_id": "prasa_completed_projects_ppp",
                "blocking_reason": "completed_projects_AAA.pdf is not in the repository",
            },
            {
                "source_id": "prasa_consulting_engineer_ppp",
                "blocking_reason": "FY2024 CER_Final.pdf is not in the repository",
            },
        ],
        "concessions": entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the PPP coverage truth file.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="print without writing")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = build_report(root)
    if not args.check:
        out = root / OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "concessions"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
