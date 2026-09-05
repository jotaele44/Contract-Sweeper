#!/usr/bin/env python3
"""Build MoneySweep -> federation spatial binding candidates without fabricating geometry.

Input JSONL rows are financial/project records. The adapter emits candidate bindings
only from explicit spatial evidence supplied on the source row. It never creates
coordinates, centroids, nearest-facility identities, or name-only identity bindings.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FORBIDDEN_METHODS = {
    "NAME_ONLY", "NORMALIZED_NAME_ONLY", "COUNT_EQUALITY", "NEAREST_ONLY",
    "PROXIMITY_ONLY", "SAME_CATEGORY", "SOURCE_ABSENCE", "MUNICIPIO_CENTROID",
    "PIXEL_GRID", "PLACEHOLDER_COORDINATE",
}
ALLOWED_CARDINALITY = {"1:1", "1:N", "N:1", "N:N", "0:1", "UNRESOLVED"}


def adapt(row: dict) -> dict:
    record_id = str(row.get("record_id") or row.get("project_id") or "").strip()
    if not record_id:
        raise ValueError("record_id/project_id is required")
    evidence = row.get("spatial_evidence") or []
    candidates = []
    for item in evidence:
        method = str(item.get("method") or "UNKNOWN").upper()
        canonical_id = item.get("canonical_id")
        cardinality = item.get("cardinality", "UNRESOLVED")
        if cardinality not in ALLOWED_CARDINALITY:
            raise ValueError(f"invalid cardinality {cardinality!r} for {record_id}")
        state = "CANDIDATE_NOT_IDENTITY"
        reason = None
        if method in FORBIDDEN_METHODS:
            reason = f"forbidden sole identity method: {method}"
        elif not canonical_id:
            reason = "no canonical_id supplied"
        elif method in {"STABLE_ID", "AUTHORITATIVE_BINDING"}:
            state = "PROVISIONAL"
        else:
            reason = "evidence retained as candidate; independent adjudication required"
        candidates.append({
            "record_id": record_id,
            "canonical_id": canonical_id,
            "method": method,
            "cardinality": cardinality,
            "identity_state": state,
            "reason": reason,
            "source_reference": item.get("source_reference"),
        })
    if not candidates:
        candidates.append({
            "record_id": record_id,
            "canonical_id": None,
            "method": "NONE",
            "cardinality": "0:1",
            "identity_state": "UNRESOLVED",
            "reason": "no authoritative spatial evidence supplied",
            "source_reference": None,
        })
    return {"record_id": record_id, "bindings": candidates}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    rows = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(adapt(json.loads(line)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    print(f"PASS records={len(rows)}; geometry_created=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
