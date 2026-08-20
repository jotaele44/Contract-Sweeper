"""
Scrape the Registro de Demandas Civiles (RDC) from justicia1.justicia.pr.gov/rdc.

Under **Ley Núm. 1-2003** the Departamento de Justicia must publish every civil
claim filed against a government agency, instrumentality or municipality. The
registry renders as a plain server-side table carrying, per case, the amount
demanded and — once resolved — the amount actually awarded:

    Caso | Núm del Caso | Causa de Acción | Cuantía Reclamada |
    Cantidad Adjudicada | Resolución final | Fecha Resolución Final | Disposición

That is public money leaving the treasury through the courts rather than
through a contract, which nothing else in the source registry covers.

Roughly 44,700 cases over 7,451 pages at six rows a page. There is no API, no
bulk export and no JSON endpoint.

Three things about the endpoint shape this scraper:

* Paging is a plain query param (``?pg=N``). Unlike ASG's portal, requesting a
  page past the end does **not** clamp to the last page — it answers 200 with
  the table headers and an empty ``<tbody>``. So "no rows" is a reliable stop
  condition and no repeated-page backstop is needed. The declared last page is
  still read from the "Ultima" link when present, purely to log progress; that
  link is absent on out-of-range pages, so its absence is not an error.

* The table is walked with lxml directly rather than ``pandas.read_html``.
  read_html returns cell text only, and this scraper needs the ``Ver`` link's
  href: it is the exact route key the detail page is addressed by, and
  reconstructing it from the case-number column would guess at the site's
  encoding.

* **Núm del Caso is not a reliable key.** Observed values include ``09``,
  ``105``, ``133`` and ``1000`` alongside ``YU2020-CV-00166``; across ~44,700
  rows these cannot all be unique, and the detail route keys on that value
  alone, so the app will silently serve the first match. Rows are therefore
  keyed by ``rdc_case_uid`` — a hash of case number, epígrafe and cause of
  action — and any case number appearing on more than one row is flagged
  ``case_number_ambiguous`` so the blast radius stays measurable.

The defendant agency — the field that makes this useful — exists only on the
detail pages. This script records a *candidate* parsed from the epígrafe and
marks it ``caption_parse`` / ``needs_review``; scripts/enrich_rdc_details.py
replaces it with the structured Demandado and promotes it to ``detail_page`` /
``verified``. See that script for the second half of the lane.

Output:
  data/staging/processed/pr_rdc_demandas_civiles.csv

Usage:
  python3 scripts/scrape_rdc_demandas.py
  python3 scripts/scrape_rdc_demandas.py --force
  python3 scripts/scrape_rdc_demandas.py --max-pages 3            # smoke test
  python3 scripts/scrape_rdc_demandas.py --start-page 7400 --force  # re-sweep the tail
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lxml.html
import pandas as pd
import requests

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.post_ingest import apply_post_ingest
from moneysweep.runtime.retry_runtime import RetryExhausted, RetryPolicy, with_retry
from scripts.config import PROJECT_ROOT, setup_logging

SOURCE_ID = "rdc_demandas_civiles"
BASE_ORIGIN = "https://justicia1.justicia.pr.gov"
BASE_URL = f"{BASE_ORIGIN}/rdc"
OUT_PATH_REL = "data/staging/processed/pr_rdc_demandas_civiles.csv"

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; MoneySweep/1.0; PR public-money research)",
    # The registry is served by a small government host. Accept HTML explicitly
    # rather than inheriting base_downloader's JSON default.
    extra_headers={"Accept": "text/html,application/xhtml+xml"},
    max_retries=3,
    base_delay_seconds=5.0,
    max_delay_seconds=30.0,
    page_sleep=0.3,
    rate_limit_sleep=60.0,
    timeout=30,
)
RETRY_POLICY = RetryPolicy(
    max_attempts=HTTP.max_retries,
    base_delay_seconds=HTTP.base_delay_seconds,
    max_delay_seconds=HTTP.max_delay_seconds,
)

DEMANDA_COLUMNS = [
    "rdc_case_uid",
    "case_number",
    "case_number_ambiguous",
    "epigrafe",
    "causa_de_accion",
    # Named to match post_ingest.AMOUNT_COLUMNS so the enrichment pass adds the
    # parsed `*_canonical` companions without a per-source special case.
    "claimed_amount",
    "adjudicated_amount",
    "resolucion_final",
    "fecha_resolucion_final",
    "disposicion",
    "plaintiff_name",
    # Matches post_ingest.ENTITY_NAME_COLUMNS, so `entity_normalized` clusters
    # on the party being sued.
    "defendant_name",
    # A case can name several defendants (the detail page for case 09 lists two).
    # `defendant_name` holds the first; this says how many there were, so a
    # case-level read is not silently mistaken for the whole picture. Filled by
    # scripts/enrich_rdc_details.py — the list view cannot know it.
    "defendant_count",
    "defendant_attribution_method",
    "review_status",
    # UTC date the detail page was read, set by scripts/enrich_rdc_details.py.
    # This — not the presence of a defendant — is what marks a case done: some
    # cases genuinely name no Demandado (bankruptcies, and captions where the
    # government is the plaintiff), and keying resumption off the defendant
    # would re-fetch those on every run forever.
    "detail_fetched_at",
    "detail_url",
    "first_seen_at",
    "source_system",
    "source_url",
    "source_file",
]

# The eight rendered headings, in order. A ninth cell holds the "Ver" link and
# carries no heading of its own.
LIST_FIELDS = [
    "epigrafe",
    "case_number",
    "causa_de_accion",
    "claimed_amount",
    "adjudicated_amount",
    "resolucion_final",
    "fecha_resolucion_final",
    "disposicion",
]

# "Ultima" -> /rdc?pg=7451. Absent on out-of-range pages.
_LAST_PAGE_RE = re.compile(r'href="[^"]*[?&]pg=(\d+)"[^>]*>\s*(?:Ultima|Última)', re.I)

# Caption separator: "vs.", "VS", "v.", " v ". Required to stand alone as a
# token so it cannot fire inside a name (e.g. "ALVS", "VSQUEZ").
_VS_RE = re.compile(r"\s+v\.?s\.?\s+|\s+v\.\s+", re.I)


class _RateLimited(Exception):
    """Internal marker so a 429 is retried by with_retry (mirrors base_downloader)."""


def _page_url(page: int) -> str:
    return f"{BASE_URL}?pg={page}"


def _clean(value: Any) -> str:
    """Collapse whitespace. The registry pads every cell ("09             ")."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def declared_last_page(html: str) -> int | None:
    """Total pages from the "Ultima" pagination link, or None when absent.

    Only used for progress logging — termination is driven by the first empty
    page, because an out-of-range request returns empty rather than clamping.
    """
    match = _LAST_PAGE_RE.search(html)
    return int(match.group(1)) if match else None


