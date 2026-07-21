"""
Download congressional earmarks for Puerto Rico from USASpending.

Earmarks (congressionally directed spending) resumed in FY2022. PR delegation
earmarks appear in appropriations bills across all agencies. USASpending has no
earmark flag, so this script retains only awards whose descriptions contain
explicit congressional-directed-spending language.

Source: USASpending API (spending_by_award) — no auth required

Output:
  data/staging/processed/pr_earmarks.csv

Usage:
  python3 scripts/download_earmarks.py
  python3 scripts/download_earmarks.py --force
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from moneysweep.runtime.base_downloader import (
    HttpConfig,
    HttpRequestFailed,
    PageResult,
    build_session,
    cache_is_complete,
    http_post_json,
    paginate,
    write_csv_complete,
)

from scripts.config import PROJECT_ROOT, setup_logging
from scripts._download_utils import derive_fiscal_year as _derive_fiscal_year

USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# USAspending requires each request to contain one award-type group.
AWARD_TYPE_GROUPS = {
    "assistance": ["02", "03", "04", "05"],
    "contracts": ["A", "B", "C", "D"],
}
SCHEMA_VERSION = "2"

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Award Amount",
    "Start Date",
    "Award Type",
    "Place of Performance State Code",
    "Place of Performance County Name",
    "Description",
]

# Earmark keyword search — USASpending description field often includes "congressionally directed"
EARMARK_KEYWORDS = [
    "congressionally directed",
    "congressional earmark",
    "directed spending",
    "community project funding",  # House term post-2022
    "spending direction",
]

TIME_WINDOWS = [
    {"label": "2022f2026", "start_date": "2022-10-01", "end_date": "2026-09-30"},
]

EARMARK_COLUMNS = [
    "award_id",
    "recipient_name",
    "recipient_uei",
    "awarding_agency",
    "awarding_sub_agency",
    "obligated_amount",
    "award_date",
    "fiscal_year",
    "pop_state",
    "pop_county",
    "description",
    "source_file",
    "source_dataset",
    "award_category",
    "earmark_keyword_matched",
]

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]
PAGE_SLEEP = 0.3
RATE_LIMIT_SLEEP = 30


_HTTP = HttpConfig(
    user_agent="ContractSweeper/1.0",
    max_retries=MAX_RETRIES,
    page_sleep=PAGE_SLEEP,
    rate_limit_sleep=RATE_LIMIT_SLEEP,
)


def _session():
    return build_session("ContractSweeper/1.0")


def _fetch_page(session, payload, logger):
    return http_post_json(
        session,
        USASPENDING_URL,
        payload,
        logger=logger,
        config=_HTTP,
        raise_on_failure=True,
    )


def _paginate(session, base_payload, logger):
    def _fetch(page):
        payload = {**base_payload, "page": page}
        data = _fetch_page(session, payload, logger)
        if data is None:
            return PageResult([], None)
        results = data.get("results", [])
        if not results:
            return PageResult([], None)
        page_meta = data.get("page_metadata", {})
        has_next = page_meta.get("has_next_page", False)
        return PageResult(results, page + 1 if has_next else None)

    return list(paginate(_fetch, start_marker=1))


def _build_payload(window, award_group):
    return {
        "filters": {
            "award_type_codes": AWARD_TYPE_GROUPS[award_group],
            "place_of_performance_locations": [{"country": "USA", "state": "PR"}],
            "time_period": [{"start_date": window["start_date"], "end_date": window["end_date"]}],
        },
        "fields": FIELDS,
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }


def _results_to_df(results, source_file):
    if not results:
        return pd.DataFrame(columns=EARMARK_COLUMNS)
    df = pd.json_normalize(results)
    rename_map = {
        "Award ID": "award_id",
        "award_id": "award_id",
        "Recipient Name": "recipient_name",
        "recipient_name": "recipient_name",
        "Awarding Agency": "awarding_agency",
        "Awarding Sub Agency": "awarding_sub_agency",
        "Award Amount": "obligated_amount",
        "total_obligated_amount": "obligated_amount",
        "Start Date": "award_date",
        "Award Type": "award_category",
        "Place of Performance State Code": "pop_state",
        "Place of Performance County Name": "pop_county",
        "Description": "description",
        "award_description": "description",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["fiscal_year"] = df.get("award_date", pd.Series(dtype=str)).apply(_derive_fiscal_year)
    df["source_file"] = source_file
    df["source_dataset"] = "earmarks"

    # Flag which keyword matched
    def _kw_match(desc):
        if not desc or pd.isna(desc):
            return ""
        desc_lower = str(desc).lower()
        for kw in EARMARK_KEYWORDS:
            if kw in desc_lower:
                return kw
        return ""

    df["earmark_keyword_matched"] = df.get("description", pd.Series(dtype=str)).apply(_kw_match)
    # The API has no earmark flag. Only description evidence is retained; broad
    # Puerto Rico awards are never relabeled as earmarks merely by DEF code.
    df = df[df["earmark_keyword_matched"] != ""].copy()

    for col in EARMARK_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[EARMARK_COLUMNS]


def run(root=None):
    return _run(root=root, force=False)


def _run(root=None, force=False):
    if root is None:
        root = PROJECT_ROOT
    out_path = root / "data" / "staging" / "processed" / "pr_earmarks.csv"
    logger = setup_logging("download_earmarks")
    logger.info("Starting congressional earmarks download for Puerto Rico...")

    queries = [
        _build_payload(window, award_group)
        for window in TIME_WINDOWS
        for award_group in AWARD_TYPE_GROUPS
    ]
    cache_payload = {"queries": queries}

    if not force and cache_is_complete(
        out_path, cache_payload, SCHEMA_VERSION, allow_empty=True
    ):
        rows = len(pd.read_csv(out_path, dtype=str, low_memory=False))
        logger.info(f"  pr_earmarks.csv exists ({rows:,} rows) — skipping.")
        return {"rows": rows, "path": str(out_path), "errors": []}

    session = _session()
    all_frames = []
    errors = []

    for window in TIME_WINDOWS:
        logger.info(f"  Window: {window['start_date']} → {window['end_date']}")
        for award_group in AWARD_TYPE_GROUPS:
            fname = f"earmarks_{window['label']}_{award_group}.csv"
            try:
                results = _paginate(
                    session, _build_payload(window, award_group), logger
                )
            except HttpRequestFailed as exc:
                logger.error(f"  {award_group}: {exc}")
                errors.append(f"{fname}: {exc}")
                continue
            df = _results_to_df(results, fname)
            if not df.empty:
                all_frames.append(df)
            logger.info(
                f"  {len(df)} keyword-confirmed earmark records "
                f"for {window['label']} ({award_group})"
            )

    session.close()

    if errors:
        logger.error("  One or more request groups failed; refusing to publish a partial cache")
        return {"rows": 0, "path": str(out_path), "errors": errors}
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        if "award_id" in combined.columns:
            combined = combined.drop_duplicates(subset=["award_id"], keep="first")
    else:
        combined = pd.DataFrame(columns=EARMARK_COLUMNS)

    write_csv_complete(
        combined,
        out_path,
        cache_payload,
        source="earmarks",
        schema_version=SCHEMA_VERSION,
        page_count=sum(max(1, (len(frame) + 99) // 100) for frame in all_frames),
    )

    total_amt = (
        pd.to_numeric(combined.get("obligated_amount", pd.Series()), errors="coerce")
        .fillna(0)
        .sum()
    )
    logger.info("=" * 60)
    logger.info("EARMARKS SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total earmark records: {len(combined):,}")
    logger.info(f"  Total obligated:       ${total_amt:,.0f}")

    return {"rows": len(combined), "path": str(out_path), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Download congressional earmarks for Puerto Rico")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = _run(force=args.force)
    print(f"\nEarmarks complete: {result['rows']:,} records")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
