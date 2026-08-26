"""Materialize guide-relevant OCIF license classes with fail-closed paging.

Authority: Puerto Rico Office of the Commissioner of Financial Institutions
(OCIF), public concessionaire registry.

This producer intentionally preserves source strings. ``source_record_id`` is a
manifestation key, not proof that two legal entities are identical. License
number is retained separately and is the preferred authoritative identifier when
present.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests
from lxml import html as lxml_html

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.post_ingest import apply_post_ingest
from scripts.config import PROJECT_ROOT, setup_logging

SOURCE_ID = "ocif_guide_financial_classes"
BASE_URL = "https://concesionarios.ocif.pr.gov/es/License/Index"
OUT_REL = "data/staging/processed/pr_ocif_guide_financial_classes.csv"
PAGE_SIZE = 100
LICENSE_CLASSES = (
    "ENTIDAD FINANCIERA INTERNACIONAL",
    "ENTIDAD BANCARIA INTERNACIONAL",
    "FONDO DE CAPITAL PRIVADO LEY 185-2014",
    "EXEMPT REPORTING ADVISORS",
    "INVESTMENT ADVISOR",
)

COLUMNS = [
    "source_record_id",
    "license_type_raw",
    "institution_name_raw",
    "dba_raw",
    "status_raw",
    "address_raw",
    "phone_raw",
    "approval_date_raw",
    "license_number_raw",
    "nmls_raw",
    "contact_name_raw",
    "crd_raw",
    "depository_raw",
    "source_page",
    "source_url",
    "retrieved_at_utc",
]

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; MoneySweep/1.0; PR public-money research)",
    max_retries=3,
    base_delay_seconds=2.0,
    max_delay_seconds=12.0,
    page_sleep=0.25,
    rate_limit_sleep=30.0,
    timeout=30,
)

_COUNT_RE = re.compile(r"Filas:\s*(\d+)\s+de\s+(\d+)\s+P[áa]gina:\s*(\d+)\s+de\s+(\d+)", re.I)


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _record_id(row: dict[str, str]) -> str:
    material = "\x1f".join(
        [
            row.get("license_type_raw", ""),
            row.get("license_number_raw", ""),
            row.get("institution_name_raw", ""),
            row.get("approval_date_raw", ""),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def parse_page(
    page_html: str,
    *,
    source_page: int,
    source_url: str,
    retrieved_at: str,
) -> tuple[list[dict], dict]:
    """Parse exactly the visible result table and its denominator marker."""
    doc = lxml_html.fromstring(page_html)
    rows: list[dict] = []

    for table in doc.xpath("//table"):
        headers = [_clean(x.text_content()) for x in table.xpath(".//thead//th")]
        if not headers or "Nombre de Ins." not in headers:
            continue
        for tr in table.xpath(".//tbody/tr"):
            cells = [_clean(td.text_content()) for td in tr.xpath("./td")]
            if len(cells) < 12:
                continue
            values = (cells + [""] * 12)[:12]
            row = dict(
                zip(
                    COLUMNS[:12],
                    [
                        "",
                        values[0],
                        values[1],
                        values[2],
                        values[3],
                        values[4],
                        values[5],
                        values[6],
                        values[7],
                        values[8],
                        values[9],
                        values[10],
                    ],
                    strict=True,
                )
            )
            row["depository_raw"] = values[11]
            row["source_page"] = str(source_page)
            row["source_url"] = source_url
            row["retrieved_at_utc"] = retrieved_at
            row["source_record_id"] = _record_id(row)
            rows.append(row)
        break

    text = _clean(doc.text_content())
    match = _COUNT_RE.search(text)
    meta = {
        "page_rows": int(match.group(1)) if match else len(rows),
        "total_rows": int(match.group(2)) if match else None,
        "page": int(match.group(3)) if match else source_page,
        "total_pages": int(match.group(4)) if match else None,
    }
    return rows, meta


def _url(license_type: str, page: int) -> str:
    params = {"LicenseTypeFilter": license_type, "Page": page, "PageSize": PAGE_SIZE}
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_class(session: requests.Session, license_type: str, logger) -> list[dict]:
    all_rows: list[dict] = []
    seen_page_hashes: set[str] = set()
    expected_total: int | None = None
    page = 1

    while True:
        url = _url(license_type, page)
        response = session.get(url, timeout=HTTP.timeout)
        if response.status_code == 429:
            time.sleep(HTTP.rate_limit_sleep)
            continue
        response.raise_for_status()
        raw_hash = hashlib.sha256(response.content).hexdigest()
        if raw_hash in seen_page_hashes:
            raise RuntimeError(f"OCIF repeated/clamped page for {license_type!r} at page {page}")
        seen_page_hashes.add(raw_hash)

        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows, meta = parse_page(
            response.text,
            source_page=page,
            source_url=url,
            retrieved_at=retrieved_at,
        )
        if meta["page"] != page:
            raise RuntimeError(
                f"OCIF page-number mismatch: requested={page}, observed={meta['page']}"
            )
        if expected_total is None:
            expected_total = meta["total_rows"]
        elif meta["total_rows"] not in (None, expected_total):
            raise RuntimeError(
                f"OCIF denominator changed during run for {license_type!r}: "
                f"{expected_total} -> {meta['total_rows']}"
            )

        for row in rows:
            if row["license_type_raw"] != license_type:
                raise RuntimeError(
                    f"OCIF filter leakage: requested {license_type!r}, "
                    f"observed {row['license_type_raw']!r}"
                )
            if not row["institution_name_raw"]:
                raise RuntimeError(f"OCIF null institution name in {license_type!r} page {page}")
        all_rows.extend(rows)

        total_pages = meta["total_pages"]
        if total_pages is None:
            raise RuntimeError(f"OCIF denominator marker missing for {license_type!r} page {page}")
        if page >= total_pages:
            break
        page += 1
        time.sleep(HTTP.page_sleep)

    if expected_total is None or len(all_rows) != expected_total:
        raise RuntimeError(
            f"OCIF arithmetic closure failed for {license_type!r}: "
            f"retained={len(all_rows)} expected={expected_total}"
        )
    ids = [row["source_record_id"] for row in all_rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"OCIF duplicate source-record manifestation in {license_type!r}")
    return all_rows


def run(
    root: Path | None = None,
    *,
    force: bool = False,
    license_classes: tuple[str, ...] = LICENSE_CLASSES,
) -> dict:
    root = root or PROJECT_ROOT
    out_path = root / OUT_REL
    logger = setup_logging("scrape_ocif_guide_financial_classes")
    if not force and file_has_data(out_path):
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        return {"rows": len(existing), "path": str(out_path), "errors": []}

    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    rows: list[dict] = []
    try:
        for license_type in license_classes:
            logger.info("OCIF class: %s", license_type)
            rows.extend(fetch_class(session, license_type, logger))
    finally:
        session.close()

    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        raise RuntimeError("OCIF produced zero rows")
    if df["source_record_id"].duplicated().any():
        raise RuntimeError("OCIF duplicate source_record_id across license classes")

    df = apply_post_ingest(df, source_id=SOURCE_ID, root=root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    return {"rows": len(df), "path": str(out_path), "errors": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--license-type", action="append", dest="license_types")
    args = parser.parse_args()
    classes = tuple(args.license_types) if args.license_types else LICENSE_CLASSES
    result = run(force=args.force, license_classes=classes)
    print(f"OCIF guide classes: {result['rows']:,} rows -> {result['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
