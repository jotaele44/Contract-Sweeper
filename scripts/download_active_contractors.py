"""
Download PR active contractor registry from government supplier databases.

Source hierarchy (fetch-first / manual-fallback / graceful-empty):
  1. Manual files in data/raw/Active Contractor Listing/
  2. asg.pr.gov/suplidores       (ASG RUL/RUP registry, via
                                  scripts/scrape_asg_suppliers.py)
  3. consultacontratos.ocpr.gov.pr (OCPR contract registry)
  4. hacienda.pr.gov             (Hacienda supplier list)
  5. subastas.pr.gov             (RUS)

Tier 2 used to probe three invented JSON endpoints under asg.pr.gov, all of
which answer 404. ASG publishes a server-rendered HTML table instead, so that
tier now delegates to scrape_asg_suppliers, the registered producer for the
asg_suppliers source.

Output:
  data/staging/processed/pr_active_contractors.csv

Usage:
  python3 scripts/download_active_contractors.py
  python3 scripts/download_active_contractors.py --force
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from scripts.build_unified_master import _normalize_name
from scripts.config import PROJECT_ROOT, setup_logging

RAW_DIRS = [
    PROJECT_ROOT / "data" / "raw" / "Active Contractor Listing",
    PROJECT_ROOT / "data" / "raw" / "active_contractors",
    PROJECT_ROOT / "data" / "raw" / "Active Contractors",
]

CONTRACTOR_COLUMNS = [
    "entity_name",
    "entity_normalized",
    "registration_id",
    "registration_date",
    "expiry_date",
    "contractor_type",
    "naics_code",
    "municipality",
    "status",
    "source_file",
]

# JSON endpoints to probe. The three ASG entries that used to head this list
# (/api/suplidores, /suplidores/api/vendors and /suplidores/) were guesses and
# all three answer 404 — note that even the plain page 404s with the trailing
# slash; the working URL is https://asg.pr.gov/suplidores without one. ASG is now
# served by scrape_asg_suppliers against the real HTML table (tier 2 below), so
# it is deliberately absent here. The remaining entries are unverified guesses of
# the same kind, left in place only because nothing has replaced them yet.
ENDPOINTS = [
    "https://consultacontratos.ocpr.gov.pr/api/suplidores",
    "https://consultacontratos.ocpr.gov.pr/suplidores",
    "https://hacienda.pr.gov/api/suplidores",
    "https://hacienda.pr.gov/suplidores/",
    "https://subastas.pr.gov/api/vendors",
    "https://subastas.pr.gov/",
]

PAGE_SIZE = 500
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]
REQUEST_SLEEP = 1.0

# Header candidates per canonical column. The ASG entries here are the headings
# the live /suplidores table actually renders ("Nombre de la Compañía",
# "Licitador ID", "Estatus") — none of the previous candidates matched them, so
# even a successful fetch used to map every column to empty.
COL_MAP = {
    "entity_name": [
        "Nombre de la Compañía",
        "Nombre",
        "Company Name",
        "Vendor Name",
        "Suplidor",
        "entity_name",
        "name",
        "nombre",
    ],
    "registration_id": [
        "Licitador ID",
        "Registro",
        "Registration ID",
        "ID",
        "registration_id",
        "num_registro",
    ],
    "registration_date": ["Fecha de Registro", "Registration Date", "registration_date", "fecha"],
    "expiry_date": ["Fecha de Expiración", "Expiry Date", "expiry_date", "fecha_expiracion"],
    "contractor_type": ["Tipo", "Type", "Category", "contractor_type", "clase"],
    "naics_code": ["NAICS", "NAICS Code", "Código NAICS", "naics_code"],
    "municipality": ["Municipio", "Municipality", "City", "municipality"],
    "status": ["Estatus", "Estado", "Status", "Active", "status", "activo"],
}


def _session():
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; ContractSweeper/1.0; PR procurement research)",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "es-PR,es;q=0.9,en;q=0.8",
        }
    )
    return s


def _get(session, url, params, logger):
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, params=params, timeout=30)
            time.sleep(REQUEST_SLEEP)
            if resp.status_code == 429:
                time.sleep(30)
                continue
            return resp
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[attempt])
            else:
                logger.error(f"  Request failed: {exc}")
    return None


def _try_json_endpoint(session, url, logger):
    all_records = []
    page = 1
    while True:
        resp = _get(session, url, {"page": page, "per_page": PAGE_SIZE, "limit": PAGE_SIZE}, logger)
        if resp is None or resp.status_code >= 400:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        if isinstance(data, list):
            all_records.extend(data)
            if len(data) < PAGE_SIZE:
                break
            page += 1
        elif isinstance(data, dict):
            records = data.get(
                "data", data.get("results", data.get("vendors", data.get("suplidores", [])))
            )
            if isinstance(records, list):
                all_records.extend(records)
                if len(records) < PAGE_SIZE:
                    break
                page += 1
            else:
                break
        else:
            break
    return all_records


def _map_col(df_cols, candidates):
    cols_lower = {c.lower().strip(): c for c in df_cols}
    for cand in candidates:
        if cand in df_cols:
            return cand
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def _normalize_df(df, source_file):
    out = {}
    for out_col, candidates in COL_MAP.items():
        src = _map_col(df.columns.tolist(), candidates)
        out[out_col] = df[src].astype(str) if src else ""
    result = pd.DataFrame(out)
    result["entity_normalized"] = result["entity_name"].apply(_normalize_name)
    result["source_file"] = source_file
    for col in CONTRACTOR_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    return result[CONTRACTOR_COLUMNS]


def parse_records(df: "pd.DataFrame", source_file: str = "fixture") -> pd.DataFrame:
    """Map a raw contractor listing DataFrame to the canonical schema.
    Pure — no network or I/O. Live scrape still needs egress to PR government
    contractor APIs (asg.pr.gov, consultacontratos.ocpr.gov.pr) or a file
    dropped into data/raw/Active Contractor Listing/.
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame(columns=CONTRACTOR_COLUMNS)
    return _normalize_df(df, source_file)


