"""Materialize the OCS domestic-insurer list and annual financial-report index.

The two surfaces are kept separate because a current insurer listing and a
historical annual-report observation are different facts. Raw display names are
preserved exactly; this producer does not collapse aliases across years.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests
from lxml import html as lxml_html

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.post_ingest import apply_post_ingest
from scripts.config import PROJECT_ROOT, setup_logging

SOURCE_ID = "ocs_insurer_registry"
INSURERS_URL = "https://www.ocs.pr.gov/consumidores/aseguradores-del-pais"
ANNUAL_URL = "https://www.ocs.pr.gov/regulados/informes-anuales"
INSURERS_OUT_REL = "data/staging/processed/pr_ocs_insurers.csv"
ANNUAL_OUT_REL = "data/staging/processed/pr_ocs_insurer_annual_reports.csv"

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; MoneySweep/1.0; PR public-money research)",
    max_retries=3,
    base_delay_seconds=2.0,
    max_delay_seconds=12.0,
    page_sleep=0.25,
    rate_limit_sleep=30.0,
    timeout=30,
)

INSURER_COLUMNS = [
    "source_record_id",
    "insurer_name_raw",
    "website_raw",
    "source_url",
    "retrieved_at_utc",
]
ANNUAL_COLUMNS = [
    "source_record_id",
    "report_year_raw",
    "insurer_name_raw",
    "report_url",
    "source_url",
    "retrieved_at_utc",
]
_YEAR_RE = re.compile(r"^(20\d{2})$")


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def _sid(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def parse_insurers(page_html: str, *, source_url: str, retrieved_at: str) -> list[dict]:
    """Extract insurer cards without normalizing names into identities."""
    doc = lxml_html.fromstring(page_html)
    rows: list[dict] = []
    seen_exact: set[str] = set()
    excluded_alt = {
        "image",
        "ocs",
        "logo",
        "gobierno de puerto rico",
        "sello ogp",
    }

    for img in doc.xpath("//img[@alt]"):
        name = _clean(img.get("alt") or "")
        if not name or name.casefold() in excluded_alt:
            continue
        parent = img
        website = ""
        for _ in range(5):
            if parent is None:
                break
            links = parent.xpath(".//a[@href]/@href")
            external = [x for x in links if x.startswith("http") and "ocs.pr.gov" not in x]
            if external:
                website = external[0]
                break
            parent = parent.getparent()
        if name in seen_exact:
            continue
        seen_exact.add(name)
        rows.append(
            {
                "source_record_id": _sid("current", name, website),
                "insurer_name_raw": name,
                "website_raw": website,
                "source_url": source_url,
                "retrieved_at_utc": retrieved_at,
            }
        )

    if not rows:
        raise RuntimeError("OCS insurer parser found zero insurer cards")
    return rows


def _nearest_year(node) -> str:
    preceding = node.xpath(
        "preceding::*[self::h1 or self::h2 or self::h3 or self::h4 or self::div or self::span]"
    )
    for cand in reversed(preceding):
        text = _clean(cand.text_content())
        match = _YEAR_RE.match(text)
        if match:
            return match.group(1)
    return ""


def parse_annual_reports(
    page_html: str,
    *,
    source_url: str,
    retrieved_at: str,
) -> list[dict]:
    doc = lxml_html.fromstring(page_html)
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for anchor in doc.xpath("//a[@href]"):
        href = str(anchor.get("href") or "").strip()
        name = _clean(anchor.text_content())
        if not href or not name:
            continue
        lower = href.casefold()
        if not any(token in lower for token in (".pdf", "document", "download", "media", "files")):
            continue
        year = _nearest_year(anchor)
        if not year:
            continue
        report_url = urljoin(source_url, href)
        key = (year, name, report_url)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_record_id": _sid(year, name, report_url),
                "report_year_raw": year,
                "insurer_name_raw": name,
                "report_url": report_url,
                "source_url": source_url,
                "retrieved_at_utc": retrieved_at,
            }
        )

    if not rows:
        raise RuntimeError("OCS annual-report parser found zero report links")
    return rows


def _get(session: requests.Session, url: str) -> tuple[str, str]:
    response = session.get(url, timeout=HTTP.timeout)
    response.raise_for_status()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return response.text, retrieved_at


def _assert_unique(df: pd.DataFrame, column: str, label: str) -> None:
    if df[column].isna().any() or df[column].eq("").any():
        raise RuntimeError(f"{label}: null/empty {column}")
    if df[column].duplicated().any():
        raise RuntimeError(f"{label}: duplicate {column}")


def run(root: Path | None = None, *, force: bool = False) -> dict:
    root = root or PROJECT_ROOT
    insurers_path = root / INSURERS_OUT_REL
    annual_path = root / ANNUAL_OUT_REL
    if not force and file_has_data(insurers_path) and file_has_data(annual_path):
        insurers_existing = pd.read_csv(insurers_path, dtype=str, low_memory=False)
        annual_existing = pd.read_csv(annual_path, dtype=str, low_memory=False)
        return {
            "rows": len(insurers_existing) + len(annual_existing),
            "paths": [str(insurers_path), str(annual_path)],
            "errors": [],
        }

    logger = setup_logging("scrape_ocs_insurers")
    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    try:
        insurer_html, insurer_at = _get(session, INSURERS_URL)
        annual_html, annual_at = _get(session, ANNUAL_URL)
    finally:
        session.close()

    insurers = pd.DataFrame(
        parse_insurers(insurer_html, source_url=INSURERS_URL, retrieved_at=insurer_at),
        columns=INSURER_COLUMNS,
    )
    annual = pd.DataFrame(
        parse_annual_reports(annual_html, source_url=ANNUAL_URL, retrieved_at=annual_at),
        columns=ANNUAL_COLUMNS,
    )
    _assert_unique(insurers, "source_record_id", "OCS insurers")
    _assert_unique(annual, "source_record_id", "OCS annual reports")

    insurers = apply_post_ingest(insurers, source_id=SOURCE_ID, root=root)
    annual = apply_post_ingest(annual, source_id=SOURCE_ID, root=root)
    insurers_path.parent.mkdir(parents=True, exist_ok=True)
    insurers.to_csv(insurers_path, index=False, encoding="utf-8")
    annual.to_csv(annual_path, index=False, encoding="utf-8")
    logger.info(
        "OCS: %s current insurer rows; %s annual-report observations",
        len(insurers),
        len(annual),
    )
    return {
        "rows": len(insurers) + len(annual),
        "paths": [str(insurers_path), str(annual_path)],
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(f"OCS insurer registry: {result['rows']:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
