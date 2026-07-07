"""Consolidated financial + political source audit (2026-07-07 snapshot).

Read-only re-projection that answers three operator questions in one deliverable:

  1. To what extent is each financial / political source implemented?
  2. Are we at 100% of the financial + political datasets? (No — see the .md.)
  3. What does each source still need to be fully prepared, and how do we get there?

It builds directly on ``scripts/build_financial_source_audit.build_rows`` so it can
never drift from the materialization gate, then layers on:

  - a coarse ``needs`` category (the single thing blocking full preparation), and
  - a concrete ``remediation_step`` (how to clear it),

both derived deterministically from the existing audit bucket + registry auth +
manual drop-zone — no new classifier, no network, no registry edits.

Output (deterministic, byte-identical on re-run):
  reports/financial_political_source_audit_2026-07-07.csv

The narrative companion (``.md``) is authored by hand from this CSV plus the
existing coverage-audit reports; regenerate the CSV with:

    python3 scripts/build_financial_political_audit_20260707.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_financial_source_audit import build_rows  # noqa: E402

OUT_CSV = REPO_ROOT / "reports" / "financial_political_source_audit_2026-07-07.csv"

# Political / influence families, surfaced as a first-class flag because the
# operator asked about the political datasets specifically.
POLITICAL_FAMILIES = {
    "political_finance",
    "lobbying",
    "territorial_legislation",
}

# audit_status bucket -> (needs, remediation_step). One coarse blocker per source
# plus the concrete action that clears it. Key-gated and manual rows are refined
# below with the specific key name / drop-zone.
NEEDS_BY_BUCKET = {
    "wired_materializing": (
        "none",
        "Producing output on disk now; keep on its update cadence.",
    ),
    "wired_offline_ready": (
        "run_offline",
        "Run the producer once; it materializes from a committed input (no key/network).",
    ),
    "wired_ready_unmaterialized": (
        "egress",
        "Run the producer in an egress-enabled environment (sandbox blocks HTTPS with 403).",
    ),
    "wired_needs_key": (
        "api_key",
        "Set the API key in .env, then run the producer in an egress-enabled environment.",
    ),
    "wired_not_set_to_materialize": (
        "design_decision",
        "Produces nothing by design (deferred stub / semantic duplicate); keep or retire.",
    ),
    "queued_manual": (
        "operator_file",
        "Operator drops the manual export file, then run the parser/ingest step.",
    ),
    "queued_scraper": (
        "scraper",
        "Build a scraping adapter for the PR-gov HTML/PDF surface, then run it.",
    ),
    "broken": (
        "fix_producer",
        "Repair the producer (missing module / import error / no entrypoint).",
    ),
    "not_considered": (
        "registry_intake",
        "No registry entry yet; create a source definition + producer.",
    ),
}


def _refine(row: dict, needs: str, step: str) -> tuple[str, str, str]:
    """Sharpen the bucket action, but keep ``needs`` COARSE.

    The specific key / committed-input path goes in ``needs_detail`` so that
    grouping the CSV by ``needs`` reproduces the documented buckets (e.g. the
    single ``api_key`` bucket of 11) without special prefix parsing. Returns
    ``(needs, remediation_step, needs_detail)``.
    """
    if needs == "api_key" and row.get("needs_key"):
        key = row["needs_key"]
        return (
            needs,
            f"Set {key} in .env, then run "
            f"`{row.get('producer_basename') or 'the producer'}` with egress.",
            f"api_key:{key}",
        )
    if needs in {"operator_file", "run_offline"} and row.get("offline_input"):
        # A committed input turns a manual queue into an offline run — a genuine
        # bucket correction, so ``needs`` legitimately changes here.
        return (
            "run_offline",
            f"Committed input present ({row['offline_input']}); run "
            f"`{row.get('producer_basename') or 'the producer'}` to materialize.",
            row["offline_input"],
        )
    return needs, step, ""


def build() -> list[dict]:
    out: list[dict] = []
    for r in build_rows():
        needs, step = NEEDS_BY_BUCKET.get(r["audit_status"], ("unknown", ""))
        needs, step, detail = _refine(r, needs, step)
        out.append(
            {
                "source_id": r["source_id"],
                "family": r["family"],
                "financial_domain": r["financial_domain"],
                "is_financial": r["is_financial"],
                "is_political": r["family"] in POLITICAL_FAMILIES,
                "required": r["required"],
                "audit_status": r["audit_status"],
                "automatable": r["automatable"],
                "producer_importable": r["producer_importable"],
                "producer_script": r["producer_script"],
                "needs": needs,
                "needs_detail": detail,
                "remediation_step": step,
                "blocker": r["blocker"],
            }
        )
    return out


def main() -> int:
    rows = build()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    registry_rows = [r for r in rows if r["audit_status"] != "not_considered"]
    print(f"wrote {OUT_CSV.relative_to(REPO_ROOT)} ({len(rows)} rows)")
    print(
        f"  registry sources: {len(registry_rows)}  (+{len(rows) - len(registry_rows)} not_considered)"
    )
    print(f"  political/influence sources: {sum(1 for r in rows if r['is_political'])}")
    print("  needs breakdown:")
    for need, n in Counter(r["needs"] for r in rows).most_common():
        print(f"    {need:16} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
