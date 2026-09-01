"""Build the FOIA / public-records priority queue (Gate ``foia``, item ``foia_tracker``).

A schema-locked request tracker whose targets are derived from the project's own
unmet-source gaps: each row is a public-records request for a source that the
pipeline needs but cannot materialize in-sandbox (credentialed exports,
key-gated APIs, manual dropzones). The authority is a curated seed
(``data/reference/foia_priority_queue_seed.csv``) keyed by ``source_id``; the
producer validates every target against ``reports/source_registry_status.csv``.
Historical requests are never dropped when another acquisition path materializes
their target: they become evidence-backed ``SUPERSEDED`` records, or remain
``OPEN`` with an explicit residual scope not covered by that materialization.

Pure, deterministic, no network. Reuses ``name_hash`` and the stdlib schema
validator (no ``jsonschema`` dep).

CLI::

    python scripts/build_foia_tracker.py            # write the CSV + manifest
    python scripts/build_foia_tracker.py --check     # validate without writing
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.runtime.canonical_ids import name_hash
from moneysweep.validation.canonical_v1_schema import validate_row

REPO_ROOT = Path(__file__).resolve().parents[1]

SEED = "data/reference/foia_priority_queue_seed.csv"
SOURCE_STATUS = "reports/source_registry_status.csv"
OUT = "reports/foia_priority_queue.csv"
MANIFEST_OUT = "data/manifests/foia_priority_queue.json"
SCHEMA = "schemas/foia_request.schema.json"
SOURCE_ID = "foia_priority_queue_seed"
EVIDENCE_TIER = "T2"
CONFIDENCE = 0.8

COLUMNS = [
    "request_id",
    "target_source_id",
    "target_agency",
    "jurisdiction",
    "record_type",
    "statute",
    "request_status",
    "tracking_state",
    "residual_gap",
    "resolution_evidence",
    "priority",
    "rationale",
    "evidence_tier",
    "confidence",
    "notes",
]


def _load_schema(root: Path) -> dict[str, Any]:
    return json.loads((root / SCHEMA).read_text(encoding="utf-8"))


def _read(root: Path, rel: str) -> list[dict[str, str]]:
    with (root / rel).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _source_status_index(root: Path) -> dict[str, str]:
    """Map source_id -> pipeline_status from the source registry status report."""
    return {
        r["source_id"]: (r.get("pipeline_status") or "").strip() for r in _read(root, SOURCE_STATUS)
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_rows(root: Path | None = None) -> list[dict[str, Any]]:
    """Return FOIA request rows from the curated seed."""
    root = root or REPO_ROOT
    status = _source_status_index(root)
    rows: list[dict[str, Any]] = []
    for ref in _read(root, SEED):
        source_id = (ref.get("target_source_id") or "").strip()
        record_type = (ref.get("record_type") or "").strip()
        rows.append(
            {
                "request_id": f"FOIA_{name_hash(source_id + '|' + record_type)}",
                "target_source_id": source_id,
                "target_agency": (ref.get("target_agency") or "").strip(),
                "jurisdiction": (ref.get("jurisdiction") or "").strip(),
                "record_type": record_type,
                "statute": (ref.get("statute") or "").strip(),
                "request_status": (ref.get("request_status") or "planned").strip(),
                "tracking_state": (ref.get("tracking_state") or "OPEN").strip(),
                "residual_gap": (ref.get("residual_gap") or "").strip(),
                "resolution_evidence": (ref.get("resolution_evidence") or "").strip(),
                "priority": (ref.get("priority") or "").strip(),
                "rationale": (ref.get("rationale") or "").strip(),
                "evidence_tier": EVIDENCE_TIER,
                "confidence": CONFIDENCE,
                "notes": "",
                "_source_status": status.get(source_id),
            }
        )
    return rows


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def check(rows: list[dict[str, Any]], root: Path | None = None) -> list[str]:
    """Return a list of problems (empty == valid)."""
    root = root or REPO_ROOT
    problems: list[str] = []
    if not rows:
        problems.append("no FOIA requests produced")
    ids = [r["request_id"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate request_id values present")
    targets = [r["target_source_id"] for r in rows]
    if len(set(targets)) != len(targets):
        problems.append("duplicate target_source_id values present")
    schema = _load_schema(root)
    for i, row in enumerate(rows, start=1):
        # Referential integrity and preservation-first lifecycle classification.
        st = row.get("_source_status")
        if st is None:
            problems.append(
                f"row {i}: target {row['target_source_id']!r} not found in source registry status"
            )
        tracking = row.get("tracking_state")
        residual = str(row.get("residual_gap") or "").strip()
        evidence = str(row.get("resolution_evidence") or "").strip()
        if tracking == "SUPERSEDED":
            if st != "fully_materialized":
                problems.append(
                    f"row {i}: SUPERSEDED target {row['target_source_id']!r} is not fully_materialized"
                )
            if residual:
                problems.append(f"row {i}: SUPERSEDED request must not retain a residual_gap")
            if not evidence:
                problems.append(f"row {i}: SUPERSEDED request requires resolution_evidence")
            else:
                evidence_path = root / evidence
                expected_prefix = f"data/manifests/{row['target_source_id']}/"
                if Path(evidence).is_absolute() or not evidence.startswith(expected_prefix):
                    problems.append(f"row {i}: resolution_evidence must be under {expected_prefix}")
                elif not evidence_path.is_file():
                    problems.append(f"row {i}: resolution_evidence does not exist: {evidence}")
                else:
                    try:
                        manifest = json.loads(evidence_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        problems.append(f"row {i}: invalid resolution_evidence {evidence}: {exc}")
                    else:
                        if manifest.get("source_id") != row["target_source_id"]:
                            problems.append(
                                f"row {i}: evidence source_id does not match {row['target_source_id']!r}"
                            )
                        files = manifest.get("files")
                        if not isinstance(files, list) or not files:
                            problems.append(f"row {i}: evidence manifest has no files")
                        else:
                            for file_row in files:
                                digest = str(file_row.get("sha256") or "")
                                relative_path = str(file_row.get("relative_path") or "")
                                if int(file_row.get("row_count") or 0) <= 0:
                                    problems.append(f"row {i}: evidence file has no data rows")
                                if len(digest) != 64 or any(
                                    c not in "0123456789abcdef" for c in digest
                                ):
                                    problems.append(f"row {i}: evidence file has invalid sha256")
                                payload_path = root / relative_path
                                if not relative_path:
                                    problems.append(f"row {i}: evidence file has no relative_path")
                                elif (
                                    payload_path.is_file()
                                    and len(digest) == 64
                                    and _sha256(payload_path) != digest
                                ):
                                    problems.append(
                                        f"row {i}: evidence payload sha256 mismatch: {relative_path}"
                                    )
        elif tracking == "OPEN":
            if st == "fully_materialized" and not residual:
                problems.append(f"row {i}: fully_materialized OPEN target requires a residual_gap")
            if evidence:
                problems.append(f"row {i}: OPEN request must not claim resolution_evidence")
        for msg in validate_row(_public_row(row), schema):
            problems.append(f"row {i} ({row.get('target_source_id')!r}): {msg}")
    return problems


def _write(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(_public_row(r) for r in rows)


def build(root: Path | None = None) -> dict[str, Any]:
    """Build, validate, and write the FOIA priority queue CSV + manifest."""
    root = root or REPO_ROOT
    rows = build_rows(root)
    problems = check(rows, root)
    if problems:
        raise ValueError("foia_tracker check failed: " + "; ".join(problems))
    _write(rows, root / OUT)
    manifest = {
        "producer_script": "scripts/build_foia_tracker.py",
        "producer_phase": "TOP_FORM_FOIA_TRACKER",
        "schema": SCHEMA,
        "source_inputs": [SEED, SOURCE_STATUS],
        "output": OUT,
        "row_count": len(rows),
        "jurisdictions": sorted({r["jurisdiction"] for r in rows}),
        "priorities": sorted({r["priority"] for r in rows}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = root / MANIFEST_OUT
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the FOIA / public-records priority queue.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="Validate without writing.")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.check:
        rows = build_rows(root)
        problems = check(rows, root)
        print(
            json.dumps({"ok": not problems, "row_count": len(rows), "problems": problems}, indent=2)
        )
        return 0 if not problems else 1
    print(json.dumps(build(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
