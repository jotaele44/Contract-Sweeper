"""
Scrape PR Oficina del Contralor (OCPR) audit & investigation reports from the
live iapconsulta.ocpr.gov.pr public search database.

iapconsulta is the OCPR's searchable database of audit reports and
investigation reports on PR government entities (agencies, municipalities,
public corporations, universities) — never individuals or private
businesses. Its "Tipo de Informe" filter has three values: Regular, Especial,
and Investigaciones, all three of which map onto the existing
``audit_type`` column in ``scripts.ingest_contralor.CONTRALOR_COLUMNS`` — this
is the same ``oficina_contralor`` source, not a separate dataset.

The search page (Informes.aspx) is classic ASP.NET WebForms, but the actual
results grid is populated client-side by jQuery DataTables against a plain
JSON handler that needs no session/viewstate/auth:

    POST https://iapconsulta.ocpr.gov.pr/app/server/code/handler/InformesPublicos.ashx
    Content-Type: application/x-www-form-urlencoded
    body: draw=<n>&start=<offset>&length=<n>&rama=&entidad=&numero=&tipo=&desde=&hasta=

The server ignores ``length`` and always returns a fixed page of 10 rows, so
pagination walks ``start`` in steps of 10 until it reaches ``recordsTotal``.
Each row's ``Open`` field embeds an ``<a href="../../OpenDoc.aspx?...">`` link
to the actual PDF report; ``report_url`` is extracted from that.

Output:
  data/staging/processed/pr_contralor_audits.csv (same schema/output path as
  scripts/ingest_contralor.py — this replaces it as the registered producer
  for the ``oficina_contralor`` source; ingest_contralor.py remains available
  as a manual-dropzone fallback).

Usage:
  python3 scripts/scrape_iapconsulta.py
  python3 scripts/scrape_iapconsulta.py --force
  python3 scripts/scrape_iapconsulta.py --max-pages 5   # smoke test
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from moneysweep.runtime.retry_runtime import RetryExhausted, RetryPolicy, with_retry
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.ingest_contralor import CONTRALOR_COLUMNS, _normalize_name

BASE_URL = "https://iapconsulta.ocpr.gov.pr/"
SEARCH_URL = BASE_URL + "app/server/code/handler/InformesPublicos.ashx"
OUT_PATH_REL = "data/staging/processed/pr_contralor_audits.csv"

PAGE_SIZE = 10  # server-enforced; requesting a larger `length` has no effect
PAGE_SLEEP = 0.5
RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=5.0, max_delay_seconds=30.0)
REQUEST_TIMEOUT = 30

_HREF_RE = re.compile(r'href="([^"]+)"')


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; ContractSweeper/1.0; PR audit research)",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE_URL,
        }
    )
    return s


def _fetch_page(session: requests.Session, start: int, logger) -> dict | None:
    payload = {
        "draw": 1,
        "start": start,
        "length": PAGE_SIZE,
        "rama": "",
        "entidad": "",
        "numero": "",
        "tipo": "",
        "desde": "",
        "hasta": "",
    }

    def _once() -> dict:
        resp = session.post(
            SEARCH_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        return with_retry(_once, policy=RETRY_POLICY, retry_on=(requests.RequestException, ValueError))
    except RetryExhausted as exc:
        logger.error(f"  Page start={start} failed: {exc}")
        return None


def _extract_report_url(open_html: str | None) -> str:
    if not open_html:
        return ""
    m = _HREF_RE.search(open_html)
    if not m:
        return ""
    return urljoin(BASE_URL, m.group(1))


def _year_from_date(value: str) -> str:
    m = re.search(r"(\d{4})", value or "")
    return m.group(1) if m else ""


def _normalize_row(record: dict) -> dict:
    entidad = (record.get("Entidad") or "").strip()
    if entidad in ("", "N/A"):
        entidad = (record.get("NombreInforme") or "").strip()
    audit_date = (record.get("Publicacion") or "").strip()

    row = {col: "" for col in CONTRALOR_COLUMNS}
    row.update(
        {
            "entity_name": entidad,
            "entity_normalized": _normalize_name(entidad),
            "audit_id": (record.get("NumInforme") or "").strip(),
            "audit_type": (record.get("TipoInforme") or "").strip(),
            "audit_year": _year_from_date(audit_date),
            "audit_date": audit_date,
            "branch": (record.get("Rama") or "").strip(),
            "report_url": _extract_report_url(record.get("Open")),
            "source_file": "iapconsulta.ocpr.gov.pr",
        }
    )
    return row


def fetch_all_records(session: requests.Session, logger, max_pages: int | None = None) -> list[dict]:
    records: list[dict] = []
    start = 0
    page = 0
    total = None
    while True:
        page += 1
        if max_pages is not None and page > max_pages:
            logger.info(f"  Reached max_pages={max_pages} — stopping early")
            break
        data = _fetch_page(session, start, logger)
        if data is None:
            break
        if total is None:
            total = data.get("recordsTotal", 0)
            logger.info(f"  recordsTotal={total:,}")
        batch = data.get("data") or []
        if not batch:
            break
        records.extend(batch)
        start += PAGE_SIZE
        if page % 20 == 0:
            logger.info(f"    page {page}: {len(records):,}/{total:,} records so far")
        if start >= total:
            break
        time.sleep(PAGE_SLEEP)
    return records


def run(root=None, max_pages=None):
    return _run(root=root, force=False, max_pages=max_pages)


def _run(root=None, force=False, max_pages=None):
    if root is None:
        root = PROJECT_ROOT
    out_path = Path(root) / OUT_PATH_REL
    logger = setup_logging("scrape_iapconsulta")
    logger.info("Starting iapconsulta.ocpr.gov.pr audit/investigation scrape...")

    if not force and out_path.exists():
        try:
            existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        except pd.errors.EmptyDataError:
            existing = pd.DataFrame()
        if len(existing) > 0:
            logger.info(f"  {out_path.name} exists ({len(existing):,} rows) — skipping.")
            return {"rows": len(existing), "path": str(out_path), "errors": []}

    session = _session()
    raw_records = fetch_all_records(session, logger, max_pages=max_pages)
    session.close()

    if not raw_records:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=CONTRALOR_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {"rows": 0, "path": str(out_path), "errors": ["No records fetched from iapconsulta"]}

    rows = [_normalize_row(r) for r in raw_records]
    combined = pd.DataFrame(rows, columns=CONTRALOR_COLUMNS)
    combined = combined[combined["entity_name"].str.strip() != ""].drop_duplicates()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_path, index=False, encoding="utf-8")

    by_type = combined["audit_type"].value_counts().to_dict()
    logger.info("=" * 60)
    logger.info("IAPCONSULTA SCRAPE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total records:   {len(combined):,}")
    logger.info(f"  Unique entities: {combined['entity_normalized'].nunique():,}")
    logger.info(f"  By report type:  {by_type}")

    return {"rows": len(combined), "path": str(out_path), "errors": []}


def main():
    parser = argparse.ArgumentParser(description="Scrape PR OCPR audit/investigation reports from iapconsulta")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages fetched (smoke testing)")
    args = parser.parse_args()
    result = _run(force=args.force, max_pages=args.max_pages)
    print(f"\niapconsulta scrape complete: {result['rows']:,} audit/investigation records")
    return 1 if result["errors"] and result["rows"] == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