def case_uid(case_number: str, epigrafe: str, causa: str) -> str:
    """Stable surrogate key for a case row.

    Núm del Caso alone is not unique across the registry (values like "09" and
    "1000" recur), so identity is the case number *plus* the caption and cause
    of action. Deterministic across runs for unchanged source text.
    """
    payload = "|".join((_clean(case_number), _clean(epigrafe), _clean(causa)))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def parse_caption(epigrafe: str) -> tuple[str, str]:
    """(plaintiff, defendant) from an epígrafe, or ("", "") when unparseable.

    Deliberately conservative — a blank is more useful than a wrong party:

    * "IN RE: DELIRIS CASTAÑER FUENTES" (bankruptcy) has no separator at all.
    * More than one separator means the caption is a compound the naive split
      would mangle, so it is left alone.

    Note that the left side is not always the private party: the registry also
    carries cases where an agency is the plaintiff ("ADM. DESARROLLO SOCIO
    ECONOMICO FAMILIA VS EVELYN HERNANDEZ ORTIZ"). That is a correct reading of
    the caption, not a parse failure — deciding which side is a government
    entity is entity resolution's job, not this parser's.
    """
    text = _clean(epigrafe)
    if not text:
        return "", ""
    parts = _VS_RE.split(text)
    if len(parts) != 2:
        return "", ""
    plaintiff, defendant = _clean(parts[0]), _clean(parts[1])
    if not plaintiff or not defendant:
        return "", ""
    return plaintiff, defendant


