"""Resumable FEC Schedule E acquisition for Puerto Rico filers.

Writes a durable CSV and manifest after every completed cycle. Existing completed
cycles are skipped when ``--resume`` is supplied. Network requests use bounded
connect/read timeouts and retry with exponential backoff so one stalled response
cannot consume the entire Actions job budget.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from scripts.config import PROJECT_ROOT, setup_logging

FEC_URL = "https://api.open.fec.gov/v1/schedules/schedule_e/"
START_CYCLE = 2000
PAGE_SIZE = 100
MAX_ATTEMPTS = 8
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
COLUMNS = [
    "cycle",
    "committee_id",
    "committee_name",
    "candidate_id",
    "candidate_name",
    "support_oppose_indicator",
    "expenditure_amount",
    "expenditure_date",
    "office",
    "office_state",
    "office_district",
    "category_code_full",
]


def current_cycle() -> int:
    year = date.today().year
    return year if year % 2 == 0 else year + 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_frame(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[COLUMNS]


def request_json(
    session: requests.Session,
    params: dict[str, str | int],
    logger: Any,
) -> dict[str, Any]:
    delay = 5.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(
                FEC_URL,
                params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else max(60.0, delay)
                )
                logger.warning("Rate limited; retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Schedule E response was not a JSON object")
            return payload
        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
        ) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Schedule E request failed after {MAX_ATTEMPTS} attempts: {exc}"
                ) from exc
            logger.warning(
                "Schedule E request attempt %s/%s failed: %s; retrying in %.1fs",
                attempt,
                MAX_ATTEMPTS,
                type(exc).__name__,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 120.0)
    raise RuntimeError("unreachable retry state")


def fetch_cycle(
    session: requests.Session,
    cycle: int,
    logger: Any,
) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
    page = 1
    pages = 1
    while page <= pages:
        data = request_json(
            session,
            {
                "filer_state": "PR",
                "two_year_transaction_period": cycle,
                "per_page": PAGE_SIZE,
                "page": page,
                "sort": "-expenditure_date",
                "sort_hide_null": "false",
            },
            logger,
        )
        results = data.get("results", [])
        pagination = data.get("pagination", {})
        if not isinstance(results, list):
            raise RuntimeError("Schedule E results field was not a list")
        if not isinstance(pagination, dict):
            raise RuntimeError("Schedule E pagination field was not an object")
        pages = int(pagination.get("pages", 1) or 1)
        for raw_item in results:
            if not isinstance(raw_item, dict):
                continue
            item: dict[str, Any] = raw_item
            rows.append(
                {
                    "cycle": cycle,
                    "committee_id": item.get("committee_id", ""),
                    "committee_name": item.get("committee_name", ""),
                    "candidate_id": item.get("candidate_id", ""),
                    "candidate_name": item.get("candidate_name", ""),
                    "support_oppose_indicator": item.get(
                        "support_oppose_indicator", ""
                    ),
                    "expenditure_amount": item.get("expenditure_amount", ""),
                    "expenditure_date": item.get("expenditure_date", ""),
                    "office": item.get("office", ""),
                    "office_state": item.get("office_state", ""),
                    "office_district": item.get("office_district", ""),
                    "category_code_full": item.get("category_code_full", ""),
                }
            )
        logger.info(
            "Schedule E cycle %s: completed page %s/%s",
            cycle,
            page,
            pages,
        )
        page += 1
    return rows, pages


def run(root: Path, resume: bool) -> dict[str, Any]:
    logger = setup_logging("download_fec_schedule_e_resumable")
    output = root / "data/staging/processed/pr_fec_independent_expenditures.csv"
    manifest_path = (
        root
        / "data/manifests/campaign_finance/fec_schedule_e_acquisition.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    cycles = list(range(START_CYCLE, current_cycle() + 1, 2))
    frame = load_frame(output) if resume else pd.DataFrame(columns=COLUMNS)
    completed = sorted(
        {
            int(value)
            for value in frame.get("cycle", pd.Series(dtype=str)).dropna()
            if str(value).isdigit()
        }
    )
    cycle_pages: dict[str, int] = {}
    manifest: dict[str, Any] = {
        "manifest_type": "fec_schedule_e_acquisition",
        "status": "running",
        "started_at": utc_now(),
        "planned_cycles": cycles,
        "completed_cycles": completed,
        "cycle_pages": cycle_pages,
        "rows": int(len(frame)),
        "resume": resume,
    }
    write_json(manifest_path, manifest)

    api_key = os.environ.get("FEC_API_KEY")
    if not api_key:
        raise RuntimeError("FEC_API_KEY is required")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "MoneySweep/1.0 campaign-finance materialization",
            "Accept": "application/json",
            "X-Api-Key": api_key,
        }
    )
    try:
        for cycle in cycles:
            if resume and cycle in completed:
                logger.info(
                    "Schedule E cycle %s already checkpointed; skipping",
                    cycle,
                )
                continue
            cycle_rows, pages = fetch_cycle(session, cycle, logger)
            retained = (
                frame[frame["cycle"].astype(str) != str(cycle)]
                if not frame.empty
                else frame
            )
            frame = pd.concat(
                [retained, pd.DataFrame(cycle_rows, columns=COLUMNS)],
                ignore_index=True,
            )
            frame = frame[COLUMNS].drop_duplicates()
            frame.to_csv(output, index=False, encoding="utf-8")
            completed.append(cycle)
            completed = sorted(set(completed))
            cycle_pages[str(cycle)] = pages
            manifest.update(
                {
                    "completed_cycles": completed,
                    "cycle_pages": cycle_pages,
                    "rows": int(len(frame)),
                    "last_checkpoint_at": utc_now(),
                }
            )
            write_json(manifest_path, manifest)
            logger.info(
                "Schedule E cycle %s checkpointed with %s rows",
                cycle,
                len(cycle_rows),
            )
    finally:
        session.close()

    missing = sorted(set(cycles) - set(completed))
    manifest.update(
        {
            "status": "complete" if not missing else "incomplete",
            "completed_at": utc_now(),
            "completed_cycles": completed,
            "missing_cycles": missing,
            "rows": int(len(frame)),
            "schema_columns": COLUMNS,
        }
    )
    write_json(manifest_path, manifest)
    if missing:
        raise RuntimeError(f"Schedule E incomplete; missing cycles: {missing}")
    print(json.dumps(manifest, sort_keys=True))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    result = run(args.root, args.resume)
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
