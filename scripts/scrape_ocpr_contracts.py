"""
Scrape the PR Comptroller (OCPR) contract registry from the live
consultacontratos.ocpr.gov.pr public search database.

Every contract granted by a PR government entity must be registered here —
the canonical record of *all* PR government contracts (distinct from
``oficina_contralor``, which carries only OCPR audit/investigation reports).

Unlike iapconsulta (classic ASP.NET WebForms), this is an ASP.NET Core MVC
app with an anti-forgery-token-protected JSON endpoint. One GET to the site
root yields a session cookie and a ``__RequestVerificationToken`` (scraped
out of the search page's hidden input); every subsequent search POST carries
that token as a header:

    GET  https://consultacontratos.ocpr.gov.pr/
    POST https://consultacontratos.ocpr.gov.pr/contract/search
      Content-Type: application/json; charset=utf-8
      __RequestVerificationToken: <token>
      body: {"draw": n, "start": offset, "length": n, "EntityId": null, ...}

Unlike iapconsulta, this endpoint honors the requested ``length`` (verified:
asking for 100 rows returns exactly 100). It is also slow: an unfiltered
search reported recordsFiltered ~1.34M contracts, and a single 100-row page
took ~20s server-side. A full, from-scratch materialization of this source
is therefore a multi-hour-to-multi-day job by design, not a CI-sized task —
the same shape as this codebase's existing SAM.gov full-registry pull
(documented in CHANGELOG.md as "2.3+ days" at its rate limit). Use
``--max-pages`` for smoke testing; run a full pull as a scheduled/background
job, same as any other large source here.

A run this long has a real chance of the anti-forgery session going stale
partway through, so a page fetch failure triggers one re-authentication +
retry before that page (and the run) is given up on as truncated. There is
still no persistent resume-from-offset: an interrupted run has to restart
from page 0 on the next invocation (after ``--force``, since a partial file
otherwise reads as "already has data" and gets skipped) — acceptable for a
first cut given the size of the underlying engineering lift, revisit if this
proves painful in practice.

Dates arrive in .NET JSON date format (``"/Date(1260507600000)/"``, epoch
milliseconds, optionally with a timezone-offset suffix) rather than plain
strings, so they need their own parser (``_parse_dotnet_date``) distinct from
iapconsulta's plain-string handling. A contract can have co-contractors
(``Contractors`` is an array); their names are joined into the single
``contractor_name`` column. Contractor SSNs are always null in the public
response (redacted), so ``contractor_id`` stays blank for scraped rows. A
downloadable, SSN-redacted copy of the contract document is linked via
``contract/downloaddocument?code=<id>`` when available; that resolves into
``document_url``.

Output:
  data/staging/processed/pr_ocpr_contracts.csv (same schema/output path as
  scripts/ingest_ocpr_contracts.py — this replaces it as the registered
  producer for the ``ocpr_contracts`` source; ingest_ocpr_contracts.py
  remains available as a manual-dropzone fallback).

Usage:
  python3 scripts/scrape_ocpr_contracts.py
  python3 scripts/scrape_ocpr_contracts.py --force
  python3 scripts/scrape_ocpr_contracts.py --max-pages 5   # smoke test
  python3 scripts/scrape_ocpr_contracts.py --page-length 250
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.pagination_runtime import PageResult, paginate
from moneysweep.runtime.retry_runtime import RetryExhausted, RetryPolicy, with_retry
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.ingest_ocpr_contracts import OUTPUT_COLUMNS

BASE_URL = "https://consultacontratos.ocpr.gov.pr/"
SEARCH_URL = BASE_URL + "contract/search"
DOWNLOAD_PATH = "contract/downloaddocument?code={code}"
OUT_PATH_REL = "data/staging/processed/pr_ocpr_contracts.csv"

DEFAULT_PAGE_LENGTH = 100  # verified live; the endpoint is slow, so this stays modest

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; ContractSweeper/1.0; PR contract research)",
    max_retries=3,
    base_delay_seconds=5.0,
    max_delay_seconds=30.0,
    page_sleep=0.5,
    rate_limit_sleep=60.0,
    timeout=60,  # observed pages can take ~20s server-side
)
RETRY_POLICY = RetryPolicy(
    max_attempts=HTTP.max_retries,
    base_delay_seconds=HTTP.base_delay_seconds,
    max_delay_seconds=HTTP.max_delay_seconds,
)

_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
# Optional trailing timezone offset (e.g. "/Date(1610000000000-0400)/"), which
# some .NET DateTimeOffset fields emit alongside the bare epoch-ms form.
_DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/")

_SEARCH_FILTERS = {
    "EntityId": None,
    "ContractNumber": None,
    "ContractorName": None,
    "DateOfGrantFrom": None,
    "DateOfGrantTo": None,
    "EffectiveDateFrom": None,
    "EffectiveDateTo": None,
    "AmountFrom": None,
    "AmountTo": None,
    "ServiceGroupId": None,
    "ServiceId": None,
    "FundId": None,
    "ContractingFormId": None,
    "PCONumber": None,
}


class _RateLimited(Exception):
    """Internal marker so a 429 is retried by with_retry (mirrors base_downloader)."""


def _session_and_token(logger) -> tuple[requests.Session, str]:
    """One GET to prime the session cookie and scrape the anti-forgery token."""
    session = build_session(HTTP.user_agent)
    resp = session.get(BASE_URL, timeout=HTTP.timeout)
    resp.raise_for_status()
    m = _TOKEN_RE.search(resp.text)
    if not m:
        raise RuntimeError("Could not find __RequestVerificationToken on the search page")
    logger.info("  Session primed, anti-forgery token acquired")
    return session, m.group(1)


def _fetch_page(
    session: requests.Session, token: str, start: int, length: int, logger
) -> dict | None:
    """POST one page. Returns the parsed JSON, or None on a terminal 4xx / retry
    exhaustion — same contract as the iapconsulta scraper's _fetch_page. A
    non-JSON 200 (e.g. redirected back to the HTML search page) surfaces from
    resp.json() as requests.exceptions.JSONDecodeError, itself a
    RequestException subclass, so it's already covered by retry_on below."""
    payload = {"draw": 1, "start": start, "length": length, **_SEARCH_FILTERS}

    def _once() -> dict | None:
        resp = session.post(
            SEARCH_URL,
            json=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "__RequestVerificationToken": token,
            },
            timeout=HTTP.timeout,
        )
        if resp.status_code == 429:
            logger.warning(f"  Rate limited at start={start} — sleeping {HTTP.rate_limit_sleep}s")
            time.sleep(HTTP.rate_limit_sleep)
            raise _RateLimited()
        if 400 <= resp.status_code < 500:
            logger.error(f"  HTTP {resp.status_code} at start={start}: {resp.text[:200]}")
            return None
        resp.raise_for_status()
        data = resp.json()
        time.sleep(HTTP.page_sleep)
        return data

    try:
        return with_retry(
            _once, policy=RETRY_POLICY, retry_on=(requests.RequestException, _RateLimited)
        )
    except RetryExhausted as exc:
        logger.error(f"  Page start={start} failed: {exc}")
        return None


