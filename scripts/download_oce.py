"""Download the public OCE Socrata donations dataset and materialize it.

The canonical dataset is ``kdwd-nb6g``. Pagination uses explicit ``$limit`` and
``$offset`` parameters so runs are complete and independently auditable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from scripts.campaign_finance_common import file_sha256
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.ingest_oce import run as ingest_oce

DATASET_ID = "kdwd-nb6g"
SOCRATA_ENDPOINT = f"https://data.oce.pr.gov/resource/{DATASET_ID}.json"
DEFAULT_PAGE_SIZE = 50_000
USER_AGENT = "moneysweep-pr/1.0 campaign-finance observatory"

API_COLUMNS = [
    "candidato",
    "candidatura",
    "siglas",
    "cantidad_donacion",
    "metodo_donacion",
    "nombre_completo",
    "donante_pueblo",
    "fecha_donacion",
    "descripcion_evento",
    "zip_code",
    "location_1",
]


def _session(app_token: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    if app_token:
        session.headers["X-App-Token"] = app_token
    return session


def fetch_rows(
    session: requests.Session,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    where: str | None = None,
    logger=None,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    pages: list[dict] = []
    offset = 0
    page = 0
    while True:
        page += 1
        params: dict[str, object] = {
            "$limit": page_size,
            "$offset": offset,
            "$order": "fecha_donacion asc",
        }
        if where:
            params["$where"] = where
        response = session.get(SOCRATA_ENDPOINT, params=params, timeout=60)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected OCE response type: {type(batch).__name__}")
        pages.append({"page": page, "offset": offset, "rows": len(batch), "url": response.url})
        rows.extend(batch)
        if logger:
            logger.info(f"  OCE page {page}: {len(batch):,} rows (total {len(rows):,})")
        if len(batch) < page_size or (max_pages is not None and page >= max_pages):
            break
        offset += page_size
    return rows, pages


def run(
    root: Path | None = None,
    *,
    force: bool = False,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    where: str | None = None,
    app_token: str | None = None,
) -> dict:
    root = Path(root) if root is not None else PROJECT_ROOT
    raw_dir = root / "data" / "raw" / "OCE"
    manifest_dir = root / "data" / "manifests" / "campaign_finance"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"oce_socrata_{DATASET_ID}.csv"
    logger = setup_logging("download_oce")

    if raw_path.exists() and not force:
        logger.info(f"  Cached raw OCE file: {raw_path}")
        ingest = ingest_oce(root=root, force=True)
        return {"status": "CACHED", "raw_path": str(raw_path), **ingest}

    token = app_token or os.environ.get("SOCRATA_APP_TOKEN")
    session = _session(token)
    try:
        rows, pages = fetch_rows(
            session,
            page_size=page_size,
            max_pages=max_pages,
            where=where,
            logger=logger,
        )
    finally:
        session.close()

    frame = pd.DataFrame(rows)
    for column in API_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    # Preserve extra Socrata columns after the canonical API fields.
    ordered = API_COLUMNS + [c for c in frame.columns if c not in API_COLUMNS]
    frame = frame[ordered]
    frame.to_csv(raw_path, index=False, encoding="utf-8")

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "manifest_type": "oce_socrata_acquisition",
        "dataset_id": DATASET_ID,
        "endpoint": SOCRATA_ENDPOINT,
        "generated_at": generated_at,
        "where": where,
        "page_size": page_size,
        "page_count": len(pages),
        "row_count": len(frame),
        "raw_path": str(raw_path.relative_to(root)),
        "sha256": file_sha256(raw_path),
        "columns": list(frame.columns),
        "pages": pages,
    }
    manifest_path = manifest_dir / "oce_socrata_latest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ingest = ingest_oce(root=root, force=True)
    return {
        "status": "OK" if len(frame) else "EMPTY",
        "downloaded_rows": len(frame),
        "raw_path": str(raw_path),
        "manifest_path": str(manifest_path),
        **ingest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--where")
    parser.add_argument("--app-token")
    args = parser.parse_args()
    result = run(
        force=args.force,
        page_size=args.page_size,
        max_pages=args.max_pages,
        where=args.where,
        app_token=args.app_token,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] not in {"EMPTY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
