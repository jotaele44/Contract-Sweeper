"""Materialize Puerto Rico Foreign-Trade Zones Board zone/site records.

The discovery denominator is frozen to the three Puerto Rico zones independently
confirmed on the FTZ Board public information system: 7, 61 and 163. The numeric
OFIS detail ids are transport locators only; the producer verifies the returned
zone number before retaining anything.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from lxml import html as lxml_html

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.post_ingest import apply_post_ingest
from scripts.config import PROJECT_ROOT, setup_logging

SOURCE_ID = "ftz_board_pr"
OUT_REL = "data/staging/processed/pr_ftz_zones_sites.csv"
DETAILS = {"007": 103, "061": 239, "163": 115}
BASE = "https://ofis.trade.gov/Zones/Details/{detail_id}"
COLUMNS = [
    "source_record_id",
    "record_type",
    "zone_number_raw",
    "approved_date_raw",
    "grantee_raw",
    "location_raw",
    "zone_status_raw",
    "port_of_entry_raw",
    "activation_limit_raw",
    "total_activated_acres_raw",
    "site_number_raw",
    "site_name_raw",
    "site_status_raw",
    "activated_acres_raw",
    "sunset_expiration_lapse_date_raw",
    "source_detail_id",
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


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def _sid(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _lines(doc) -> list[str]:
    return [x.strip() for x in doc.text_content().splitlines() if x.strip()]


def _label_value(lines: list[str], label: str) -> str:
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            return lines[i + 1]
    return ""


def _site_rows(doc) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for table in doc.xpath("//table"):
        headers = [_clean(x.text_content()) for x in table.xpath(".//thead//th")]
        if not headers:
            first = table.xpath(".//tr[1]/th|.//tr[1]/td")
            headers = [_clean(x.text_content()) for x in first]
        if "Site Number" not in headers or "Site Name" not in headers:
            continue
        body_rows = table.xpath(".//tbody/tr") or table.xpath(".//tr[position()>1]")
        for tr in body_rows:
            cells = [_clean(x.text_content()) for x in tr.xpath("./td")]
            if len(cells) < 4:
                continue
            cells += [""] * (5 - len(cells))
            rows.append(
                {
                    "site_number_raw": cells[0],
                    "site_name_raw": cells[1],
                    "site_status_raw": cells[2],
                    "activated_acres_raw": cells[3],
                    "sunset_expiration_lapse_date_raw": cells[4],
                }
            )
        break
    return rows


def parse_zone(
    page_html: str,
    *,
    detail_id: int,
    source_url: str,
    retrieved_at: str,
) -> list[dict]:
    doc = lxml_html.fromstring(page_html)
    lines = _lines(doc)
    zone = _label_value(lines, "Zone Number")
    if zone.isdigit():
        zone = zone.zfill(3)
    if not zone:
        raise RuntimeError(f"FTZ detail {detail_id}: missing Zone Number")

    base = {
        "zone_number_raw": zone,
        "approved_date_raw": _label_value(lines, "Approved on Date"),
        "grantee_raw": _label_value(lines, "Grantee"),
        "location_raw": _label_value(lines, "Location"),
        "zone_status_raw": _label_value(lines, "Status"),
        "port_of_entry_raw": _label_value(lines, "Port of Entry"),
        "activation_limit_raw": _label_value(lines, "Activation Limit"),
        "total_activated_acres_raw": _label_value(lines, "Total Activated Acres"),
        "source_detail_id": str(detail_id),
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at,
    }

    output: list[dict] = []
    zone_row = {col: "" for col in COLUMNS}
    zone_row.update(base)
    zone_row["record_type"] = "zone"
    zone_row["source_record_id"] = _sid("zone", zone, str(detail_id))
    output.append(zone_row)

    for site in _site_rows(doc):
        row = {col: "" for col in COLUMNS}
        row.update(base)
        row.update(site)
        row["record_type"] = "site"
        row["source_record_id"] = _sid("site", zone, site["site_number_raw"], site["site_name_raw"])
        output.append(row)
    return output


def run(root: Path | None = None, *, force: bool = False) -> dict:
    root = root or PROJECT_ROOT
    out_path = root / OUT_REL
    if not force and file_has_data(out_path):
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        return {"rows": len(existing), "path": str(out_path), "errors": []}

    logger = setup_logging("scrape_ftz_board_pr")
    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    rows: list[dict] = []
    observed: set[str] = set()
    try:
        for expected_zone, detail_id in DETAILS.items():
            url = BASE.format(detail_id=detail_id)
            response = session.get(url, timeout=HTTP.timeout)
            response.raise_for_status()
            retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            parsed = parse_zone(
                response.text,
                detail_id=detail_id,
                source_url=url,
                retrieved_at=retrieved_at,
            )
            actual = parsed[0]["zone_number_raw"]
            if actual != expected_zone:
                raise RuntimeError(
                    f"FTZ locator mismatch: detail_id={detail_id} "
                    f"expected={expected_zone} observed={actual}"
                )
            if actual in observed:
                raise RuntimeError(f"FTZ duplicate zone: {actual}")
            observed.add(actual)
            rows.extend(parsed)
    finally:
        session.close()

    expected = set(DETAILS)
    if observed != expected:
        raise RuntimeError(
            f"FTZ denominator mismatch: expected={sorted(expected)} observed={sorted(observed)}"
        )

    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty or int((df["record_type"] == "zone").sum()) != len(expected):
        raise RuntimeError("FTZ zone arithmetic closure failed")
    if df["source_record_id"].duplicated().any():
        raise RuntimeError("FTZ duplicate source_record_id")
    if df["zone_number_raw"].isna().any() or df["zone_number_raw"].eq("").any():
        raise RuntimeError("FTZ null zone_number_raw")

    df = apply_post_ingest(df, source_id=SOURCE_ID, root=root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    logger.info("FTZ Board PR: %s rows across %s zones", len(df), len(expected))
    return {"rows": len(df), "path": str(out_path), "errors": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(f"FTZ Board PR: {result['rows']:,} rows -> {result['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
