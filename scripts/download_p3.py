"""
Download Puerto Rico P3 Authority (Public-Private Partnerships) contract data.

The P3 Authority manages major infrastructure concessions post-Maria:
  - PRASA water/wastewater system (Operation and Maintenance agreement)
  - Luis Muñoz Marín International Airport (Aerostar concession)
  - PR Highway and Transportation Authority (Metropistas, PR-22/PR-5)
  - Luma Energy (PREPA T&D system operation — handled by download_prepa_contracts.py)
  - Education facilities public-private partnerships

These are PR-government-issued but receive federal funding and are crucial
for understanding the complete infrastructure-contractor control map.

Sources tried in order:
  1. P3 Authority portal (p3.pr.gov) — HTML scraping of project listings
  2. AAFAF P3 disclosure documents
  3. USASpending known P3 recipients with PR place of performance

Output:
  data/staging/processed/pr_p3_contracts.csv   (raw scrape, gitignored)
  data/reference/pr_p3_concessions.csv         (promoted, committed; --promote)

The raw output is gitignored working data. scripts/ingest_projects.py reads the
*promoted* file instead, so the canonical projects table stays reproducible from
a clean checkout — promotion is a deliberate reviewed step rather than whatever
the last local scrape happened to produce.

Usage:
  python3 scripts/download_p3.py [--force] [--promote]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from scripts.config import PROJECT_ROOT, setup_logging

P3_BASE = "https://p3.pr.gov"
AAFAF_P3_URL = "https://www.aafaf.pr.gov/p3/"
REFERENCE_OUT = "data/reference/pr_p3_concessions.csv"

PAGE_SLEEP = 0.5
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]

P3_COLUMNS = [
    "project_id",
    "project_name",
    "sector",
    "concessionaire_name",
    "concessionaire_normalized",
    "contract_value",
    "term_years",
    "award_date",
    "financial_close_date",
    "federal_funding_flag",
    "status",
    "municipality",
    "spatial_extent",
    "canonical_project_number",
    "source_doc",
]

# How much of Puerto Rico a concession physically covers. This is the field the
# spatial producer keys its geometry decision off, so it must distinguish
# "we don't know" from "the asset genuinely has no single site":
#
#   site       one physical location -> ``municipality`` is set, resolves to a point
#   corridor   a route spanning municipalities -> resolves to a LineString
#   islandwide a territory-wide system -> no single point exists
#   unknown    not yet determined (portal-scraped rows start here)
#
# ``municipality`` is deliberately left empty for corridor/islandwide/unknown.
# Defaulting those to San Juan because the operator is headquartered there is
# the exact distortion scripts/run_contract_finance_geo_reasoning.py's
# san_juan_hq_bias_report exists to catch.
SPATIAL_EXTENTS = {"site", "corridor", "islandwide", "unknown"}

# ``canonical_project_number`` names the reference-seed project_number this row
# describes, when the two surfaces cover the same concession under different
# names ("LUMA Energy T&D System" here vs "LUMA Energy Transmission and
# Distribution Operation" in the seed). ingest_projects.py dedupes on it. An
# explicit crosswalk is used rather than fuzzy name matching because a false
# match silently merges two real concessions, and a missed one silently
# duplicates a project across the canonical table.

# Known P3 projects with verified data (used as seed if scraping fails)
KNOWN_P3_PROJECTS = [
    {
        "project_id": "P3-001",
        "project_name": "Luis Muñoz Marín Airport",
        "sector": "transport",
        "concessionaire_name": "Aerostar Airport Holdings LLC",
        "contract_value": "2400000000",
        "term_years": "40",
        "award_date": "2013-02-27",
        "financial_close_date": "2013-02-27",
        "federal_funding_flag": "Y",
        "status": "active",
        # LMM is physically in Carolina, not San Juan, despite the common name.
        "municipality": "Carolina",
        "spatial_extent": "site",
        "canonical_project_number": "",
        "source_doc": "known_p3_seed",
    },
    {
        "project_id": "P3-002",
        "project_name": "PR-22 and PR-5 Highway",
        "sector": "transport",
        "concessionaire_name": "Metropistas",
        "contract_value": "1100000000",
        "term_years": "40",
        "award_date": "2011-01-01",
        "financial_close_date": "2011-01-01",
        "federal_funding_flag": "Y",
        "status": "active",
        # PR-22 runs San Juan -> Hatillo and PR-5 links Bayamón/Toa Alta; the
        # concession is the route, not any one municipality.
        "municipality": "",
        "spatial_extent": "corridor",
        "canonical_project_number": "HTA-PPP-2011",
        "source_doc": "known_p3_seed",
    },
    {
        "project_id": "P3-003",
        "project_name": "PRASA O&M Agreement",
        "sector": "water",
        "concessionaire_name": "Veolia Water Puerto Rico",
        "contract_value": "500000000",
        "term_years": "10",
        "award_date": "2009-01-01",
        "financial_close_date": "2009-01-01",
        "federal_funding_flag": "Y",
        "status": "expired",
        # Island-wide water/wastewater system operation.
        "municipality": "",
        "spatial_extent": "islandwide",
        "canonical_project_number": "",
        "source_doc": "known_p3_seed",
    },
    {
        "project_id": "P3-004",
        "project_name": "LUMA Energy T&D System",
        "sector": "energy",
        "concessionaire_name": "LUMA Energy LLC",
        "contract_value": "2000000000",
        "term_years": "15",
        "award_date": "2020-06-22",
        "financial_close_date": "2021-06-01",
        "federal_funding_flag": "Y",
        "status": "active",
        # Island-wide transmission & distribution grid.
        "municipality": "",
        "spatial_extent": "islandwide",
        "canonical_project_number": "PREPA-TD-OMA-2020",
        "source_doc": "known_p3_seed",
    },
    {
        "project_id": "P3-005",
        "project_name": "PREPA Generation Privatization",
        "sector": "energy",
        "concessionaire_name": "Genera PR LLC",
        "contract_value": "3500000000",
        "term_years": "20",
        "award_date": "2023-01-01",
        "financial_close_date": "2023-06-01",
        "federal_funding_flag": "Y",
        "status": "active",
        # Legacy generation fleet spread across several plant sites.
        "municipality": "",
        "spatial_extent": "islandwide",
        "canonical_project_number": "PREPA-GEN-OMA-2023",
        "source_doc": "known_p3_seed",
    },
    {
        "project_id": "P3-006",
        "project_name": "Teodoro Moscoso Bridge Toll Concession",
        "sector": "transport",
        "concessionaire_name": "Autopistas de Puerto Rico y Compañía",
        # No single documented total concession value — only line-item ACT
        # contract amounts exist (data/reference/pr_ppp_concession_contracts.csv),
        # and those price individual services, not the concession itself. Left
        # empty rather than substituting a line-item figure for a concession
        # total the source never states.
        "contract_value": "",
        "term_years": "",
        # Earliest ACT contract start (1992-000228 C/D) documenting the
        # concession; no single award date is otherwise on record.
        "award_date": "1991-12-20",
        "financial_close_date": "",
        "federal_funding_flag": "",
        "status": "active",
        # The bridge itself sits in San Juan.
        "municipality": "San Juan",
        "spatial_extent": "site",
        "canonical_project_number": "",
        "source_doc": "known_p3_seed",
    },
]


def parse_records(records: list[dict]) -> pd.DataFrame:
    """Map raw P3 portal records to the canonical schema.
    Pure — no network or I/O. Live fetch still needs egress to scrape the
    P3 Authority portal (p3.pr.gov) and AAFAF P3 page.
    """
    if not records:
        return pd.DataFrame(columns=P3_COLUMNS)
    processed = []
    for r in records:
        row = dict(r)
        if not row.get("concessionaire_normalized"):
            row["concessionaire_normalized"] = _normalize_name(
                str(row.get("concessionaire_name", ""))
            )
        processed.append(row)
    df = pd.DataFrame(processed)
    for col in P3_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[P3_COLUMNS]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "ContractSweeper/1.0 (PR P3 Authority contract research)",
            "Accept": "text/html,application/json",
        }
    )
    return s


def _get(session: requests.Session, url: str, params: dict, logger) -> requests.Response | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, params=params, timeout=60)
            if resp.status_code == 429:
                time.sleep(60)
                continue
            if 400 <= resp.status_code < 500:
                logger.warning(f"  HTTP {resp.status_code} for {url}")
                return None
            resp.raise_for_status()
            time.sleep(PAGE_SLEEP)
            return resp
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(f"  Attempt {attempt + 1} failed ({exc}) — retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"  All {MAX_RETRIES} attempts failed: {exc}")
    return None


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    n = re.sub(r"[^\w\s]", " ", name.upper())
    n = re.sub(r"\s+", " ", n).strip()
    suffixes = {"INC", "LLC", "LLP", "CORP", "CO", "LTD", "LP", "THE", "OF"}
    tokens = n.split()
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return " ".join(tokens)


def _scrape_p3_portal(session: requests.Session, logger) -> list[dict]:
    rows = []
    project_urls = [
        f"{P3_BASE}/en/projects/",
        f"{P3_BASE}/en/transactions/",
        f"{P3_BASE}/proyectos/",
    ]
    for url in project_urls:
        resp = _get(session, url, {}, logger)
        if not resp:
            continue
        # Extract project names and links
        links = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:project|transaction|proyecto)[^"\']*)["\'][^>]*>([^<]{5,200})</a>',
            resp.text,
            re.IGNORECASE,
        )
        logger.info(f"  P3 portal {url.split('/')[-2]}: {len(links)} project links found")
        # Only the (href, title) pair is genuinely associated — the regex
        # captured both from the same anchor. Page-wide sweeps for "$N" and for
        # sector words are NOT: indexing them by the link's position attaches
        # whichever dollar figure happens to appear i-th on the page to the i-th
        # project, which silently invents contract values. These rows now feed
        # canonical projects, so they are left empty for review rather than
        # guessed. Per-project values need a detail-page fetch, not a page sweep.
        for i, (href, title) in enumerate(links[:30]):
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) < 5:
                continue
            project_url = href if href.startswith("http") else f"{P3_BASE}{href}"
            rows.append(
                {
                    "project_id": f"P3-PORTAL-{i + 1:03d}",
                    "project_name": title,
                    "sector": "",
                    "concessionaire_name": "",
                    "concessionaire_normalized": "",
                    "contract_value": "",
                    "term_years": "",
                    "award_date": "",
                    "financial_close_date": "",
                    "federal_funding_flag": "",
                    "status": "active",
                    "municipality": "",
                    "spatial_extent": "unknown",
                    "source_doc": project_url,
                }
            )
        if rows:
            break
        time.sleep(PAGE_SLEEP)
    return rows


def _scrape_aafaf_p3(session: requests.Session, logger) -> list[dict]:
    """Scrape the AAFAF P3 disclosure page for concession references.

    AAFAF publishes P3 disclosure documents separately from the P3 Authority
    portal, so a concession missing from one often appears on the other. Only
    the anchor text and href are read — same restraint as the portal scraper.
    """
    rows: list[dict] = []
    resp = _get(session, AAFAF_P3_URL, {}, logger)
    if not resp:
        return rows
    links = re.findall(
        r'<a[^>]+href=["\']([^"\']+\.(?:pdf|xlsx?)|[^"\']*(?:p3|alianza|proyecto)[^"\']*)["\']'
        r"[^>]*>([^<]{5,200})</a>",
        resp.text,
        re.IGNORECASE,
    )
    logger.info(f"  AAFAF P3 page: {len(links)} disclosure links found")
    for i, (href, title) in enumerate(links[:30]):
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 5:
            continue
        doc_url = href if href.startswith("http") else f"https://www.aafaf.pr.gov{href}"
        rows.append(
            {
                "project_id": f"P3-AAFAF-{i + 1:03d}",
                "project_name": title,
                "sector": "",
                "concessionaire_name": "",
                "concessionaire_normalized": "",
                "contract_value": "",
                "term_years": "",
                "award_date": "",
                "financial_close_date": "",
                "federal_funding_flag": "",
                "status": "",
                "municipality": "",
                "spatial_extent": "unknown",
                "source_doc": doc_url,
            }
        )
    return rows


def run(root: Path | None = None, force: bool = False) -> dict:
    if root is None:
        root = PROJECT_ROOT
    root = Path(root)
    out_dir = root / "data" / "staging" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pr_p3_contracts.csv"

    logger = setup_logging("download_p3")

    if not force and out_path.exists():
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        if len(existing) > 0:
            logger.info(f"  Cached — {len(existing):,} rows in {out_path.name}")
            return {"rows": len(existing), "path": str(out_path), "status": "CACHED"}

    session = _session()
    all_rows: list[dict] = []

    logger.info("  Attempting to scrape P3 Authority portal...")
    portal_rows = _scrape_p3_portal(session, logger)
    all_rows.extend(portal_rows)

    # AAFAF publishes P3 disclosures separately from the P3 Authority portal, so
    # it is a second independent surface rather than a fallback for the first.
    logger.info("  Attempting to scrape AAFAF P3 disclosure page...")
    for row in _scrape_aafaf_p3(session, logger):
        if not any(
            r.get("project_name", "").lower() == row["project_name"].lower() for r in all_rows
        ):
            all_rows.append(row)

    # Always include known seed projects — they are well-documented and verified
    logger.info(f"  Adding {len(KNOWN_P3_PROJECTS)} known P3 projects (seed data)...")
    for seed in KNOWN_P3_PROJECTS:
        # Only add if not already captured from a scraped surface
        if not any(
            r.get("project_name", "").lower() == seed["project_name"].lower() for r in all_rows
        ):
            all_rows.append(seed)

    session.close()

    for r in all_rows:
        if "concessionaire_normalized" not in r or not r["concessionaire_normalized"]:
            r["concessionaire_normalized"] = _normalize_name(str(r.get("concessionaire_name", "")))

    df = pd.DataFrame(all_rows)
    for col in P3_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[P3_COLUMNS]
    df.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(f"  Written: {out_path.name} ({len(df):,} rows)")
    return {"rows": len(df), "path": str(out_path), "status": "OK"}


def promote(root: Path | None = None) -> dict:
    """Copy the raw scrape into the committed reference file ingest_projects reads.

    Deliberately separate from run(): a scrape is a candidate, and only a
    reviewed promotion makes it an input to the canonical table.
    """
    root = Path(root or PROJECT_ROOT)
    src = root / "data" / "staging" / "processed" / "pr_p3_contracts.csv"
    dest = root / REFERENCE_OUT
    if not src.exists():
        return {"rows": 0, "path": str(dest), "status": "NO_SOURCE"}
    df = pd.read_csv(src, dtype=str, low_memory=False).fillna("")
    for col in P3_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    df[P3_COLUMNS].to_csv(dest, index=False, encoding="utf-8")
    return {"rows": len(df), "path": str(dest), "status": "PROMOTED"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download PR P3 Authority contract data")
    parser.add_argument("--force", action="store_true", help="Re-download even if cached")
    parser.add_argument(
        "--promote",
        action="store_true",
        help=f"Copy the scrape into {REFERENCE_OUT} (the committed file ingest_projects reads)",
    )
    args = parser.parse_args()
    result = run(force=args.force)
    print(f"\nP3 contracts: {result['rows']:,} rows — {result['status']}")
    if args.promote:
        promoted = promote()
        print(f"Promoted to {REFERENCE_OUT}: {promoted['rows']:,} rows — {promoted['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
