"""
Download Puerto Rico federal contract *opportunities* (pre-award solicitations)
from the SAM.gov Get Opportunities public API.

This is the pre-award complement to the SAM.gov award/entity sources:
``sam_entities`` (registration/UEI) and ``sam_exclusions`` (debarment) describe
*who* can receive awards; this source captures the open **solicitations, bid
notices, and RFPs** with Place of Performance in Puerto Rico *before* an award
exists. It is the compliant, primary-source replacement for the commercial
govcb.com aggregator (whose Terms of Service forbid reproduction/redistribution).

Endpoint: https://api.sam.gov/opportunities/v2/search  (api_key query param)
A SAM API key (SAM_API_KEY) is required: https://sam.gov/data-services

The API requires ``postedFrom``/``postedTo`` (MM/dd/yyyy) and limits any single
request to a 1-year date range, so a wider lookback is split into <=365-day
windows and paginated with offset/limit.

Output:
  data/staging/processed/pr_sam_opportunities.csv

Usage:
  python3 scripts/download_sam_opportunities.py
  python3 scripts/download_sam_opportunities.py --days 365 --state PR
  python3 scripts/download_sam_opportunities.py --api-key YOUR_KEY --force
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from moneysweep.runtime.base_downloader import (
    HttpConfig,
    PageResult,
    build_session,
    http_get_json,
    paginate,
)
from scripts.config import PROJECT_ROOT, get_sam_api_key, setup_logging

_USER_AGENT = "ContractSweeper/1.0 (PR federal spending research)"
SAM_URL = "https://api.sam.gov/opportunities/v2/search"
PAGE_SIZE = 1000  # API max
DEFAULT_DAYS = 365  # default lookback window (also the API's max single-request range)
DEFAULT_STATE = "PR"  # Place of Performance state
_DATE_FMT = "%m/%d/%Y"
# Guard against a runaway offset loop on an unexpectedly huge result set.
_MAX_PAGES_PER_WINDOW = 200

OUTPUT_COLUMNS = [
    "notice_id",
    "solicitation_number",
    "title",
    "agency",
    "posted_date",
    "response_deadline",
    "naics_code",
    "notice_type",
    "set_aside",
    "pop_state",
    "active",
    "ui_link",
]


def _flatten(record: dict) -> dict:
    """Best-effort flatten of a SAM opportunity record into OUTPUT_COLUMNS."""
    pop = record.get("placeOfPerformance") or {}
    state = pop.get("state") if isinstance(pop, dict) else None
    if isinstance(state, dict):
        pop_state = state.get("code", "") or state.get("name", "")
    else:
        pop_state = state or ""

    row = {col: "" for col in OUTPUT_COLUMNS}
    row["notice_id"] = record.get("noticeId", "")
    row["solicitation_number"] = record.get("solicitationNumber", "")
    row["title"] = record.get("title", "")
    row["agency"] = record.get("fullParentPathName", "") or record.get("department", "")
    row["posted_date"] = record.get("postedDate", "")
    row["response_deadline"] = record.get("responseDeadLine", "") or record.get("responseDate", "")
    row["naics_code"] = record.get("naicsCode", "")
    row["notice_type"] = record.get("type", "")
    row["set_aside"] = record.get("typeOfSetAsideDescription", "") or record.get(
        "typeOfSetAside", ""
    )
    row["pop_state"] = pop_state
    row["active"] = record.get("active", "")
    row["ui_link"] = record.get("uiLink", "")
    return row


def _date_windows(start: date, end: date, max_span_days: int = DEFAULT_DAYS) -> list[tuple]:
    """Split [start, end] into contiguous windows no wider than ``max_span_days``.

    The SAM Opportunities API rejects a postedFrom/postedTo range wider than one
    year, so a longer lookback is chunked into API-legal windows.
    """
    windows: list[tuple] = []
    cursor = start
    step = timedelta(days=max_span_days)
    while cursor <= end:
        window_end = min(cursor + step, end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _fetch_window(session, api_key: str, posted_from: str, posted_to: str, state: str, logger):
    """Yield flattened rows for a single posted-date window via offset pagination."""

    def _page(offset: int) -> PageResult:
        params = {
            "api_key": api_key,
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        if state:
            params["state"] = state
        config = HttpConfig(user_agent=_USER_AGENT, page_sleep=0.5)
        data: Any = http_get_json(session, SAM_URL, params, logger=logger, config=config)
        if not isinstance(data, dict):
            return PageResult([], None)
        results = data.get("opportunitiesData") or []
        if not results:
            return PageResult([], None)
        rows = [_flatten(r) for r in results]
        total = data.get("totalRecords")
        next_offset = offset + PAGE_SIZE
        if len(results) < PAGE_SIZE:
            next_marker = None
        elif total is not None and next_offset >= int(total):
            next_marker = None
        else:
            next_marker = next_offset
        return PageResult(rows, next_marker)

    return list(paginate(_page, start_marker=0, max_pages=_MAX_PAGES_PER_WINDOW))


def run(
    root: Path | None = None,
    api_key: str | None = None,
    days: int = DEFAULT_DAYS,
    state: str = DEFAULT_STATE,
    force: bool = False,
) -> dict:
    root = Path(root or PROJECT_ROOT)
    out_path = root / "data" / "staging" / "processed" / "pr_sam_opportunities.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logging("download_sam_opportunities")

    if not force and out_path.exists():
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        if len(existing) > 0:
            logger.info(f"  Cached — {len(existing):,} rows in {out_path.name}")
            return {"rows": len(existing), "path": str(out_path), "status": "CACHED"}

    if api_key is None:
        try:
            api_key = get_sam_api_key()
        except RuntimeError:
            api_key = ""
    if not api_key:
        logger.warning(
            "  SAM_API_KEY not set — opportunities API requires a key; writing empty file"
        )
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {"rows": 0, "path": str(out_path), "status": "NO_KEY"}

    end = datetime.utcnow().date()
    start = end - timedelta(days=max(days, 1))
    windows = _date_windows(start, end)

    session = build_session(_USER_AGENT)
    logger.info(
        f"Fetching SAM.gov opportunities (state={state or 'ALL'}, "
        f"{start:%Y-%m-%d}..{end:%Y-%m-%d}, {len(windows)} window(s))..."
    )
    rows: list[dict] = []
    try:
        for w_start, w_end in windows:
            posted_from = w_start.strftime(_DATE_FMT)
            posted_to = w_end.strftime(_DATE_FMT)
            window_rows = _fetch_window(session, api_key, posted_from, posted_to, state, logger)
            logger.info(f"  {posted_from}..{posted_to}: {len(window_rows):,} rows")
            rows.extend(window_rows)
    finally:
        session.close()

    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not df.empty and "notice_id" in df.columns:
        # Overlapping windows share an inclusive boundary day; drop dupes by notice id.
        df = df.drop_duplicates(subset=["notice_id"]).reset_index(drop=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    status = "OK" if len(df) else "NO_DATA"
    logger.info(f"  {status}: {len(df):,} opportunity records → {out_path.name}")
    return {"rows": len(df), "path": str(out_path), "status": status}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None, help="SAM API key (or set SAM_API_KEY)")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Lookback window in days (default {DEFAULT_DAYS}; >365 is split into API-legal windows)",
    )
    parser.add_argument(
        "--state",
        default=DEFAULT_STATE,
        help="Place-of-Performance state filter (default PR; pass empty to disable)",
    )
    parser.add_argument("--force", action="store_true", help="Re-fetch even if output exists")
    args = parser.parse_args()
    result = run(api_key=args.api_key, days=args.days, state=args.state, force=args.force)
    print(f"\nSAM opportunities: {result['rows']:,} rows — {result['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