def parse_rows(html: str) -> list[dict]:
    """Data rows of the registry table, plus each row's detail href.

    Returns [] for a page with an empty tbody (past the end) or with no table
    at all (an error page still answers 200), so neither case raises.
    """
    try:
        tree = lxml.html.fromstring(html)
    except (lxml.etree.ParserError, ValueError):
        return []

    rows: list[dict] = []
    for tr in tree.xpath("//table//tbody/tr"):
        cells = tr.xpath("./td")
        if len(cells) < len(LIST_FIELDS):
            continue
        record = {field: _clean(cells[i].text_content()) for i, field in enumerate(LIST_FIELDS)}
        if not record["case_number"] and not record["epigrafe"]:
            continue
        hrefs = tr.xpath(".//a/@href")
        record["detail_href"] = hrefs[0] if hrefs else ""
        rows.append(record)
    return rows


def _normalize_row(record: dict, today: str) -> dict:
    """One parsed table row to a canonical output row."""
    plaintiff, defendant = parse_caption(record.get("epigrafe", ""))
    href = record.get("detail_href", "")
    detail_url = f"{BASE_ORIGIN}{href}" if href.startswith("/") else href

    row = {col: "" for col in DEMANDA_COLUMNS}
    for field in LIST_FIELDS:
        row[field] = record.get(field, "")
    row.update(
        {
            "rdc_case_uid": case_uid(
                record.get("case_number", ""),
                record.get("epigrafe", ""),
                record.get("causa_de_accion", ""),
            ),
            # Recomputed across the whole frame once collection finishes.
            "case_number_ambiguous": "false",
            "plaintiff_name": plaintiff,
            "defendant_name": defendant,
            # Only claim an attribution method when something was actually
            # parsed; an unparseable caption leaves the field genuinely unset.
            "defendant_attribution_method": "caption_parse" if defendant else "",
            "review_status": "needs_review",
            "detail_url": detail_url,
            "first_seen_at": today,
            "source_system": SOURCE_ID,
            "source_url": BASE_URL,
            "source_file": "justicia1.justicia.pr.gov/rdc",
        }
    )
    return row


def flag_ambiguous_case_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    """Mark every row whose case number is shared with another row.

    The detail route keys on Núm del Caso alone, so a shared value means the
    detail pass cannot be trusted to reach the right case. Flagging keeps that
    visible instead of silently importing whichever record the app serves.
    """
    if frame.empty or "case_number" not in frame.columns:
        return frame
    frame = frame.copy()
    counts = frame["case_number"].value_counts()
    shared = set(counts[counts > 1].index)
    frame["case_number_ambiguous"] = [
        "true" if str(number) in shared else "false" for number in frame["case_number"]
    ]
    return frame


def _carry_forward_first_seen(frame: pd.DataFrame, out_path: Path, today: str) -> pd.DataFrame:
    """Preserve each case's existing ``first_seen_at``, stamping only new ones.

    The registry renders no filing date — only a resolution date, and only once
    a case is resolved. ``first_seen_at`` is therefore a real upper bound on
    when an unresolved case entered the registry, but only if it never moves:
    re-stamping every row each run would turn it into "the date we last
    scraped", which is worse than leaving it blank.
    """
    previous: dict[str, str] = {}
    if out_path.exists():
        try:
            existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            existing = None
        if existing is not None and {"rdc_case_uid", "first_seen_at"} <= set(existing.columns):
            previous = {
                str(uid): str(seen)
                for uid, seen in zip(existing["rdc_case_uid"], existing["first_seen_at"])
                if isinstance(seen, str) and seen.strip()
            }

    frame = frame.copy()
    frame["first_seen_at"] = [previous.get(str(uid), today) for uid in frame["rdc_case_uid"]]
    return frame


