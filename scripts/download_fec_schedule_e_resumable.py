"""Page-resumable FEC Schedule E acquisition for certified PR committees."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from scripts.config import PROJECT_ROOT, setup_logging

FEC_URL = "https://api.open.fec.gov/v1/schedules/schedule_e/"
START_CYCLE = 2000
PAGE_SIZE = 100
COMMITTEE_BATCH_SIZE = 5
MAX_ATTEMPTS = 8
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
_T = TypeVar("_T")
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


def chunks(values: Sequence[_T], size: int) -> Iterator[list[_T]]:
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def committee_ids(path: Path) -> list[str]:
    if not path.exists():
        raise RuntimeError(f"Certified committee universe is missing: {path}")
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    if "committee_id" not in frame.columns:
        raise RuntimeError("Certified committee universe lacks committee_id")
    seen: set[str] = set()
    output: list[str] = []
    for raw in frame["committee_id"].dropna().astype(str):
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    if not output:
        raise RuntimeError("Certified committee universe is empty")
    return output


def request_json(
    session: requests.Session,
    params: dict[str, Any],
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
                retry_after = response.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else max(60.0, delay)
                logger.warning("Rate limited; retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Schedule E response was not a JSON object")
            return payload
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
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


def normalize_rows(results: list[Any], cycle: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                "cycle": cycle,
                "committee_id": raw.get("committee_id", ""),
                "committee_name": raw.get("committee_name", ""),
                "candidate_id": raw.get("candidate_id", ""),
                "candidate_name": raw.get("candidate_name", ""),
                "support_oppose_indicator": raw.get("support_oppose_indicator", ""),
                "expenditure_amount": raw.get("expenditure_amount", ""),
                "expenditure_date": raw.get("expenditure_date", ""),
                "office": raw.get("office", ""),
                "office_state": raw.get("office_state", ""),
                "office_district": raw.get("office_district", ""),
                "category_code_full": raw.get("category_code_full", ""),
            }
        )
    return rows


def page_path(checkpoint_dir: Path, cycle: int, batch: int, page: int) -> Path:
    return checkpoint_dir / f"cycle={cycle}" / f"batch={batch:04d}" / f"page={page:06d}.csv"


def valid_checkpoint(path: Path, receipt: dict[str, Any]) -> bool:
    return (
        path.exists()
        and receipt.get("sha256") == sha256_file(path)
        and int(receipt.get("rows", -1)) == len(pd.read_csv(path, dtype=str, low_memory=False))
    )


def assemble_output(checkpoint_dir: Path, output: Path) -> pd.DataFrame:
    page_files = sorted(checkpoint_dir.glob("cycle=*/batch=*/page=*.csv"))
    frames = [pd.read_csv(path, dtype=str, low_memory=False) for path in page_files]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[COLUMNS].drop_duplicates().reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(output)
    return frame


def run(root: Path, resume: bool) -> dict[str, Any]:
    logger = setup_logging("download_fec_schedule_e_resumable")
    processed = root / "data/staging/processed"
    committees_path = processed / "pr_fec_committees.csv"
    output = processed / "pr_fec_independent_expenditures.csv"
    checkpoint_dir = root / "data/checkpoints/campaign_finance/fec_schedule_e"
    manifest_path = root / "data/manifests/campaign_finance/fec_schedule_e_acquisition.json"
    if not resume and checkpoint_dir.exists():
        for path in sorted(checkpoint_dir.glob("**/*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    ids = committee_ids(committees_path)
    batches = list(chunks(ids, COMMITTEE_BATCH_SIZE))
    cycles = list(range(START_CYCLE, current_cycle() + 1, 2))
    manifest: dict[str, Any] = {
        "manifest_type": "fec_schedule_e_acquisition",
        "status": "running",
        "started_at": utc_now(),
        "query_scope": "certified_pr_committee_ids",
        "committee_count": len(ids),
        "committee_batch_size": COMMITTEE_BATCH_SIZE,
        "planned_cycles": cycles,
        "planned_batches_per_cycle": len(batches),
        "page_receipts": {},
        "resume": resume,
    }
    if resume and manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(previous.get("page_receipts"), dict):
            manifest["page_receipts"] = previous["page_receipts"]
            manifest["resumed_from_started_at"] = previous.get("started_at")
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
            for batch_number, batch_ids in enumerate(batches, start=1):
                page = 1
                total_pages = 1
                while page <= total_pages:
                    key = f"{cycle}/{batch_number}/{page}"
                    path = page_path(checkpoint_dir, cycle, batch_number, page)
                    receipt = manifest["page_receipts"].get(key, {})
                    if resume and valid_checkpoint(path, receipt):
                        total_pages = int(receipt["total_pages"])
                        logger.info(
                            "Schedule E cycle %s batch %s/%s page %s/%s restored",
                            cycle,
                            batch_number,
                            len(batches),
                            page,
                            total_pages,
                        )
                        page += 1
                        continue
                    payload = request_json(
                        session,
                        {
                            "committee_id": batch_ids,
                            "two_year_transaction_period": cycle,
                            "per_page": PAGE_SIZE,
                            "page": page,
                            "sort": "-expenditure_date",
                            "sort_hide_null": "false",
                        },
                        logger,
                    )
                    results = payload.get("results", [])
                    pagination = payload.get("pagination", {})
                    if not isinstance(results, list) or not isinstance(pagination, dict):
                        raise RuntimeError("Invalid Schedule E response schema")
                    total_pages = int(pagination.get("pages", 1) or 1)
                    rows = normalize_rows(results, cycle)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".csv.tmp")
                    pd.DataFrame(rows, columns=COLUMNS).to_csv(
                        temporary, index=False, encoding="utf-8"
                    )
                    temporary.replace(path)
                    manifest["page_receipts"][key] = {
                        "cycle": cycle,
                        "batch": batch_number,
                        "page": page,
                        "total_pages": total_pages,
                        "committee_ids": batch_ids,
                        "rows": len(rows),
                        "sha256": sha256_file(path),
                        "checkpointed_at": utc_now(),
                    }
                    manifest.update(
                        {
                            "last_checkpoint_at": utc_now(),
                            "next_cycle": cycle,
                            "next_batch": batch_number,
                            "next_page": page + 1,
                            "checkpoint_pages": len(manifest["page_receipts"]),
                            "checkpoint_rows": sum(
                                int(item["rows"]) for item in manifest["page_receipts"].values()
                            ),
                        }
                    )
                    write_json(manifest_path, manifest)
                    logger.info(
                        "Schedule E cycle %s batch %s/%s page %s/%s checkpointed",
                        cycle,
                        batch_number,
                        len(batches),
                        page,
                        total_pages,
                    )
                    page += 1
    finally:
        session.close()

    frame = assemble_output(checkpoint_dir, output)
    completed_cycles = sorted(
        {
            int(value)
            for value in frame.get("cycle", pd.Series(dtype=str)).dropna()
            if str(value).isdigit()
        }
    )
    manifest.update(
        {
            "status": "complete",
            "completed_at": utc_now(),
            "completed_cycles": cycles,
            "observed_nonempty_cycles": completed_cycles,
            "missing_cycles": [],
            "rows": len(frame),
            "output_sha256": sha256_file(output),
            "schema_columns": COLUMNS,
            "checkpoint_pages": len(manifest["page_receipts"]),
            "checkpoint_rows": sum(
                int(item["rows"]) for item in manifest["page_receipts"].values()
            ),
        }
    )
    write_json(manifest_path, manifest)
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
