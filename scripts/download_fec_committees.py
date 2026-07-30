"""
Download FEC committee master, Schedule B disbursements, and Schedule E
independent expenditures for Puerto Rico-linked political committees.

Schedule B supports repeated ``committee_id`` parameters. MoneySweep batches
committee IDs so a full historical run stays within practical API-call limits
instead of issuing one request for every committee/cycle pair.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from moneysweep.runtime.base_downloader import (
    HttpConfig,
    PageResult,
    build_session,
    http_get_json,
    paginate,
)
from scripts.config import PROJECT_ROOT, setup_logging

_USER_AGENT = "ContractSweeper/1.0 (PR federal spending research)"
FEC_BASE = "https://api.open.fec.gov/v1"
PAGE_SIZE = 100
PAGE_SLEEP_DEMO = 2.5
PAGE_SLEEP_KEY = 0.2
MAX_RETRIES = 3
START_CYCLE = 2000
COMMITTEE_BATCH_SIZE = 10

_T = TypeVar("_T")


def _current_fec_cycle() -> int:
    year = date.today().year
    return year if year % 2 == 0 else year + 1


END_CYCLE = _current_fec_cycle()

COMMITTEE_COLUMNS = [
    "committee_id",
    "name",
    "committee_type",
    "committee_type_full",
    "designation",
    "designation_full",
    "party",
    "party_full",
    "state",
    "treasurer_name",
    "first_file_date",
    "last_file_date",
    "organization_type",
]

DISBURSEMENT_COLUMNS = [
    "cycle",
    "committee_id",
    "committee_name",
    "recipient_name",
    "recipient_city",
    "recipient_state",
    "disbursement_amount",
    "disbursement_date",
    "disbursement_description",
    "disbursement_purpose_category",
    "memo_text",
]

INDEPENDENT_EXPENDITURE_COLUMNS = [
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


def _session(api_key: str) -> requests.Session:
    return build_session(_USER_AGENT, {"X-Api-Key": api_key})


def _get(
    session: requests.Session,
    url: str,
    params: dict,
    logger,
    sleep_s: float,
) -> dict | None:
    config = HttpConfig(
        user_agent=_USER_AGENT,
        max_retries=MAX_RETRIES,
        page_sleep=sleep_s,
    )
    return http_get_json(
        session,
        url,
        params,
        logger=logger,
        config=config,
        raise_on_failure=True,
    )


def _chunks(values: Sequence[_T], size: int) -> Iterator[list[_T]]:
    if size < 1:
        raise ValueError("chunk size must be positive")
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def _unique_committee_ids(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        committee_id = str(raw).strip()
        if committee_id and committee_id not in seen:
            seen.add(committee_id)
            output.append(committee_id)
    return output


def _fetch_committees(
    session: requests.Session,
    sleep_s: float,
    logger,
) -> list[dict]:
    """Fetch every FEC committee whose registered state is Puerto Rico."""
    url = f"{FEC_BASE}/committees/"

    def _fetch(page: int) -> PageResult:
        params = {
            "state": "PR",
            "per_page": PAGE_SIZE,
            "page": page,
            "sort": "-last_file_date",
        }
        data = _get(session, url, params, logger, sleep_s)
        if data is None:
            return PageResult([], None)
        results = data.get("results", [])
        if not results:
            return PageResult([], None)
        rows = [
            {
                "committee_id": item.get("committee_id", ""),
                "name": item.get("name", ""),
                "committee_type": item.get("committee_type", ""),
                "committee_type_full": item.get("committee_type_full", ""),
                "designation": item.get("designation", ""),
                "designation_full": item.get("designation_full", ""),
                "party": item.get("party", ""),
                "party_full": item.get("party_full", ""),
                "state": item.get("state", ""),
                "treasurer_name": item.get("treasurer_name", ""),
                "first_file_date": item.get("first_file_date", ""),
                "last_file_date": item.get("last_file_date", ""),
                "organization_type": item.get("organization_type", ""),
            }
            for item in results
        ]
        pagination = data.get("pagination", {})
        pages = int(pagination.get("pages", 1) or 1)
        if page == 1:
            logger.info(
                "  Committees: %s total PR-linked",
                f"{int(pagination.get('count', 0) or 0):,}",
            )
        return PageResult(rows, None if page >= pages else page + 1)

    return list(paginate(_fetch, start_marker=1))


def _fetch_disbursements(
    session: requests.Session,
    committee_ids: list[str],
    cycles: list[int],
    sleep_s: float,
    logger,
    batch_size: int = COMMITTEE_BATCH_SIZE,
) -> list[dict]:
    """Fetch Schedule B using repeated committee_id parameters in bounded batches."""
    url = f"{FEC_BASE}/schedules/schedule_b/"
    rows: list[dict] = []
    unique_ids = _unique_committee_ids(committee_ids)
    batches = list(_chunks(unique_ids, batch_size))
    logger.info(
        "  Schedule B request plan: %s committees in %s batches x %s cycles",
        f"{len(unique_ids):,}",
        f"{len(batches):,}",
        len(cycles),
    )

    for cycle in cycles:
        for batch_number, committee_batch in enumerate(batches, start=1):

            def _fetch(
                page: int,
                cycle: int = cycle,
                committee_batch: list[str] = committee_batch,
            ) -> PageResult:
                params = {
                    "committee_id": committee_batch,
                    "two_year_transaction_period": cycle,
                    "per_page": PAGE_SIZE,
                    "page": page,
                    "sort": "-disbursement_date",
                    "sort_hide_null": "false",
                }
                data = _get(session, url, params, logger, sleep_s)
                if data is None:
                    return PageResult([], None)
                results = data.get("results", [])
                if not results:
                    return PageResult([], None)
                page_rows = []
                for item in results:
                    page_rows.append(
                        {
                            "cycle": cycle,
                            "committee_id": item.get("committee_id", ""),
                            "committee_name": item.get("committee_name", ""),
                            "recipient_name": item.get("recipient_name", ""),
                            "recipient_city": item.get("recipient_city", ""),
                            "recipient_state": item.get("recipient_state", ""),
                            "disbursement_amount": item.get("disbursement_amount", ""),
                            "disbursement_date": item.get("disbursement_date", ""),
                            "disbursement_description": item.get("disbursement_description", ""),
                            "disbursement_purpose_category": item.get(
                                "disbursement_purpose_category", ""
                            ),
                            "memo_text": item.get("memo_text", ""),
                        }
                    )
                pagination = data.get("pagination", {})
                pages = int(pagination.get("pages", 1) or 1)
                return PageResult(page_rows, None if page >= pages else page + 1)

            rows.extend(paginate(_fetch, start_marker=1))
            if batch_number == len(batches) or batch_number % 10 == 0:
                logger.info(
                    "  Schedule B cycle %s: completed batch %s/%s",
                    cycle,
                    batch_number,
                    len(batches),
                )

    return rows


def _fetch_independent_expenditures(
    session: requests.Session,
    cycles: list[int],
    sleep_s: float,
    logger,
) -> list[dict]:
    """Fetch Schedule E independent expenditures filed by PR committees."""
    url = f"{FEC_BASE}/schedules/schedule_e/"
    rows: list[dict] = []
    for cycle in cycles:

        def _fetch(page: int, cycle: int = cycle) -> PageResult:
            params = {
                "filer_state": "PR",
                "two_year_transaction_period": cycle,
                "per_page": PAGE_SIZE,
                "page": page,
                "sort": "-expenditure_date",
                "sort_hide_null": "false",
            }
            data = _get(session, url, params, logger, sleep_s)
            if data is None:
                return PageResult([], None)
            results = data.get("results", [])
            if not results:
                return PageResult([], None)
            page_rows = [
                {
                    "cycle": cycle,
                    "committee_id": item.get("committee_id", ""),
                    "committee_name": item.get("committee_name", ""),
                    "candidate_id": item.get("candidate_id", ""),
                    "candidate_name": item.get("candidate_name", ""),
                    "support_oppose_indicator": item.get("support_oppose_indicator", ""),
                    "expenditure_amount": item.get("expenditure_amount", ""),
                    "expenditure_date": item.get("expenditure_date", ""),
                    "office": item.get("office", ""),
                    "office_state": item.get("office_state", ""),
                    "office_district": item.get("office_district", ""),
                    "category_code_full": item.get("category_code_full", ""),
                }
                for item in results
            ]
            pagination = data.get("pagination", {})
            pages = int(pagination.get("pages", 1) or 1)
            return PageResult(page_rows, None if page >= pages else page + 1)

        rows.extend(paginate(_fetch, start_marker=1))
    return rows


def _write_frame(rows: list[dict], columns: list[str], path: Path) -> int:
    frame = pd.DataFrame(rows, columns=columns).drop_duplicates()
    frame.to_csv(path, index=False, encoding="utf-8")
    return len(frame)


def run(
    root: Path | None = None,
    api_key: str | None = None,
    force: bool = False,
    skip_disbursements: bool = False,
    skip_expenditures: bool = False,
) -> dict:
    root = Path(root) if root is not None else PROJECT_ROOT
    processed_dir = root / "data" / "staging" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    committees_path = processed_dir / "pr_fec_committees.csv"
    disbursements_path = processed_dir / "pr_fec_disbursements.csv"
    expenditures_path = processed_dir / "pr_fec_independent_expenditures.csv"
    logger = setup_logging("download_fec_committees")
    manifest_dir = root / "data" / "manifests" / "campaign_finance"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "fec_outflows_acquisition.json"
    acquisition_manifest = {
        "manifest_type": "fec_outflows_acquisition",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "committee_batch_size": COMMITTEE_BATCH_SIZE,
        "cycle_start": START_CYCLE,
        "cycle_end": END_CYCLE,
    }
    manifest_path.write_text(
        json.dumps(acquisition_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    api_key = api_key or os.environ.get("FEC_API_KEY", "DEMO_KEY")
    is_demo = api_key == "DEMO_KEY"
    sleep_s = PAGE_SLEEP_DEMO if is_demo else PAGE_SLEEP_KEY
    if is_demo:
        logger.warning("Using DEMO_KEY (30 requests/hour); configure FEC_API_KEY for a full run.")

    if not force and committees_path.exists():
        committee_frame = pd.read_csv(
            committees_path,
            dtype=str,
            low_memory=False,
        )
        committees = committee_frame.to_dict("records")
    else:
        logger.info("Phase 1: fetching PR-linked FEC committees")
        session = _session(api_key)
        try:
            committees = _fetch_committees(session, sleep_s, logger)
        finally:
            session.close()
        committee_frame = pd.DataFrame(
            committees,
            columns=COMMITTEE_COLUMNS,
        ).drop_duplicates()
        committee_frame.to_csv(
            committees_path,
            index=False,
            encoding="utf-8",
        )

    committee_ids = (
        committee_frame.get("committee_id", pd.Series(dtype=str)).dropna().astype(str).tolist()
    )
    committee_ids = _unique_committee_ids(committee_ids)
    cycles = list(range(START_CYCLE, END_CYCLE + 1, 2))
    logger.info(
        "Phase 1 complete: %s committees",
        f"{len(committee_frame):,}",
    )

    if skip_disbursements:
        if not disbursements_path.exists():
            pd.DataFrame(columns=DISBURSEMENT_COLUMNS).to_csv(
                disbursements_path,
                index=False,
                encoding="utf-8",
            )
        disbursement_rows = 0
    elif not committee_ids:
        disbursement_rows = _write_frame(
            [],
            DISBURSEMENT_COLUMNS,
            disbursements_path,
        )
    else:
        logger.info("Phase 2: fetching Schedule B disbursements")
        session = _session(api_key)
        try:
            disbursements = _fetch_disbursements(
                session,
                committee_ids,
                cycles,
                sleep_s,
                logger,
            )
        finally:
            session.close()
        disbursement_rows = _write_frame(
            disbursements,
            DISBURSEMENT_COLUMNS,
            disbursements_path,
        )
        logger.info(
            "Phase 2 complete: %s disbursements",
            f"{disbursement_rows:,}",
        )

    if skip_expenditures:
        if not expenditures_path.exists():
            pd.DataFrame(columns=INDEPENDENT_EXPENDITURE_COLUMNS).to_csv(
                expenditures_path,
                index=False,
                encoding="utf-8",
            )
        expenditure_rows = 0
    else:
        logger.info("Phase 3: fetching Schedule E independent expenditures")
        session = _session(api_key)
        try:
            expenditures = _fetch_independent_expenditures(
                session,
                cycles,
                sleep_s,
                logger,
            )
        finally:
            session.close()
        expenditure_rows = _write_frame(
            expenditures,
            INDEPENDENT_EXPENDITURE_COLUMNS,
            expenditures_path,
        )
        logger.info(
            "Phase 3 complete: %s independent expenditures",
            f"{expenditure_rows:,}",
        )

    committee_batches = (len(committee_ids) + COMMITTEE_BATCH_SIZE - 1) // COMMITTEE_BATCH_SIZE
    schedule_b_planned = 0 if skip_disbursements else committee_batches * len(cycles)
    schedule_e_planned = 0 if skip_expenditures else len(cycles)
    acquisition_manifest.update(
        {
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "committee_count": len(committee_ids),
            "cycles": cycles,
            "schedule_b": {
                "planned_batches": schedule_b_planned,
                "completed_batches": schedule_b_planned,
                "rows": disbursement_rows,
                "skipped": skip_disbursements,
            },
            "schedule_e": {
                "planned_cycles": schedule_e_planned,
                "completed_cycles": schedule_e_planned,
                "rows": expenditure_rows,
                "skipped": skip_expenditures,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(acquisition_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "rows": len(committee_frame),
        "committees": len(committee_frame),
        "disbursements": disbursement_rows,
        "independent_expenditures": expenditure_rows,
        "status": "OK",
        "request_plan": {
            "committee_batch_size": COMMITTEE_BATCH_SIZE,
            "committee_batches": (len(committee_ids) + COMMITTEE_BATCH_SIZE - 1)
            // COMMITTEE_BATCH_SIZE,
            "cycles": len(cycles),
        },
        "paths": {
            "committees": str(committees_path),
            "disbursements": str(disbursements_path),
            "independent_expenditures": str(expenditures_path),
            "acquisition_manifest": str(manifest_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download FEC committees and Schedule B/E for PR committees."
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-disbursements", action="store_true")
    parser.add_argument("--skip-expenditures", action="store_true")
    args = parser.parse_args()
    result = run(
        api_key=args.api_key,
        force=args.force,
        skip_disbursements=args.skip_disbursements,
        skip_expenditures=args.skip_expenditures,
    )
    print(
        "\nFEC committees: "
        f"{result['committees']:,} | "
        f"disbursements: {result['disbursements']:,} | "
        f"independent expenditures: {result['independent_expenditures']:,}"
    )
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