def merge_with_existing(frame: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    """Fold a sweep's rows into the stored corpus instead of replacing it.

    A sweep only ever observes the list view, so writing its result straight
    over the output file loses two different things:

    * **Cases the sweep did not visit.** ``--start-page`` exists precisely so
      the append-ordered tail can be re-swept cheaply, and ``--max-pages``
      bounds a smoke test. Either way ``raw_records`` holds a slice, not the
      corpus, and replacing the file with a slice deletes every earlier case.

    * **Detail enrichment, on every run — including a full one.** The list
      view cannot see Demandado, so a rebuilt row carries a caption guess at
      best. Since the scheduled refresh re-sweeps from page 1, replacing would
      discard every party record scripts/enrich_rdc_details.py has accumulated,
      each month, silently.

    So: a case already carrying ``detail_fetched_at`` is authoritative and is
    kept as stored; an unenriched case is refreshed from the sweep; and a
    stored case the sweep did not return is kept rather than dropped. That last
    rule means the corpus never shrinks, which matches the coverage contract's
    append-mostly reading — a shortfall means the sweep stopped early, not that
    the registry lost a case.

    A case whose resolution changes *after* it was enriched is therefore not
    refreshed by a sweep. Clearing its ``detail_fetched_at`` re-queues it for
    the detail pass, which is the authoritative path for those fields anyway.
    """
    if not out_path.exists():
        return frame
    try:
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return frame
    if existing.empty or "rdc_case_uid" not in existing.columns:
        return frame

    existing = existing.fillna("")
    if "detail_fetched_at" not in existing.columns:
        existing["detail_fetched_at"] = ""

    enriched = set(
        existing.loc[
            existing["detail_fetched_at"].astype(str).str.strip() != "", "rdc_case_uid"
        ].astype(str)
    )
    incoming = frame[~frame["rdc_case_uid"].astype(str).isin(enriched)]
    refreshed = set(incoming["rdc_case_uid"].astype(str))
    retained = existing[
        existing["rdc_case_uid"].astype(str).isin(enriched)
        | ~existing["rdc_case_uid"].astype(str).isin(refreshed)
    ]

    columns = list(dict.fromkeys([*DEMANDA_COLUMNS, *existing.columns, *frame.columns]))
    combined = pd.concat(
        [retained.reindex(columns=columns), incoming.reindex(columns=columns)],
        ignore_index=True,
    ).fillna("")
    return combined.drop_duplicates(subset=["rdc_case_uid"], keep="first")


def _fetch_page(session: requests.Session, page: int, logger) -> str | None:
    """GET one listing page. None on a terminal 4xx or retry exhaustion."""

    def _once() -> str | None:
        resp = session.get(_page_url(page), timeout=HTTP.timeout)
        if resp.status_code == 429:
            logger.warning(f"  Rate limited on page {page} — sleeping {HTTP.rate_limit_sleep}s")
            time.sleep(HTTP.rate_limit_sleep)
            raise _RateLimited()
        if 400 <= resp.status_code < 500:
            logger.error(f"  HTTP {resp.status_code} on page {page}")
            return None
        resp.raise_for_status()
        time.sleep(HTTP.page_sleep)
        return resp.text

    try:
        return with_retry(
            _once, policy=RETRY_POLICY, retry_on=(requests.RequestException, _RateLimited)
        )
    except RetryExhausted as exc:
        logger.error(f"  Page {page} failed: {exc}")
        return None


def fetch_all_records(
    session: requests.Session,
    logger,
    start_page: int = 1,
    max_pages: int | None = None,
) -> tuple[list[dict], bool]:
    """Walk pages from ``start_page`` until one comes back empty.

    Returns (records, truncated). ``truncated`` is True iff a page fetch failed
    mid-sweep, so a partial result can be told apart from a clean finish — the
    same contract as scrape_asg_emergency_purchases.fetch_all_records.
    """
    records: list[dict] = []
    truncated = False
    last_page: int | None = None
    page = start_page
    fetched = 0

    while True:
        if max_pages is not None and fetched >= max_pages:
            break

        html = _fetch_page(session, page, logger)
        if html is None:
            truncated = True
            break
        fetched += 1

        if last_page is None:
            last_page = declared_last_page(html)
            logger.info(f"  declared last page: {last_page if last_page else 'unknown'}")

        batch = parse_rows(html)
        if not batch:
            # Past the end: the registry answers 200 with an empty tbody rather
            # than clamping, so this is the clean stop condition.
            logger.info(f"  page {page} returned no rows — sweep complete")
            break

        records.extend(batch)
        if page % 100 == 0:
            logger.info(f"    page {page}: {len(records):,} cases so far")
        page += 1

    return records, truncated


def run(
    root=None,
    force: bool = False,
    max_pages: int | None = None,
    start_page: int = 1,
) -> dict:
    return _run(root=root, force=force, max_pages=max_pages, start_page=start_page)


def _run(
    root=None,
    force: bool = False,
    max_pages: int | None = None,
    start_page: int = 1,
) -> dict:
    if root is None:
        root = PROJECT_ROOT
    out_path = Path(root) / OUT_PATH_REL
    logger = setup_logging("scrape_rdc_demandas")
    logger.info("Starting RDC civil-claims registry sweep...")

    if not force and file_has_data(out_path):
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        logger.info(f"  {out_path.name} exists ({len(existing):,} rows) — skipping.")
        return {"status": "OK", "rows": len(existing), "path": str(out_path), "errors": []}

    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    try:
        raw_records, truncated = fetch_all_records(
            session, logger, start_page=start_page, max_pages=max_pages
        )
    finally:
        session.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()

    if not raw_records:
        pd.DataFrame(columns=DEMANDA_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {
            "status": "ERROR",
            "rows": 0,
            "path": str(out_path),
            "errors": ["No records fetched from justicia1.justicia.pr.gov/rdc"],
        }

    frame = pd.DataFrame([_normalize_row(r, today) for r in raw_records], columns=DEMANDA_COLUMNS)
    frame = frame.drop_duplicates(subset=["rdc_case_uid"])
    # Both read the file before it is overwritten: first_seen_at values survive,
    # and so do cases this sweep did not visit or must not overwrite.
    frame = _carry_forward_first_seen(frame, out_path, today)
    frame = merge_with_existing(frame, out_path)
    # Corpus-wide, so a duplicate case number is caught even when the two rows
    # sharing it came from different sweeps.
    frame = flag_ambiguous_case_numbers(frame)
    # Adds claimed_amount_canonical / adjudicated_amount_canonical,
    # entity_normalized and the geo columns.
    frame = apply_post_ingest(frame, source_id=SOURCE_ID, root=Path(root))
    frame.to_csv(out_path, index=False, encoding="utf-8")

    errors = []
    if truncated:
        msg = (
            f"Sweep stopped early after a page fetch failure — only "
            f"{len(frame):,} cases captured; re-run with --force once the "
            f"endpoint recovers"
        )
        logger.error(f"  {msg}")
        errors.append(msg)

    ambiguous = int((frame["case_number_ambiguous"] == "true").sum())
    attributed = int((frame["defendant_attribution_method"] == "caption_parse").sum())

    logger.info("=" * 60)
    logger.info("RDC CIVIL-CLAIMS SWEEP SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total cases:            {len(frame):,}")
    logger.info(f"  Caption-parsed parties: {attributed:,} (needs_review until enriched)")
    logger.info(f"  Ambiguous case numbers: {ambiguous:,}")
    if "claimed_amount_canonical" in frame.columns:
        logger.info(f"  Total claimed:          ${frame['claimed_amount_canonical'].sum():,.2f}")
    if "adjudicated_amount_canonical" in frame.columns:
        logger.info(
            f"  Total adjudicated:      ${frame['adjudicated_amount_canonical'].sum():,.2f}"
        )

    return {
        "status": "TRUNCATED" if truncated else "OK",
        "rows": len(frame),
        "path": str(out_path),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep the PR civil-claims registry (RDC)")
    parser.add_argument("--force", action="store_true", help="Re-sweep even if output exists")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="Limit pages fetched (smoke testing)"
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First page to fetch. The registry is append-ordered, so a high "
        "start page re-sweeps only recent cases.",
    )
    args = parser.parse_args()
    result = _run(force=args.force, max_pages=args.max_pages, start_page=args.start_page)
    print(f"\nRDC sweep complete: {result['rows']:,} civil claims")
    return 1 if result["errors"] and result["rows"] == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