def _parse_dotnet_date(value) -> str:
    """Extract the epoch-ms payload from .NET's "/Date(1260507600000)/" and
    format it as an ISO date, or "" if absent/unparseable."""
    if not value:
        return ""
    m = _DOTNET_DATE_RE.search(str(value))
    if not m:
        return ""
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def _extract_document_url(record: dict) -> str:
    code = record.get("DocumentWithoutSocialSecurityId")
    if not code:
        return ""
    return urljoin(BASE_URL, DOWNLOAD_PATH.format(code=code))


def _normalize_row(record: dict) -> dict:
    contractors = record.get("Contractors") or []
    contractor_name = "; ".join(c.get("Name", "").strip() for c in contractors if c.get("Name"))
    amount = record.get("AmountToPay")

    row = {col: "" for col in OUTPUT_COLUMNS}
    row.update(
        {
            "contract_number": (record.get("ContractNumber") or "").strip(),
            "contractor_name": contractor_name,
            "agency": (record.get("EntityName") or "").strip(),
            "contract_amount": "" if amount is None else str(amount),
            "start_date": _parse_dotnet_date(record.get("EffectiveDateFrom")),
            "end_date": _parse_dotnet_date(record.get("EffectiveDateTo")),
            "service_description": (record.get("Service") or "").strip(),
            "contract_type": (record.get("ServiceGroup") or "").strip(),
            "status": "Cancelado" if record.get("CancellationDate") else "",
            "document_url": _extract_document_url(record),
            "source_file": "consultacontratos.ocpr.gov.pr",
        }
    )
    return row


