"""
Scrape the ASG registered-bidder registry from asg.pr.gov/suplidores.

ASG maintains Puerto Rico's two central vendor registries — the Registro Único
de Licitadores (RUL) and the Registro Único de Proveedores (RUP) — and publishes
them as a paginated HTML table. Each vendor carries a **Licitador ID**, a stable
government-issued identifier for a PR government bidder that MoneySweep has no
other source for, plus a fiscal address whose municipality feeds geo attribution.

Table shape: every vendor is TWO rows. A summary row

    <tr data-group="50727"><td>50727</td><td>10-8 InService</td><td>…pills…</td>

is followed by a collapsed detail row carrying the rest:

    <tr class="detail-row" data-group="50727">
        Domicilio Fiscal   PO BOX 629 / Salinas, PR, 00751
        Datos de Contacto  info@… / (866) 496-8108
        Información de RUL  Estatus, Número de Certificado, Emisión, Vencimiento
        Información de RUP  (same four fields)

Both rows are already in the page, so no per-vendor request is needed — but they
must be paired on ``data-group``, which is why this uses lxml rather than
pandas.read_html (read_html flattens the panel across all four columns and the
detail rows come back as duplicated prose). Dates live in a ``data-date``
attribute in ISO form, so they need no locale-aware parsing.

Output is ``scripts.contractor_schema.CONTRACTOR_COLUMNS`` plus geo_zip — the same
contractor-reference schema download_active_contractors writes, so this becomes
the live-scrape producer for that shape rather than a parallel one (mirroring how
scrape_ocpr_contracts shares ingest_ocpr_contracts' columns).

Paging note: requesting a page past the end **clamps to the last page** rather
than returning an empty one, so the walk stops on the declared page count with a
repeated-page check as a backstop. Same trap as comprasemergencias.

Output:
  data/staging/processed/pr_asg_suppliers.csv

Usage:
  python3 scripts/scrape_asg_suppliers.py
  python3 scripts/scrape_asg_suppliers.py --force
  python3 scripts/scrape_asg_suppliers.py --max-pages 2   # smoke test
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests
from lxml import html as lxml_html

from moneysweep.runtime.base_downloader import HttpConfig, build_session, file_has_data
from moneysweep.runtime.post_ingest import apply_post_ingest
from moneysweep.runtime.retry_runtime import RetryExhausted, RetryPolicy, with_retry
from scripts.build_unified_master import _normalize_name
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.contractor_schema import CONTRACTOR_COLUMNS

SOURCE_ID = "asg_suppliers"
BASE_URL = "https://asg.pr.gov/suplidores"
OUT_PATH_REL = "data/staging/processed/pr_asg_suppliers.csv"

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; MoneySweep/1.0; PR public-money research)",
    max_retries=3,
    base_delay_seconds=5.0,
    max_delay_seconds=30.0,
    page_sleep=0.3,
    rate_limit_sleep=60.0,
    timeout=30,
)
RETRY_POLICY = RetryPolicy(
    max_attempts=HTTP.max_retries,
    base_delay_seconds=HTTP.base_delay_seconds,
    max_delay_seconds=HTTP.max_delay_seconds,
)

# Output is the shared contractor-reference schema plus geo_zip: ASG serializes a
# missing city as the literal string "None" ("None, PR, 00901") but still gives a
# real postal code, and geo_zip is the first thing geo attribution looks at, so
# carrying it lets those vendors still resolve to a municipality.
# Fields ASG publishes that the shared contractor schema has no column for. They
# stay here rather than widening CONTRACTOR_COLUMNS, because no other contractor
# producer can fill them — the RUL/RUP certificates and the two registry statuses
# exist only in ASG's registries. `naics_code` is NOT in this list: that column
# already exists in the shared schema and was simply being written empty.
SUPPLIER_EXTRA_COLUMNS = [
    "naics_descriptions",
    "rul_status",
    "rup_status",
    "rul_certificate",
    "rup_certificate",
    "contact_email",
    "contact_phone",
]

# Output is the shared contractor-reference schema plus geo_zip and the ASG-only
# fields above.
SUPPLIER_COLUMNS = [*CONTRACTOR_COLUMNS, "geo_zip", *SUPPLIER_EXTRA_COLUMNS]

_PAGE_COUNT_RE = re.compile(r"P[áa]gina\s*\d+\s*de\s*(\d+)", re.I)
# "Código: 61171" inside .naics-list. Codes and their Spanish descriptions
# alternate as sibling <div>s, so the label is what marks a code line.
_NAICS_CODE_RE = re.compile(r"C[óo]digo:\s*(\d+)", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# "(866) 496-8108" and the looser variants ASG mixes in.
_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?:x|ext\.?)\s*\d+)?", re.I)
# "Salinas, PR, 00751" — the last address line, which is where the municipality
# and postal code live. The street/PO-BOX line above it varies too much to key on.
_CITY_LINE_RE = re.compile(r"^(.*?),\s*PR\s*,?\s*(\d{5})?\s*$", re.I)
# ASG renders an absent field by interpolating Python's None into the template.
# Left alone it would enter the registry as a municipality named "None".
_PLACEHOLDERS = {"", "none", "n/a", "na", "null", "-"}


class _RateLimited(Exception):
    """Internal marker so a 429 is retried by with_retry (mirrors base_downloader)."""


def _page_url(page: int) -> str:
    return f"{BASE_URL}?page={page}&order_by=companyname"


def declared_page_count(html: str) -> int | None:
    """Total pages from the "Página 1 de 47" marker, or None if absent."""
    match = _PAGE_COUNT_RE.search(html)
    return int(match.group(1)) if match else None


def _text(node) -> str:
    return " ".join(node.text_content().split()) if node is not None else ""


def _section_fields(col) -> dict[str, str]:
    """The ``.info-label`` / ``.info-value`` pairs inside one RUL or RUP column.

    Both sections use identical labels ("Número de Certificado", "Fecha de
    Vencimiento"), so they can only be told apart by the column they sit in —
    reading labels document-wide would silently mix RUL and RUP values.
    """
    fields: dict[str, str] = {}
    for label in col.xpath('.//div[contains(@class, "info-label")]'):
        value = label.getnext()
        if value is None:
            continue
        # Dates render as an empty <span data-date="2026-12-03T00:00:00"> that
        # client-side JS formats, so text_content() is blank and the attribute
        # is the only place the date exists.
        stamps = value.xpath(".//*[@data-date]/@data-date")
        fields[_text(label)] = str(stamps[0])[:10] if stamps else _text(value)
    return fields


def _address_parts(detail) -> tuple[str, str]:
    """(municipality, postal_code) from the Domicilio Fiscal block."""
    for label in detail.xpath('.//div[@class="info-label"]'):
        if _text(label) != "Domicilio Fiscal":
            continue
        value = label.getnext()
        if value is None:
            return "", ""
        lines = [ln.strip() for ln in value.text_content().split("\n") if ln.strip()]
        for line in reversed(lines):
            match = _CITY_LINE_RE.match(" ".join(line.split()))
            if match:
                municipality = match.group(1).strip()
                if municipality.casefold() in _PLACEHOLDERS:
                    municipality = ""
                return municipality, (match.group(2) or "").strip()
        return "", ""
    return "", ""


def _naics_parts(detail) -> tuple[str, str]:
    """(codes, descriptions) from the Clasificación NAICS block, pipe-delimited.

    The block alternates ``<div>Código: 61171</div>`` with a description div, so
    a code's label is what identifies it and the following sibling carries its
    text. Vendors carry anywhere from 1 to ~21 classifications, and the pipe
    delimiter matches how aliases are already packed in
    data/reference/pr_public_money_entities.csv.
    """
    codes: list[str] = []
    descriptions: list[str] = []

    for block in detail.xpath('.//*[contains(@class, "naics-list")]'):
        for node in block.xpath("./div"):
            match = _NAICS_CODE_RE.search(_text(node))
            if not match:
                continue
            codes.append(match.group(1))
            following = node.getnext()
            # A trailing code with no description must not swallow the next
            # code line as its own label.
            text = _text(following) if following is not None else ""
            descriptions.append("" if _NAICS_CODE_RE.search(text) else text)

    return "|".join(codes), "|".join(descriptions)


def _contact_parts(detail) -> tuple[str, str]:
    """(email, phone) from the Datos de Contacto block."""
    for label in detail.xpath('.//div[contains(@class, "info-label")]'):
        if _text(label) != "Datos de Contacto":
            continue
        value = label.getnext()
        if value is None:
            break
        text = _text(value)
        email = _EMAIL_RE.search(text)
        phone = _PHONE_RE.search(text)
        return (email.group(0) if email else ""), (phone.group(0).strip() if phone else "")
    return "", ""


def _contractor_type(rul: dict, rup: dict) -> str:
    """Which of the two central registries the vendor actually appears in."""
    registries = []
    if rul.get("RUL Estatus"):
        registries.append("RUL")
    if rup.get("RUP Estatus"):
        registries.append("RUP")
    return "+".join(registries)


def _normalize_row(summary: dict, detail: dict) -> dict:
    """One vendor's summary + detail fields to a SUPPLIER_COLUMNS row."""
    entity_name = summary.get("entity_name", "")
    rul = detail.get("rul", {})
    rup = detail.get("rup", {})
    # Prefer RUP (proveedores, the broader registry) and fall back to RUL, so a
    # vendor listed in only one still gets its dates.
    issued = rup.get("Fecha de Emisión") or rul.get("Fecha de Emisión") or ""
    expires = rup.get("Fecha de Vencimiento") or rul.get("Fecha de Vencimiento") or ""

    row = {col: "" for col in SUPPLIER_COLUMNS}
    row.update(
        {
            "entity_name": entity_name,
            "entity_normalized": _normalize_name(entity_name),
            "registration_id": summary.get("registration_id", ""),
            "registration_date": issued,
            "expiry_date": expires,
            "contractor_type": _contractor_type(rul, rup),
            "naics_code": detail.get("naics_code", ""),
            "municipality": detail.get("municipality", ""),
            "status": summary.get("status", ""),
            "source_file": "asg.pr.gov/suplidores",
            "geo_zip": detail.get("postal_code", ""),
            "naics_descriptions": detail.get("naics_descriptions", ""),
            "rul_status": rul.get("RUL Estatus", ""),
            "rup_status": rup.get("RUP Estatus", ""),
            "rul_certificate": rul.get("Número de Certificado", ""),
            "rup_certificate": rup.get("Número de Certificado", ""),
            "contact_email": detail.get("contact_email", ""),
            "contact_phone": detail.get("contact_phone", ""),
        }
    )
    return row


def parse_records(html: str) -> list[dict]:
    """Pair each vendor's summary row with its detail row, one dict per vendor."""
    doc = lxml_html.fromstring(html)

    details: dict[str, dict] = {}
    for detail in doc.xpath('//tr[contains(@class, "detail-row")][@data-group]'):
        group = str(detail.get("data-group") or "")
        municipality, postal_code = _address_parts(detail)
        columns = detail.xpath('.//div[contains(@class, "info-col")]')
        rul: dict[str, str] = {}
        rup: dict[str, str] = {}
        for col in columns:
            heading = " ".join(
                " ".join(h.text_content().split())
                for h in col.xpath('.//span[contains(@class, "section-header")]')
            )
            if "RUL" in heading:
                rul = _section_fields(col)
            elif "RUP" in heading:
                rup = _section_fields(col)
        naics_code, naics_descriptions = _naics_parts(detail)
        contact_email, contact_phone = _contact_parts(detail)
        details[group] = {
            "municipality": municipality,
            "postal_code": postal_code,
            "naics_code": naics_code,
            "naics_descriptions": naics_descriptions,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "rul": rul,
            "rup": rup,
        }

    records = []
    for summary in doc.xpath('//tr[@data-group][not(contains(@class, "detail-row"))]'):
        cells = summary.xpath("./td")
        if len(cells) < 3:
            continue
        group = str(summary.get("data-group") or "")
        registration_id = _text(cells[0])
        entity_name = _text(cells[1])
        if not registration_id or not entity_name:
            continue
        records.append(
            {
                "summary": {
                    "registration_id": registration_id,
                    "entity_name": entity_name,
                    "status": _text(cells[2]),
                },
                "detail": details.get(group, {}),
            }
        )
    return records


def _fetch_page(session: requests.Session, page: int, logger) -> str | None:
    """GET one listing page. None on a terminal 4xx or retry exhaustion."""

    def _once() -> str | None:
        resp = session.get(_page_url(page), timeout=HTTP.timeout)
        if resp.status_code == 429:
            logger.warning(f"  Rate limited on page {page} — sleeping {HTTP.rate_limit_sleep}s")
            time.sleep(HTTP.rate_limit_sleep)
            raise _RateLimited()
        if 400 <= resp.status_code < 500:
            logger.error(f"  HTTP {resp.status_code} on page {page}")
            return None
        resp.raise_for_status()
        time.sleep(HTTP.page_sleep)
        return resp.text

    try:
        return with_retry(
            _once, policy=RETRY_POLICY, retry_on=(requests.RequestException, _RateLimited)
        )
    except RetryExhausted as exc:
        logger.error(f"  Page {page} failed: {exc}")
        return None


def fetch_all_records(
    session: requests.Session, logger, max_pages: int | None = None
) -> tuple[list[dict], bool]:
    """Walk every page. Returns (records, truncated) — see the module docstring
    on why the walk cannot simply stop at the first empty page."""
    records: list[dict] = []
    truncated = False
    total_pages: int | None = None
    previous_signature: tuple[str, ...] | None = None
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break
        if total_pages is not None and page > total_pages:
            break

        html = _fetch_page(session, page, logger)
        if html is None:
            truncated = True
            break

        if total_pages is None:
            total_pages = declared_page_count(html)
            logger.info(f"  declared pages: {total_pages if total_pages else 'unknown'}")

        batch = parse_records(html)
        if not batch:
            break

        signature = tuple(r["summary"]["registration_id"] for r in batch)
        if signature == previous_signature:
            logger.info(f"  page {page} repeated page {page - 1} — stopping")
            break
        previous_signature = signature

        records.extend(batch)
        if page % 10 == 0:
            logger.info(f"    page {page}: {len(records):,} vendors so far")
        page += 1

    return records, truncated


def run(root=None, force: bool = False, max_pages: int | None = None) -> dict:
    return _run(root=root, force=force, max_pages=max_pages)


def _run(root=None, force: bool = False, max_pages: int | None = None) -> dict:
    if root is None:
        root = PROJECT_ROOT
    out_path = Path(root) / OUT_PATH_REL
    logger = setup_logging("scrape_asg_suppliers")
    logger.info("Starting ASG supplier-registry scrape...")

    if not force and file_has_data(out_path):
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        logger.info(f"  {out_path.name} exists ({len(existing):,} rows) — skipping.")
        return {"status": "OK", "rows": len(existing), "path": str(out_path), "errors": []}

    session = build_session(HTTP.user_agent, HTTP.extra_headers)
    try:
        raw_records, truncated = fetch_all_records(session, logger, max_pages=max_pages)
    finally:
        session.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not raw_records:
        pd.DataFrame(columns=SUPPLIER_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {
            "status": "ERROR",
            "rows": 0,
            "path": str(out_path),
            "errors": ["No vendors fetched from asg.pr.gov/suplidores"],
        }

    rows = [_normalize_row(r["summary"], r["detail"]) for r in raw_records]
    frame = pd.DataFrame(rows, columns=SUPPLIER_COLUMNS)
    frame = frame.drop_duplicates(subset=["registration_id"])
    frame = apply_post_ingest(frame, source_id=SOURCE_ID, root=Path(root))
    frame.to_csv(out_path, index=False, encoding="utf-8")

    errors = []
    if truncated:
        msg = (
            f"Scrape stopped early after a page fetch failure — only "
            f"{len(frame):,} vendors captured; re-run with --force once the "
            f"endpoint recovers"
        )
        logger.error(f"  {msg}")
        errors.append(msg)

    logger.info("=" * 60)
    logger.info("ASG SUPPLIER REGISTRY SCRAPE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total vendors:   {len(frame):,}")
    logger.info(f"  By registry:     {frame['contractor_type'].value_counts().to_dict()}")
    logger.info(f"  With municipality: {(frame['municipality'] != '').sum():,}")

    return {
        "status": "TRUNCATED" if truncated else "OK",
        "rows": len(frame),
        "path": str(out_path),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape the ASG registered-bidder registry")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--max-pages", type=int, default=None, help="Limit pages fetched (smoke testing)"
    )
    args = parser.parse_args()
    result = _run(force=args.force, max_pages=args.max_pages)
    print(f"\nASG supplier scrape complete: {result['rows']:,} vendors")
    return 1 if result["errors"] and result["rows"] == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
