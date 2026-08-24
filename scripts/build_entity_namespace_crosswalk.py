#!/usr/bin/env python3
"""Build a fail-closed crosswalk from legacy/specialized entity products to ENT_*.

Only canonical names and committed authoritative aliases can resolve. Review
collisions cause a non-zero exit in ``--check`` mode. Name-only rows with no
canonical binding remain CANDIDATE_NOT_IDENTITY and are preserved.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import cast

from moneysweep.investigate.crosswalk import (
    NamespaceBridgeRecord,
    bridge_csv,
    bridge_prepa_graph,
)
from moneysweep.investigate.resolver import CanonicalEntityIndex

PRODUCTS = (
    (
        "entity_hierarchy",
        "data/staging/processed/enrichment/entity_hierarchy.csv",
        ("vendor_name", "parent_name"),
        ("uei", "parent_uei"),
    ),
    (
        "entity_profiles",
        "data/staging/processed/pr_entity_profiles.csv",
        ("recipient_name", "np_name", "med_provider_name", "bank_name"),
        (),
    ),
)


def build(root: Path, prepa_graph: str | None = None) -> dict[str, object]:
    index = CanonicalEntityIndex(root=root)
    records: list[NamespaceBridgeRecord] = []
    for namespace, rel_path, name_fields, id_fields in PRODUCTS:
        records.extend(
            bridge_csv(
                index,
                path=root / rel_path,
                namespace=namespace,
                name_fields=name_fields,
                id_fields=id_fields,
            )
        )
    if prepa_graph:
        records.extend(bridge_prepa_graph(index, root / prepa_graph))

    collisions = [record for record in records if record.bridge_status == "REVIEW"]
    counts: dict[str, int] = {}
    for record in records:
        counts[record.bridge_status] = counts.get(record.bridge_status, 0) + 1
    index_audit = index.audit()
    index_collision_count = int(index_audit["identity_collision_count"])
    return {
        "canonical_identity_authority": "data/reference/entity_master.csv::entity_id (ENT_*)",
        "record_count": len(records),
        "status_counts": counts,
        "unadjudicated_identity_collision_count": len(collisions) + index_collision_count,
        "canonical_index_audit": index_audit,
        "records": [record.to_dict() for record in records],
    }


def write_csv(payload: dict[str, object], path: Path) -> None:
    rows = cast(list[dict[str, object]], payload.get("records") or [])
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_namespace",
        "source_record_id",
        "source_name",
        "normalized_name",
        "bridge_status",
        "canonical_entity_id",
        "canonical_name",
        "match_method",
        "candidates",
        "source_path",
        "source_row",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            public = dict(row)
            candidates = cast(list[str], public.get("candidates") or [])
            public["candidates"] = "|".join(candidates)
            writer.writerow({key: public.get(key, "") for key in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--prepa-graph", default=None)
    parser.add_argument("--output", default="reports/entity_namespace_crosswalk.json")
    parser.add_argument("--csv", default="reports/entity_namespace_crosswalk.csv")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    payload = build(root, args.prepa_graph)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(payload, root / args.csv)
    summary = {key: value for key, value in payload.items() if key != "records"}
    print(json.dumps(summary, indent=2))
    collision_count = int(payload["unadjudicated_identity_collision_count"])
    if args.check and collision_count != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
