"""Ingest PR public infrastructure projects into Canonical v1 ``projects.csv`` (WS-G).

Two source surfaces, read in order:

1. ``data/reference/pr_infrastructure_projects.csv`` — the committed reference
   seed of well-documented public PR infrastructure programs and P3 concessions,
   whose ``lead_entity`` is the **public agency** that owns the asset.
2. ``data/reference/pr_p3_concessions.csv`` — promoted P3 Authority / AAFAF
   concessions, whose lead is the **concessionaire** operating under the
   agreement. Every row from here is ``project_type=ppp`` by construction.

The second surface used to be a dead end: ``download_p3.py`` wrote a staging CSV
and nothing read it, so scraped and seeded concessions never met. Reading both
here is what makes "every known PPP" a single canonical table rather than two
half-lists.

Note the second input is the *promoted reference* file, not the scraper's raw
staging output. ``data/staging/processed/`` is gitignored, so an ingester reading
it would build a canonical table that cannot be reproduced from a clean checkout
— the committed projects.csv would not match what CI regenerates. Promotion
(``download_p3.py --promote``) is therefore a deliberate reviewed step, which is
also what the repo's "manual sources stay staged until the gates pass" rule
already asks for.

Each project's ``lead_entity`` resolves to an existing canonical entity (and
optional ``municipality`` to an existing municipality node) via the shared
resolver in ``scripts/build_edges.py``.
Evidence-first: one accepted Tier-T2 evidence row per project. Only projects whose
lead entity resolves are written (``lead_entity_id`` references must not dangle);
others are reported as skips.

Projects are the anchor for ``LOCATED_IN`` (project -> municipality) and for
operator relationships (e.g. LUMA / Genera / Metropistas) that ``build_edges.py``
derives, so an operator edge attaches to the project rather than to an agency.

Roadmap: WS-G, tasks T97-T108 (seed subset). Stdlib only.

CLI::

    python scripts/ingest_projects.py            # write projects + evidence
    python scripts/ingest_projects.py --check     # summarize without writing
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

from moneysweep.runtime.canonical_ids import project_id
from scripts.build_edges import build_resolver, resolve
from scripts.build_evidence import Evidence, make_evidence, merge_evidence

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_SOURCE = "data/reference/pr_infrastructure_projects.csv"
P3_SOURCE = "data/reference/pr_p3_concessions.csv"
PROJECTS_OUT = "data/canonical_v1/projects.csv"
EVIDENCE_OUT = "data/canonical_v1/evidence.csv"
MANIFEST_OUT = "data/manifests/canonical_v1/projects.json"
SOURCE_NAME = "PR Infrastructure Projects (reference seed)"
P3_SOURCE_NAME = "PR P3 Authority / AAFAF concessions (promoted)"

VALID_TYPES = {"infrastructure", "recovery", "ppp", "real_estate", "other"}
VALID_EXTENTS = {"site", "corridor", "islandwide", "unknown"}

PROJECT_COLUMNS = [
    "project_id",
    "project_name",
    "project_number",
    "project_type",
    "lead_entity_id",
    "municipality_id",
    "funding_source_id",
    "total_value",
    "currency",
    "status",
    "start_date",
    "end_date",
    "spatial_extent",
    "confidence",
    "evidence_id",
    "review_status",
    "notes",
]


def _norm_name(name: str) -> str:
    """Loose key for cross-surface duplicate detection."""
    return " ".join((name or "").upper().split())


def _read_seed_records(root: Path) -> list[dict[str, str]]:
    """Records from the reference seed, already in the internal record shape."""
    path = root / PROJECTS_SOURCE
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            {
                **rec,
                "_source_path": PROJECTS_SOURCE,
                "_source_name": SOURCE_NAME,
                "_row_ref": f"row {i}",
            }
            for i, rec in enumerate(csv.DictReader(fh), start=2)
        ]


def _read_p3_records(root: Path) -> list[dict[str, str]]:
    """Records from the P3 acquisition surface, mapped to the internal shape.

    The P3 CSV names its columns for a concession, not a project: the lead is the
    ``concessionaire_name`` operating the asset, and ``contract_value`` is the
    project's total value. ``term_years`` is deliberately *not* turned into an
    ``end_date`` — deriving one would manufacture a date the source never stated.
    """
    path = root / P3_SOURCE
    if not path.exists():
        return []
    records: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for i, rec in enumerate(csv.DictReader(fh), start=2):
            concessionaire = (rec.get("concessionaire_name") or "").strip()
            name = (rec.get("project_name") or "").strip()
            source_doc = (rec.get("source_doc") or "").strip()
            extent = (rec.get("spatial_extent") or "").strip() or "unknown"
            records.append(
                {
                    "project_name": name,
                    "project_number": (rec.get("project_id") or "").strip(),
                    "canonical_project_number": (rec.get("canonical_project_number") or "").strip(),
                    "project_type": "ppp",
                    "lead_entity": concessionaire,
                    "municipality": (rec.get("municipality") or "").strip(),
                    "spatial_extent": extent,
                    "total_value": (rec.get("contract_value") or "").strip(),
                    "currency": "USD",
                    "status": (rec.get("status") or "").strip(),
                    "start_date": (rec.get("award_date") or "").strip(),
                    "end_date": "",
                    "source_type": "web",
                    # Seed rows are hand-verified; portal/AAFAF rows are scraped.
                    "extraction_method": ("manual" if source_doc == "known_p3_seed" else "scrape"),
                    "claim": (
                        f"{name} is operated by {concessionaire} under a Puerto Rico "
                        f"public-private partnership agreement."
                        if concessionaire
                        else f"{name} is listed as a Puerto Rico public-private partnership."
                    ),
                    "_source_path": P3_SOURCE,
                    "_source_name": P3_SOURCE_NAME,
                    "_row_ref": f"row {i}",
                }
            )
    return records


def build_rows(root: Path | None = None) -> dict[str, Any]:
    """Build project rows (lead entity resolved) + evidence + skip report.

    Reads the reference seed first so its agency-led rows win any collision with
    the concessionaire-led P3 rows describing the same asset.
    """
    root = root or REPO_ROOT
    resolver = build_resolver(root)
    project_rows: list[dict[str, Any]] = []
    evidence_rows: list[Evidence] = []
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_numbers: set[str] = set()
    seen_names: set[str] = set()

    for rec in _read_seed_records(root) + _read_p3_records(root):
        source_path = rec["_source_path"]
        row_ref = rec["_row_ref"]
        name = (rec.get("project_name") or "").strip()
        ptype = (rec.get("project_type") or "").strip()
        number = (rec.get("project_number") or "").strip()
        lead = (rec.get("lead_entity") or "").strip()
        muni = (rec.get("municipality") or "").strip()
        extent = (rec.get("spatial_extent") or "").strip()
        reason = None
        if not name or ptype not in VALID_TYPES:
            reason = f"missing name or invalid project_type {ptype!r}"
        elif extent and extent not in VALID_EXTENTS:
            reason = f"invalid spatial_extent {extent!r}"
        lead_id = resolve(resolver, "Entity", lead) if not reason else None
        if not reason and lead_id is None:
            reason = f"unresolved lead_entity {lead!r}"
        if reason:
            skipped.append({"source": source_path, "row": row_ref, "reason": reason})
            continue

        # Cross-surface dedupe. The same concession appears in both the
        # agency-led seed and the concessionaire-led P3 export under different
        # names ("LUMA Energy T&D System" vs "LUMA Energy Transmission and
        # Distribution Operation"), and project_id() keys off the lead entity, so
        # neither the id nor the name catches the collision. The P3 export names
        # the seed row it duplicates in canonical_project_number; that explicit
        # crosswalk is the primary key, with exact number/name as a backstop.
        name_key = _norm_name(name)
        canonical_number = (rec.get("canonical_project_number") or "").strip()
        duplicate_of = None
        if canonical_number and canonical_number in seen_numbers:
            duplicate_of = canonical_number
        elif number and number in seen_numbers:
            duplicate_of = number
        elif name_key in seen_names:
            duplicate_of = name
        if duplicate_of:
            skipped.append(
                {
                    "source": source_path,
                    "row": row_ref,
                    "reason": f"duplicate of already-ingested project {duplicate_of!r}",
                }
            )
            continue

        muni_id = resolve(resolver, "Municipality", muni) if muni else ""
        if muni and not muni_id:
            skipped.append(
                {
                    "source": source_path,
                    "row": row_ref,
                    "reason": f"unresolved municipality {muni!r}",
                }
            )
            continue

        pid = project_id(lead, number or name)
        if pid in seen:
            continue
        seen.add(pid)
        if number:
            seen_numbers.add(number)
        seen_names.add(name_key)
        ev = make_evidence(
            source_type=(rec.get("source_type") or "web").strip(),
            source_name=rec["_source_name"],
            source_path_or_url=source_path,
            page_or_line_ref=row_ref,
            claim=(rec.get("claim") or f"{name} led by {lead}").strip(),
            extraction_method=(rec.get("extraction_method") or "manual").strip(),
            evidence_tier=(rec.get("evidence_tier") or "").strip() or None,
            review_status="accepted",
        )
        evidence_rows.append(ev)
        project_rows.append(
            {
                "project_id": pid,
                "project_name": name,
                "project_number": number,
                "project_type": ptype,
                "lead_entity_id": lead_id,
                "municipality_id": muni_id or "",
                "funding_source_id": "",
                "total_value": (rec.get("total_value") or "").strip(),
                "currency": (rec.get("currency") or "").strip(),
                "status": (rec.get("status") or "").strip(),
                "start_date": (rec.get("start_date") or "").strip(),
                "end_date": (rec.get("end_date") or "").strip(),
                "spatial_extent": extent,
                "confidence": ev.confidence,
                "evidence_id": ev.evidence_id,
                "review_status": "accepted",
                "notes": f"lead={lead}",
            }
        )
    return {"project_rows": project_rows, "evidence_rows": evidence_rows, "skipped": skipped}


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    if not rows:
        problems.append("no project rows produced")
    ids = [r["project_id"] for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate project_id values present")
    if any(r["project_type"] not in VALID_TYPES for r in rows):
        problems.append("invalid project_type present")
    if any(r.get("spatial_extent") and r["spatial_extent"] not in VALID_EXTENTS for r in rows):
        problems.append("invalid spatial_extent present")
    # A site-extent project claims one physical location, so it must name it.
    if any(r.get("spatial_extent") == "site" and not r.get("municipality_id") for r in rows):
        problems.append("spatial_extent=site without a resolved municipality_id")
    return problems


def _write(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=PROJECT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def ingest(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    built = build_rows(root)
    rows, evidence_rows = built["project_rows"], built["evidence_rows"]
    problems = check(rows)
    if problems:
        raise ValueError("project ingest check failed: " + "; ".join(problems))
    _write(rows, root / PROJECTS_OUT)
    evidence_manifest = merge_evidence(root / EVIDENCE_OUT, evidence_rows)
    type_counts: dict[str, int] = {}
    extent_counts: dict[str, int] = {}
    for r in rows:
        type_counts[r["project_type"]] = type_counts.get(r["project_type"], 0) + 1
        extent = r.get("spatial_extent") or "unset"
        extent_counts[extent] = extent_counts.get(extent, 0) + 1
    located = sum(1 for r in rows if r.get("municipality_id"))
    manifest = {
        "producer_script": "scripts/ingest_projects.py",
        "producer_phase": "CANONICAL_V1_PROJECTS_INGEST",
        "source_inputs": [PROJECTS_SOURCE, P3_SOURCE],
        "row_count": len(rows),
        "project_type_counts": type_counts,
        "spatial_extent_counts": extent_counts,
        "rows_with_municipality": located,
        "skipped_count": len(built["skipped"]),
        "skipped": built["skipped"],
        "evidence_rows_added": len(evidence_rows),
        "evidence_table_rows": evidence_manifest["row_count"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = root / MANIFEST_OUT
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest PR infrastructure projects into canonical_v1."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.check:
        built = build_rows(root)
        rows = built["project_rows"]
        problems = check(rows)
        print(
            json.dumps(
                {
                    "ok": not problems,
                    "row_count": len(rows),
                    "skipped": len(built["skipped"]),
                    "problems": problems,
                },
                indent=2,
            )
        )
        return 0 if not problems else 1
    print(json.dumps(ingest(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