def _try_asg_suppliers(logger):
    """Fetch the ASG RUL/RUP registry through its registered producer.

    Imported lazily because scrape_asg_suppliers imports CONTRACTOR_COLUMNS from
    this module — a module-level import either way would be circular. Any
    failure degrades to the next tier rather than aborting the run, matching how
    the JSON probes behave.
    """
    try:
        from scripts.scrape_asg_suppliers import (
            CONTRACTOR_COLUMNS as _cols,
            build_session,
            fetch_all_records,
        )
        from scripts.scrape_asg_suppliers import HTTP as _http
        from scripts.scrape_asg_suppliers import _normalize_row

        logger.info("  Trying: https://asg.pr.gov/suplidores (HTML registry)")
        session = build_session(_http.user_agent, _http.extra_headers)
        try:
            records, _ = fetch_all_records(session, logger)
        finally:
            session.close()

        if not records:
            return pd.DataFrame(columns=CONTRACTOR_COLUMNS)
        rows = [_normalize_row(r["summary"], r["detail"]) for r in records]
        # Drop scrape_asg_suppliers' extra geo_zip so this module keeps writing
        # exactly CONTRACTOR_COLUMNS.
        return pd.DataFrame(rows).reindex(columns=_cols)
    except Exception as exc:
        logger.warning(f"    ASG suplidores scrape failed: {exc}")
        return pd.DataFrame(columns=CONTRACTOR_COLUMNS)


def _try_manual_files(logger):
    all_dfs = []
    for raw_dir in RAW_DIRS:
        if not raw_dir.exists():
            continue
        for pattern in ("*.csv", "*.xlsx", "*.xls"):
            for f in raw_dir.glob(pattern):
                if f.name.startswith("."):
                    continue
                logger.info(f"  Reading manual file: {f.name}")
                try:
                    if f.suffix.lower() in (".xlsx", ".xls"):
                        df = pd.read_excel(f, dtype=str)
                    else:
                        df = pd.read_csv(f, dtype=str, low_memory=False)
                    if not df.empty:
                        mapped = _normalize_df(df, f.name)
                        all_dfs.append(mapped)
                        logger.info(f"    → {len(df):,} rows")
                except Exception as e:
                    logger.warning(f"    Failed: {e}")
    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return pd.DataFrame(columns=CONTRACTOR_COLUMNS)


def run(root=None, force=False):
    root = Path(root or PROJECT_ROOT)
    out_path = root / "data" / "staging" / "processed" / "pr_active_contractors.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logging("download_active_contractors")

    if out_path.exists() and not force:
        rows = sum(1 for _ in open(out_path)) - 1
        logger.info(f"  pr_active_contractors.csv exists ({rows:,} rows) — skipping.")
        return {"status": "CACHED", "rows": rows}

    # 1. Manual files
    df = _try_manual_files(logger)
    if not df.empty:
        df.to_csv(out_path, index=False, encoding="utf-8")
        logger.info(f"  Active contractors (manual): {len(df):,} rows")
        return {"status": "OK", "rows": len(df)}

    # 2. ASG RUL/RUP registry, the one tier that is known to work.
    df = _try_asg_suppliers(logger)
    if not df.empty:
        df.to_csv(out_path, index=False, encoding="utf-8")
        logger.info(f"  Active contractors (ASG suplidores): {len(df):,} rows")
        return {"status": "OK", "rows": len(df)}

    # 3. Other JSON endpoints
    session = _session()
    for url in ENDPOINTS:
        logger.info(f"  Trying: {url}")
        records = _try_json_endpoint(session, url, logger)
        if records:
            logger.info(f"  Found {len(records):,} records at {url}")
            df = _normalize_df(pd.DataFrame(records), "api")
            df.to_csv(out_path, index=False, encoding="utf-8")
            return {"status": "OK", "rows": len(df)}

    # 4. Graceful empty
    logger.warning(
        "  No active contractor data found. Manual instructions:\n"
        "  Visit: https://asg.pr.gov/suplidores or https://consultacontratos.ocpr.gov.pr\n"
        "  Download the supplier registry and place in data/raw/Active Contractor Listing/"
    )
    pd.DataFrame(columns=CONTRACTOR_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
    return {"status": "EMPTY", "rows": 0}


def main():
    parser = argparse.ArgumentParser(description="Download PR active contractor registry")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(f"\nActive contractors: {result['rows']:,} records ({result['status']})")
    return 0 if result["status"] in ("OK", "CACHED") else 1


if __name__ == "__main__":
    sys.exit(main())