def fetch_all_records(
    session: requests.Session,
    token: str,
    logger,
    page_length: int = DEFAULT_PAGE_LENGTH,
    max_pages: int | None = None,
) -> tuple[list[dict], bool]:
    """Page through the search API, normalizing each record as its page
    arrives. Returns (rows, truncated) — `truncated` is True iff a page fetch
    failed mid-scrape (as opposed to a clean stop at recordsTotal or an
    intentional max_pages cutoff).

    A failed page gets one re-authentication + retry (the session/token this
    was called with can go stale partway through a multi-hour run) before
    it's counted as a failure. A malformed individual record is logged and
    skipped rather than aborting the whole — otherwise reachable — result."""
    total_known = False
    truncated = False
    skipped = 0

    def _fetch(start: int) -> PageResult:
        nonlocal total_known, truncated, session, token, skipped
        page_num = start // page_length + 1
        data = _fetch_page(session, token, start, page_length, logger)
        if data is None:
            logger.warning(f"  Page start={start} failed — re-authenticating and retrying once")
            try:
                session, token = _session_and_token(logger)
                data = _fetch_page(session, token, start, page_length, logger)
            except (requests.RequestException, RuntimeError) as exc:
                logger.error(f"  Re-authentication failed: {exc}")
                data = None
        if data is None:
            truncated = True
            return PageResult(records=[], next_marker=None)

        total = data.get("recordsTotal") or 0
        if not total_known:
            logger.info(f"  recordsTotal={total:,}")
            total_known = True

        batch = data.get("data") or []
        normalized = []
        for record in batch:
            try:
                normalized.append(_normalize_row(record))
            except Exception as exc:  # untrusted API payload shape
                skipped += 1
                logger.warning(f"  Skipping malformed record at start={start}: {exc}")

        next_start = start + len(batch)
        if page_num % 20 == 0:
            logger.info(f"    page {page_num}: {next_start:,}/{total:,} records so far")
        next_marker = next_start if batch and next_start < total else None
        return PageResult(records=normalized, next_marker=next_marker)

    rows = list(paginate(_fetch, start_marker=0, max_pages=max_pages))
    if skipped:
        logger.warning(f"  Skipped {skipped:,} malformed record(s) during normalization")
    return rows, truncated


def _cached_row_count(path: Path) -> int:
    """Cheap line count for the skip-log message — avoids a full pandas parse
    of what could be a multi-hundred-MB cached CSV."""
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh) - 1  # minus the header row


def run(root=None, max_pages=None, page_length=DEFAULT_PAGE_LENGTH):
    return _run(root=root, force=False, max_pages=max_pages, page_length=page_length)


def _run(root=None, force=False, max_pages=None, page_length=DEFAULT_PAGE_LENGTH):
    if root is None:
        root = PROJECT_ROOT
    out_path = Path(root) / OUT_PATH_REL
    logger = setup_logging("scrape_ocpr_contracts")
    logger.info("Starting consultacontratos.ocpr.gov.pr contract registry scrape...")

    if not force and file_has_data(out_path):
        row_count = _cached_row_count(out_path)
        logger.info(f"  {out_path.name} exists ({row_count:,} rows) — skipping.")
        return {"rows": row_count, "path": str(out_path), "errors": [], "status": "OK"}

    session, token = _session_and_token(logger)
    rows, truncated = fetch_all_records(
        session, token, logger, page_length=page_length, max_pages=max_pages
    )
    session.close()

    if not rows:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {
            "rows": 0,
            "path": str(out_path),
            "errors": ["No records fetched from consultacontratos.ocpr.gov.pr"],
            "status": "ERROR",
        }

    combined = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    combined = combined[combined["contract_number"] != ""].drop_duplicates()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_path, index=False, encoding="utf-8")

    errors = []
    if truncated:
        msg = (
            f"Scrape stopped early after a page fetch failure — only "
            f"{len(combined):,} records captured; re-run with --force once the "
            f"endpoint recovers"
        )
        logger.error(f"  {msg}")
        errors.append(msg)

    logger.info("=" * 60)
    logger.info("OCPR CONTRACTS SCRAPE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total records: {len(combined):,}")
    logger.info(f"  Unique agencies: {combined['agency'].nunique():,}")

    return {
        "rows": len(combined),
        "path": str(out_path),
        "errors": errors,
        "status": "TRUNCATED" if truncated else "OK",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scrape the PR OCPR contract registry from consultacontratos.ocpr.gov.pr"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="Limit pages fetched (smoke testing)"
    )
    parser.add_argument(
        "--page-length",
        type=int,
        default=DEFAULT_PAGE_LENGTH,
        help="Rows requested per page (default: %(default)s)",
    )
    args = parser.parse_args()
    result = _run(force=args.force, max_pages=args.max_pages, page_length=args.page_length)
    print(f"\nocpr_contracts scrape complete: {result['rows']:,} contract records")
    # Unlike a quick 4K-row scrape, a truncated run here is a meaningful loss
    # (potentially most of a multi-day pull) even with rows > 0, so any error
    # fails the exit code rather than only a fully-empty result.
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
