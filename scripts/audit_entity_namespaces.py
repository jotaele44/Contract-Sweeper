#!/usr/bin/env python3
"""Compare entity namespace products without treating name overlap as identity.

The audit computes INTERSECTION, A_ONLY, B_ONLY, UNION, and
SYMMETRIC_DIFFERENCE over normalized discovery keys. Results are explicitly
``CANDIDATE_NOT_IDENTITY`` unless the products share a stable authoritative
identifier outside this name-universe comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from moneysweep.runtime.name_normalization import normalize_name

DEFAULT_PRODUCTS = (
    ("entity_master", "data/reference/entity_master.csv", "canonical_name"),
    ("entity_hierarchy", "data/staging/processed/enrichment/entity_hierarchy.csv", "vendor_name"),
    ("entity_profiles", "data/staging/processed/pr_entity_profiles.csv", "recipient_name"),
)


@dataclass(frozen=True)
class ProductKeys:
    path: str
    field: str
    exists: bool
    keys: set[str]


def _keys(path: Path, field: str) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            key = normalize_name(row.get(field) or "")
            if key:
                out.add(key)
    return out


def compare_sets(a: set[str], b: set[str]) -> dict[str, object]:
    intersection = a & b
    a_only = a - b
    b_only = b - a
    union = a | b
    symmetric_difference = a ^ b
    return {
        "classification": "CANDIDATE_NOT_IDENTITY",
        "warning": "Normalized-name set overlap is discovery evidence only; it never proves canonical identity.",
        "A_count": len(a),
        "B_count": len(b),
        "INTERSECTION_count": len(intersection),
        "A_ONLY_count": len(a_only),
        "B_ONLY_count": len(b_only),
        "UNION_count": len(union),
        "SYMMETRIC_DIFFERENCE_count": len(symmetric_difference),
        "INTERSECTION": sorted(intersection),
        "A_ONLY": sorted(a_only),
        "B_ONLY": sorted(b_only),
    }


def audit(root: Path, products: Iterable[tuple[str, str, str]]) -> dict[str, object]:
    loaded: dict[str, ProductKeys] = {}
    for label, rel_path, field in products:
        path = root / rel_path
        loaded[label] = ProductKeys(
            path=rel_path,
            field=field,
            exists=path.exists(),
            keys=_keys(path, field),
        )
    comparisons: dict[str, object] = {}
    labels = list(loaded)
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            comparisons[f"{left}__vs__{right}"] = compare_sets(
                loaded[left].keys,
                loaded[right].keys,
            )
    return {
        "status": "AUDIT_ONLY",
        "canonical_identity_authority": "data/reference/entity_master.csv::entity_id (ENT_*)",
        "namespace_rules": {
            "ENT_*": "canonical internal identity",
            "UEI/CAGE/DUNS/EIN/CIK": "external identifiers attached to a canonical target",
            "normalized_name": "discovery key only",
            "PREPA specialized IDs": "domain-local IDs requiring explicit canonical bridge",
        },
        "products": {
            label: {
                "path": item.path,
                "field": item.field,
                "exists": item.exists,
                "key_count": len(item.keys),
            }
            for label, item in loaded.items()
        },
        "comparisons": comparisons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="reports/entity_namespace_adjudication.json")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    payload = audit(root, DEFAULT_PRODUCTS)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
