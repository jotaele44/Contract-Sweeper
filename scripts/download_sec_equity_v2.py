#!/usr/bin/env python3
"""Re-materialize benchmark SEC issuer/financial data with stable-ID gates.

This producer is intentionally bounded to BPOP/OFG/EVTC until the benchmark
regressions pass. It never repairs identity by name similarity and never emits
synthetic financial fallback rows. Raw SEC JSON bytes are frozen and reused
unless --refresh is explicitly supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.sec_equity_identity import (
    SecIdentityError,
    SecIssuerBinding,
    require_binding,
    require_submission_identity,
)
from scripts.config import PROJECT_ROOT

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
USER_AGENT = "MoneySweep research@pr-pipeline.org"
BENCHMARKS = {
    "BPOP": "0000763901",
    "OFG": "0001030469",
    "EVTC": "0001559865",
}
FINANCIAL_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_revenues": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "r_and_d_expense": ("ResearchAndDevelopmentExpense",),
}
SHARE_CONCEPTS = (
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: invalid UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}: expected JSON object")
    return value


def _fetch_frozen(
    session: requests.Session,
    *,
    url: str,
    path: Path,
    refresh: bool,
) -> tuple[Mapping[str, Any], dict[str, object]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        payload = path.read_bytes()
        origin = "REUSED_FROZEN"
    else:
        response = session.get(url, timeout=60)
        response.raise_for_status()
        payload = response.content
        _load_json_bytes(payload, label=url)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(payload)
        temporary.replace(path)
        origin = "DOWNLOADED"
        time.sleep(0.12)
    return _load_json_bytes(payload, label=str(path)), {
        "path": str(path),
        "source_url": url,
        "byte_size": len(payload),
        "sha256": _sha256(payload),
        "origin": origin,
    }


def _annual_series(facts: Mapping[str, Any], concepts: Iterable[str]) -> dict[int, float]:
    taxonomy = facts.get("facts", {}).get("us-gaap", {})
    if not isinstance(taxonomy, Mapping):
        return {}
    for concept in concepts:
        node = taxonomy.get(concept)
        if not isinstance(node, Mapping):
            continue
        units = node.get("units", {})
        if not isinstance(units, Mapping):
            continue
        entries = units.get("USD", [])
        if not isinstance(entries, list):
            continue
        selected: dict[int, Mapping[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("form") not in {"10-K", "10-K405", "10-KSB"}:
                continue
            if entry.get("fp") != "FY" or entry.get("val") is None or not entry.get("end"):
                continue
            year = int(str(entry["end"])[:4])
            incumbent = selected.get(year)
            if incumbent is None or str(entry.get("filed", "")) > str(incumbent.get("filed", "")):
                selected[year] = entry
        if selected:
            return {year: float(entry["val"]) for year, entry in sorted(selected.items())}
    return {}


def _financial_rows(
    binding: SecIssuerBinding, name: str, facts: Mapping[str, Any]
) -> list[dict[str, object]]:
    years: dict[int, dict[str, object]] = {}
    for field, concepts in FINANCIAL_CONCEPTS.items():
        for year, value in _annual_series(facts, concepts).items():
            years.setdefault(year, {})[field] = value
    rows: list[dict[str, object]] = []
    for year, values in sorted(years.items()):
        if year < 2014:
            continue
        row: dict[str, object] = {
            "cik": binding.cik,
            "ticker": binding.ticker,
            "name": name,
            "fiscal_year": year,
            "identity_status": "PASS",
            "identity_basis": "SEC_COMPANY_TICKERS_CIK",
        }
        row.update(values)
        rows.append(row)
    return rows


def _share_denominators(
    binding: SecIssuerBinding, facts: Mapping[str, Any]
) -> list[dict[str, object]]:
    fact_root = facts.get("facts", {})
    if not isinstance(fact_root, Mapping):
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for taxonomy_name, concept in SHARE_CONCEPTS:
        taxonomy = fact_root.get(taxonomy_name, {})
        if not isinstance(taxonomy, Mapping):
            continue
        node = taxonomy.get(concept)
        if not isinstance(node, Mapping):
            continue
        units = node.get("units", {})
        if not isinstance(units, Mapping):
            continue
        entries = units.get("shares", [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("val") is None or not entry.get("end"):
                continue
            if entry.get("form") not in {"10-K", "10-Q", "10-K405", "10-KSB"}:
                continue
            key = (
                taxonomy_name,
                concept,
                entry.get("end"),
                entry.get("filed"),
                entry.get("form"),
                entry.get("accn"),
                entry.get("val"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "cik": binding.cik,
                    "ticker": binding.ticker,
                    "concept_taxonomy": taxonomy_name,
                    "concept": concept,
                    "as_of_date": entry.get("end"),
                    "filed_date": entry.get("filed"),
                    "form": entry.get("form"),
                    "fiscal_year": entry.get("fy"),
                    "fiscal_period": entry.get("fp"),
                    "frame": entry.get("frame"),
                    "accession_number": entry.get("accn"),
                    "shares_outstanding": entry.get("val"),
                    "unit": "shares",
                    "identity_status": "PASS",
                    "denominator_state": "CANDIDATE_EXACT_DATE",
                }
            )
    return sorted(
        rows, key=lambda row: (str(row["ticker"]), str(row["as_of_date"]), str(row["filed_date"]))
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def run(*, root: Path, tickers: tuple[str, ...], refresh: bool = False) -> dict[str, object]:
    wanted = tuple(dict.fromkeys(value.strip().upper() for value in tickers))
    unknown = sorted(set(wanted) - set(BENCHMARKS))
    if unknown:
        raise ValueError(f"uncertified benchmark ticker(s): {unknown}")
    raw_dir = root / "data" / "staging" / "raw" / "sec_equity_v2"
    out_dir = root / "data" / "staging" / "processed"
    manifest_dir = root / "data" / "manifests" / "sec_equity_v2"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    raw_manifest: list[dict[str, object]] = []
    ticker_payload, meta = _fetch_frozen(
        session,
        url=TICKER_URL,
        path=raw_dir / "company_tickers.json",
        refresh=refresh,
    )
    raw_manifest.append(meta)

    company_rows: list[dict[str, object]] = []
    financial_rows: list[dict[str, object]] = []
    denominator_rows: list[dict[str, object]] = []
    try:
        for ticker in wanted:
            binding = require_binding(
                ticker_payload, ticker=ticker, expected_cik=BENCHMARKS[ticker]
            )
            submission, sub_meta = _fetch_frozen(
                session,
                url=SUBMISSIONS_URL.format(cik=binding.cik),
                path=raw_dir / ticker / "submissions.json",
                refresh=refresh,
            )
            raw_manifest.append(sub_meta)
            require_submission_identity(submission, binding=binding)
            facts, facts_meta = _fetch_frozen(
                session,
                url=FACTS_URL.format(cik=binding.cik),
                path=raw_dir / ticker / "companyfacts.json",
                refresh=refresh,
            )
            raw_manifest.append(facts_meta)
            name = str(submission.get("name") or binding.title_raw)
            company_rows.append(
                {
                    "cik": binding.cik,
                    "ticker": binding.ticker,
                    "name": name,
                    "name_raw_ticker_map": binding.title_raw,
                    "state_of_inc": submission.get("stateOfIncorporation", ""),
                    "sic": submission.get("sic", ""),
                    "sic_description": submission.get("sicDescription", ""),
                    "fiscal_year_end": submission.get("fiscalYearEnd", ""),
                    "identity_status": "PASS",
                    "identity_basis": "SEC_COMPANY_TICKERS_CIK+SUBMISSIONS_CIK",
                }
            )
            financial_rows.extend(_financial_rows(binding, name, facts))
            denominator_rows.extend(_share_denominators(binding, facts))
    finally:
        session.close()

    if len(company_rows) != len(wanted):
        raise AssertionError("benchmark company row conservation failed")
    if len({row["cik"] for row in company_rows}) != len(company_rows):
        raise ValueError("benchmark CIK collision")

    _write_csv(out_dir / "pr_sec_companies_v2.csv", company_rows)
    _write_csv(out_dir / "pr_sec_financials_v2.csv", financial_rows)
    _write_csv(out_dir / "pr_sec_share_denominators_v2.csv", denominator_rows)
    receipt = {
        "receipt_version": "sec_equity_identity_v2",
        "scope": list(wanted),
        "company_rows": len(company_rows),
        "financial_rows": len(financial_rows),
        "share_denominator_rows": len(denominator_rows),
        "synthetic_fallback_rows": 0,
        "identity_state": "PASS",
        "denominator_certification": "PROVISIONAL_UNTIL_TEMPORAL_ADJUDICATION",
        "raw_manifest": raw_manifest,
    }
    (manifest_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--ticker", action="append", choices=sorted(BENCHMARKS))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    tickers = tuple(args.ticker or ("BPOP", "OFG", "EVTC"))
    try:
        result = run(root=args.root, tickers=tickers, refresh=args.refresh)
    except (OSError, requests.RequestException, SecIdentityError, ValueError) as exc:
        print(f"SEC equity v2 failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
