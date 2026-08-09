"""Materialize Financial Oversight and Management Board (FOMB) public records.

The producer is deliberately provenance-first. It enumerates FOMB collection
pages, preserves the exact response body and HTTP metadata for every discovery
surface, creates a content-addressed document manifest, normalizes contract
review observations when the live table can be enumerated, derives temporal
fiscal-document version edges without deleting superseded records, and builds
non-destructive crosswalk candidates against locally materialized Puerto Rico
contract/entity sources.

FOMB currently mixes server-rendered historical pages with JavaScript/DataTables
surfaces. Static links are always collected. For dynamic tables the producer
attempts to discover an inline AJAX endpoint and paginate it; if the site changes
shape, the raw discovery HTML remains authoritative evidence and the run reports
that collection as incomplete rather than fabricating rows.

Outputs:
  data/manifests/fomb_documents_manifest.jsonl
  data/staging/processed/pr_fomb_documents.csv
  data/staging/processed/pr_fomb_contract_reviews.csv
  data/staging/processed/pr_fomb_fiscal_versions.csv
  data/staging/processed/pr_fomb_crosswalk.csv
  data/raw/FOMB/discovery/*.html
  data/raw/FOMB/discovery/*.headers.json
  data/raw/FOMB/documents/<sha256>.<ext>

Usage:
  python3 scripts/download_fomb.py
  python3 scripts/download_fomb.py --no-download-documents
  python3 scripts/download_fomb.py --max-documents 50
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.runtime.base_downloader import HttpConfig, build_session
from scripts.config import PROJECT_ROOT, setup_logging

BASE_URL = "https://oversightboard.pr.gov/"
RAW_ROOT_REL = "data/raw/FOMB"
MANIFEST_REL = "data/manifests/fomb_documents_manifest.jsonl"
DOCUMENTS_REL = "data/staging/processed/pr_fomb_documents.csv"
CONTRACTS_REL = "data/staging/processed/pr_fomb_contract_reviews.csv"
VERSIONS_REL = "data/staging/processed/pr_fomb_fiscal_versions.csv"
CROSSWALK_REL = "data/staging/processed/pr_fomb_crosswalk.csv"

COLLECTIONS = {
    "documents": "documents/",
    "contract_review": "contract-review/",
    "fiscal_plans": "fiscal-plans/",
    "budgets": "budgets/",
    "related_documents_letters": "related-documents-and-letters/",
    "budget_reapportionments": "budget-reapportionment-requests/",
    "quarterly_financial_reports": "quarterly-financial-reports/",
    "debt": "debt/",
    "legislative_process": "legislative-process/",
    "reports": "fomb-reports/",
}

HTTP = HttpConfig(
    user_agent="Mozilla/5.0 (compatible; MoneySweep/1.0; public-record research)",
    max_retries=3,
    base_delay_seconds=2.0,
    max_delay_seconds=20.0,
    page_sleep=0.25,
    rate_limit_sleep=60.0,
    timeout=60,
)

DOCUMENT_COLUMNS = [
    "document_id",
    "collection",
    "title_raw",
    "document_type_raw",
    "publication_date",
    "source_url",
    "download_url",
    "retrieved_at",
    "http_status",
    "content_type",
    "byte_size",
    "sha256",
    "duplicate_content_group",
    "local_path",
]
CONTRACT_COLUMNS = [
    "fomb_review_id",
    "government_entity_raw",
    "counterparty_raw",
    "amount_raw",
    "amount_numeric",
    "currency",
    "status_raw",
    "completed_date",
    "review_document_url",
    "contract_number_candidate",
    "source_url",
    "retrieved_at",
]
VERSION_COLUMNS = [
    "document_id",
    "collection",
    "covered_entity",
    "fiscal_year",
    "document_class",
    "version_label",
    "publication_date",
    "supersedes_document_id",
    "source_url",
]
CROSSWALK_COLUMNS = [
    "fomb_review_id",
    "local_source",
    "local_record_id",
    "match_basis",
    "match_confidence",
    "amount_delta",
    "date_delta_days",
    "entity_conflict",
    "counterparty_conflict",
    "status_conflict",
]

_DATE_RE = re.compile(r"\b(20\d{2})[-_/](0?[1-9]|1[0-2])[-_/]([0-2]?\d|3[01])\b")
_YEAR_RE = re.compile(r"\b(?:FY\s*)?(20\d{2})\b", re.I)
_AMOUNT_RE = re.compile(r"-?\$?\s*([\d,]+(?:\.\d{1,2})?)")
_CONTRACT_RE = re.compile(r"\b20\d{2}-\d{6}(?:-[A-Z0-9]+)?\b", re.I)
_AJAX_URL_PATTERNS = [
    re.compile(r"ajax\s*:\s*['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"(?:ajaxUrl|ajax_url|dataUrl|data_url)\s*[:=]\s*['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"['\"]url['\"]\s*:\s*['\"]([^'\"]*(?:admin-ajax|wp-json|contract)[^'\"]*)['\"]", re.I),
]


@dataclass
class Link:
    href: str
    text: str


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        self._href = values.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append(Link(self._href, text))
            self._href = None
            self._text = []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", query, ""))


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    m = _AMOUNT_RE.search(str(value))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _publication_date(text: str) -> str:
    m = _DATE_RE.search(text or "")
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _extract_links(page_html: str, page_url: str) -> list[Link]:
    parser = _LinkParser()
    parser.feed(page_html)
    seen: set[tuple[str, str]] = set()
    out: list[Link] = []
    for link in parser.links:
        href = _canonical_url(urljoin(page_url, html.unescape(link.href)))
        key = (href, link.text)
        if key not in seen:
            seen.add(key)
            out.append(Link(href, link.text))
    return out


def _looks_like_document(url: str, text: str) -> bool:
    lower = url.lower()
    if any(lower.endswith(ext) or f"{ext}?" in lower for ext in (".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx")):
        return True
    if any(host in lower for host in ("docs.oversightboard.pr.gov", "drive.google.com", "docs.google.com")):
        return True
    return "download" in _norm(text) and urlparse(url).netloc not in {"", urlparse(BASE_URL).netloc}


def _classify_title(title: str, collection: str) -> tuple[str, str, str, str]:
    n = _norm(title)
    entity = ""
    entity_map = {
        "commonwealth": "Commonwealth of Puerto Rico",
        "prepa": "Puerto Rico Electric Power Authority",
        "puerto rico electric power authority": "Puerto Rico Electric Power Authority",
        "prasa": "Puerto Rico Aqueduct and Sewer Authority",
        "puerto rico aqueduct": "Puerto Rico Aqueduct and Sewer Authority",
        "university of puerto rico": "University of Puerto Rico",
        "upr": "University of Puerto Rico",
        "highway and transportation authority": "Puerto Rico Highways and Transportation Authority",
        "hta": "Puerto Rico Highways and Transportation Authority",
        "pridco": "Puerto Rico Industrial Development Company",
        "crim": "Municipal Revenue Collections Center",
        "cofina": "Puerto Rico Sales Tax Financing Corporation",
        "cossec": "Public Corporation for Supervision and Insurance of Cooperatives",
        "gdb": "Government Development Bank for Puerto Rico",
    }
    for needle, canonical in entity_map.items():
        if needle in n:
            entity = canonical
            break
    year_m = _YEAR_RE.search(title or "")
    fiscal_year = year_m.group(1) if year_m else ""
    if "fiscal plan" in n:
        doc_class = "fiscal_plan"
    elif "budget" in n and "reapportion" not in n:
        doc_class = "budget"
    elif "reapportion" in n or "reprogram" in n:
        doc_class = "budget_reapportionment"
    elif "quarterly" in n and "report" in n:
        doc_class = "quarterly_financial_report"
    elif collection == "contract_review":
        doc_class = "contract_review"
    elif collection == "legislative_process":
        doc_class = "legislative_review"
    elif collection == "debt":
        doc_class = "debt"
    else:
        doc_class = collection
    version = "revised" if "revised" in n or "amended" in n else "certified" if "certified" in n else ""
    return entity, fiscal_year, doc_class, version


def _discover_ajax_url(page_html: str, page_url: str) -> str | None:
    decoded = html.unescape(page_html).replace("\\/", "/")
    candidates: list[str] = []
    for pattern in _AJAX_URL_PATTERNS:
        candidates.extend(pattern.findall(decoded))
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or "{{" in candidate or "<%" in candidate:
            continue
        return urljoin(page_url, candidate)
    return None


def _json_rows(payload: Any) -> tuple[list[Any], int | None]:
    if isinstance(payload, list):
        return payload, len(payload)
    if not isinstance(payload, dict):
        return [], None
    for key in ("data", "rows", "results", "aaData"):
        rows = payload.get(key)
        if isinstance(rows, list):
            total = payload.get("recordsFiltered") or payload.get("recordsTotal") or payload.get("total")
            try:
                total = int(total) if total is not None else None
            except (TypeError, ValueError):
                total = None
            return rows, total
    nested = payload.get("data")
    if isinstance(nested, dict):
        return _json_rows(nested)
    return [], None


def _row_value(row: Any, *keys: str) -> str:
    if isinstance(row, dict):
        normalized = {_norm(k).replace(" ", ""): v for k, v in row.items()}
        for key in keys:
            value = normalized.get(_norm(key).replace(" ", ""))
            if value not in (None, ""):
                return str(value).strip()
    if isinstance(row, list):
        # FOMB public contract table order: Entity, Counterpart, Amount, Status, Completed, Document.
        positions = {"entity": 0, "counterpart": 1, "amount": 2, "status": 3, "completed": 4, "document": 5}
        for key in keys:
            idx = positions.get(_norm(key).replace(" ", ""))
            if idx is not None and idx < len(row):
                return re.sub(r"<[^>]+>", "", str(row[idx])).strip()
    return ""


def _document_href_from_value(value: str, page_url: str) -> str:
    m = re.search(r"href=['\"]([^'\"]+)['\"]", value or "", re.I)
    if m:
        return _canonical_url(urljoin(page_url, html.unescape(m.group(1))))
    if str(value).startswith(("http://", "https://")):
        return _canonical_url(str(value))
    return ""


def _enumerate_contract_reviews(session: requests.Session, page_html: str, page_url: str, retrieved_at: str, logger) -> tuple[list[dict[str, Any]], str | None]:
    ajax_url = _discover_ajax_url(page_html, page_url)
    if not ajax_url:
        return [], None
    records: list[dict[str, Any]] = []
    start = 0
    length = 500
    while True:
        params = {"draw": 1, "start": start, "length": length}
        try:
            response = session.get(ajax_url, params=params, timeout=HTTP.timeout)
            if response.status_code in (400, 404, 405):
                response = session.post(ajax_url, data=params, timeout=HTTP.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("FOMB contract AJAX enumeration stopped at start=%s: %s", start, exc)
            break
        rows, total = _json_rows(payload)
        if not rows:
            break
        for raw in rows:
            entity = _row_value(raw, "entity", "government entity", "agency")
            counterpart = _row_value(raw, "counterpart", "counterparty", "contractor")
            amount_raw = _row_value(raw, "amount")
            status = _row_value(raw, "status")
            completed = _row_value(raw, "completed", "completed date", "date")
            document_value = _row_value(raw, "document", "download", "url")
            review_document_url = _document_href_from_value(document_value, page_url)
            stable = "|".join([_norm(entity), _norm(counterpart), amount_raw, completed, review_document_url])
            contract_m = _CONTRACT_RE.search(" ".join([counterpart, document_value]))
            records.append({
                "fomb_review_id": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24],
                "government_entity_raw": entity,
                "counterparty_raw": counterpart,
                "amount_raw": amount_raw,
                "amount_numeric": _parse_amount(amount_raw),
                "currency": "USD" if "$" in amount_raw or amount_raw else "",
                "status_raw": status,
                "completed_date": _publication_date(completed),
                "review_document_url": review_document_url,
                "contract_number_candidate": contract_m.group(0).upper() if contract_m else "",
                "source_url": page_url,
                "retrieved_at": retrieved_at,
            })
        start += len(rows)
        if len(rows) < length or (total is not None and start >= total):
            break
    return records, ajax_url


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in columns})


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except (OSError, csv.Error, UnicodeError):
        return []


def _build_crosswalk(root: Path, reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        ("ocpr_contracts", root / "data/staging/processed/pr_ocpr_contracts.csv"),
        ("transition_contracts", root / "data/staging/processed/pr_transition_contracts.csv"),
        ("act_transition", root / "data/staging/processed/pr_act_transition_contracts.csv"),
        ("acuden_transition", root / "data/staging/processed/pr_acuden_transition_contracts.csv"),
    ]
    output: list[dict[str, Any]] = []
    for source_name, path in candidates:
        for local in _load_csv(path):
            local_contract = str(local.get("contract_number") or local.get("contract_id") or "").strip()
            local_entity = str(local.get("agency") or local.get("entity") or local.get("government_entity") or "")
            local_counterparty = str(local.get("contractor_name") or local.get("contractor") or local.get("counterparty") or "")
            local_amount = _parse_amount(local.get("contract_amount") or local.get("amount"))
            local_date = str(local.get("grant_date") or local.get("date_of_grant") or local.get("start_date") or "")
            for review in reviews:
                basis: list[str] = []
                score = 0.0
                if review.get("contract_number_candidate") and local_contract and _norm(review["contract_number_candidate"]) == _norm(local_contract):
                    basis.append("contract_number")
                    score += 0.70
                if _norm(review.get("government_entity_raw")) and _norm(review.get("government_entity_raw")) == _norm(local_entity):
                    basis.append("entity_exact")
                    score += 0.15
                if _norm(review.get("counterparty_raw")) and _norm(review.get("counterparty_raw")) == _norm(local_counterparty):
                    basis.append("counterparty_exact")
                    score += 0.20
                f_amount = review.get("amount_numeric")
                amount_delta = None
                if f_amount is not None and local_amount is not None:
                    amount_delta = round(float(f_amount) - float(local_amount), 2)
                    tolerance = max(1.0, abs(float(f_amount)) * 0.001)
                    if abs(amount_delta) <= tolerance:
                        basis.append("amount_close")
                        score += 0.10
                if score < 0.35:
                    continue
                output.append({
                    "fomb_review_id": review["fomb_review_id"],
                    "local_source": source_name,
                    "local_record_id": local_contract or hashlib.sha256(json.dumps(local, sort_keys=True).encode()).hexdigest()[:20],
                    "match_basis": ";".join(basis),
                    "match_confidence": min(round(score, 3), 1.0),
                    "amount_delta": "" if amount_delta is None else amount_delta,
                    "date_delta_days": "",
                    "entity_conflict": bool(local_entity and review.get("government_entity_raw") and _norm(local_entity) != _norm(review.get("government_entity_raw"))),
                    "counterparty_conflict": bool(local_counterparty and review.get("counterparty_raw") and _norm(local_counterparty) != _norm(review.get("counterparty_raw"))),
                    "status_conflict": False,
                })
    output.sort(key=lambda row: (-float(row["match_confidence"]), row["fomb_review_id"], row["local_source"], row["local_record_id"]))
    return output


def _build_versions(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        entity, fiscal_year, doc_class, version = _classify_title(doc.get("title_raw", ""), doc.get("collection", ""))
        if doc_class not in {"fiscal_plan", "budget", "budget_reapportionment"}:
            continue
        rows.append({
            "document_id": doc["document_id"],
            "collection": doc["collection"],
            "covered_entity": entity,
            "fiscal_year": fiscal_year,
            "document_class": doc_class,
            "version_label": version,
            "publication_date": doc.get("publication_date", ""),
            "supersedes_document_id": "",
            "source_url": doc.get("download_url") or doc.get("source_url"),
        })
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["covered_entity"], row["fiscal_year"], row["document_class"])
        grouped.setdefault(key, []).append(row)
    for group in grouped.values():
        group.sort(key=lambda r: (r["publication_date"], r["document_id"]))
        previous = ""
        for row in group:
            if previous and row["version_label"] in {"revised", "certified"}:
                row["supersedes_document_id"] = previous
            previous = row["document_id"]
    return sorted(rows, key=lambda r: (r["covered_entity"], r["fiscal_year"], r["document_class"], r["publication_date"], r["document_id"]))


def _extension_for(content_type: str, url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix
    return {
        "application/pdf": ".pdf",
        "text/csv": ".csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
    }.get((content_type or "").split(";")[0].strip().lower(), ".bin")


def run(root: Path | str | None = None, download_documents: bool = True, max_documents: int | None = None) -> dict[str, Any]:
    root = Path(root) if root is not None else PROJECT_ROOT
    logger = setup_logging("download_fomb")
    raw_root = root / RAW_ROOT_REL
    discovery_dir = raw_root / "discovery"
    content_dir = raw_root / "documents"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    content_dir.mkdir(parents=True, exist_ok=True)
    retrieved_at = _utc_now()
    session = build_session(HTTP.user_agent)

    documents: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    errors: list[str] = []
    collection_state: dict[str, Any] = {}

    for collection, rel in COLLECTIONS.items():
        page_url = urljoin(BASE_URL, rel)
        try:
            response = session.get(page_url, timeout=HTTP.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"{collection}: {exc}")
            collection_state[collection] = {"status": "ERROR", "source_url": page_url}
            continue
        body = response.content
        page_html = response.text
        (discovery_dir / f"{collection}.html").write_bytes(body)
        headers_payload = {
            "source_url": page_url,
            "retrieved_at": retrieved_at,
            "status_code": response.status_code,
            "headers": {k: v for k, v in response.headers.items() if k.lower() not in {"set-cookie"}},
            "sha256": _sha256_bytes(body),
            "byte_size": len(body),
        }
        (discovery_dir / f"{collection}.headers.json").write_text(json.dumps(headers_payload, indent=2, sort_keys=True), encoding="utf-8")

        links = _extract_links(page_html, page_url)
        doc_links = [link for link in links if _looks_like_document(link.href, link.text)]
        for link in doc_links:
            title = link.text or Path(urlparse(link.href).path).name
            stable = f"{collection}|{_canonical_url(link.href)}|{title}"
            documents.append({
                "document_id": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24],
                "collection": collection,
                "title_raw": title,
                "document_type_raw": _classify_title(title, collection)[2],
                "publication_date": _publication_date(title),
                "source_url": page_url,
                "download_url": link.href,
                "retrieved_at": retrieved_at,
                "http_status": "",
                "content_type": "",
                "byte_size": "",
                "sha256": "",
                "duplicate_content_group": "",
                "local_path": "",
            })
        state: dict[str, Any] = {"status": "OK", "source_url": page_url, "static_document_links": len(doc_links)}
        if collection == "contract_review":
            contract_rows, ajax_url = _enumerate_contract_reviews(session, page_html, page_url, retrieved_at, logger)
            reviews.extend(contract_rows)
            state["ajax_url"] = ajax_url or ""
            state["contract_rows"] = len(contract_rows)
            if ajax_url is None:
                state["status"] = "PARTIAL_DYNAMIC_ENDPOINT_UNDISCOVERED"
                errors.append("contract_review: dynamic table endpoint not discovered; raw HTML preserved")
        collection_state[collection] = state

    # Deduplicate observations by collection+URL+title, never by content hash.
    unique_docs: dict[str, dict[str, Any]] = {}
    for doc in documents:
        unique_docs[doc["document_id"]] = doc
    documents = list(unique_docs.values())
    documents.sort(key=lambda d: (d["collection"], d["publication_date"], d["title_raw"], d["download_url"]))

    if max_documents is not None:
        documents_to_fetch = documents[: max(0, max_documents)]
    else:
        documents_to_fetch = documents

    if download_documents:
        for idx, doc in enumerate(documents_to_fetch, 1):
            try:
                response = session.get(doc["download_url"], timeout=HTTP.timeout, allow_redirects=True)
                response.raise_for_status()
            except requests.RequestException as exc:
                errors.append(f"document {doc['download_url']}: {exc}")
                continue
            payload = response.content
            sha = _sha256_bytes(payload)
            content_type = response.headers.get("Content-Type", "")
            ext = _extension_for(content_type, response.url)
            local = content_dir / f"{sha}{ext}"
            if not local.exists():
                local.write_bytes(payload)
            doc.update({
                "download_url": _canonical_url(response.url),
                "http_status": response.status_code,
                "content_type": content_type,
                "byte_size": len(payload),
                "sha256": sha,
                "duplicate_content_group": sha,
                "local_path": str(local.relative_to(root)),
            })
            if idx % 100 == 0:
                logger.info("Fetched %s/%s FOMB documents", idx, len(documents_to_fetch))

    manifest_path = root / MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        for doc in documents:
            fh.write(json.dumps(doc, sort_keys=True, ensure_ascii=False) + "\n")

    _write_csv(root / DOCUMENTS_REL, documents, DOCUMENT_COLUMNS)
    review_by_id = {row["fomb_review_id"]: row for row in reviews}
    reviews = sorted(review_by_id.values(), key=lambda r: (r["completed_date"], r["government_entity_raw"], r["counterparty_raw"], r["fomb_review_id"]))
    _write_csv(root / CONTRACTS_REL, reviews, CONTRACT_COLUMNS)
    versions = _build_versions(documents)
    _write_csv(root / VERSIONS_REL, versions, VERSION_COLUMNS)
    crosswalk = _build_crosswalk(root, reviews)
    _write_csv(root / CROSSWALK_REL, crosswalk, CROSSWALK_COLUMNS)

    state_path = raw_root / "collection_state.json"
    state_path.write_text(json.dumps({"retrieved_at": retrieved_at, "collections": collection_state, "errors": errors}, indent=2, sort_keys=True), encoding="utf-8")
    session.close()
    return {
        "rows": len(documents),
        "documents": len(documents),
        "contract_reviews": len(reviews),
        "versions": len(versions),
        "crosswalks": len(crosswalk),
        "path": str(root / DOCUMENTS_REL),
        "errors": errors,
        "status": "OK" if not errors else "PARTIAL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--no-download-documents", action="store_true")
    parser.add_argument("--max-documents", type=int)
    args = parser.parse_args(argv)
    result = run(root=args.root, download_documents=not args.no_download_documents, max_documents=args.max_documents)
    print(json.dumps(result, indent=2, sort_keys=True))
    # A partial dynamic endpoint is retained as a successful materialization with
    # explicit errors; output validation still protects existing authoritative data.
    return 0 if result["documents"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
