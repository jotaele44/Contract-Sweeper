"""
Extract Puerto Rico P3 concession contracts from the ACT/ACUDEN transition report.

The transition report ``Contratos Vigentes ACT.pdf`` and its ACUDEN companion were
already re-extracted into a committed workbook
(``data/raw/act_transition/reextraction_2026-07/contratos_vigentes_complete_extraction.xlsx``,
1,803 rows across ACT_2020 and ACUDEN_2024). Nothing read it for concession
content, so the P3 rows inside it — including the Metropistas toll-road agreements
— never reached any canonical table.

This parser pulls out only the rows whose contractor is a **known P3
concessionaire**. Selection is by controlled name list rather than keyword search
on purpose: a regex over the whole row matches "Generación Futura Inc" on
"genera" and pulls in unrelated construction firms, and a false positive here
would assert that an ordinary road-repair contract is a public-private
partnership.

Input:  data/raw/act_transition/reextraction_2026-07/contratos_vigentes_complete_extraction.xlsx
Output: data/staging/processed/pr_ppp_concession_contracts.csv
        reports/act_transition_ppp_extract.json

Usage:
  python3 scripts/parse_act_transition_ppp.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from scripts._contract_dropzone import CONTRACT_COLUMNS, _normalize_name
from scripts.config import PROJECT_ROOT, setup_logging

SOURCE_XLSX = (
    "data/raw/act_transition/reextraction_2026-07/"
    "contratos_vigentes_complete_extraction.xlsx"
)
SHEET = "Combined_Canonical"
OUT = "data/staging/processed/pr_ppp_concession_contracts.csv"
REPORT_OUT = "reports/act_transition_ppp_extract.json"

# Known Puerto Rico P3 concessionaires, keyed by the normalized contractor name
# as it appears in the transition report, mapped to the concession they hold.
# ``project_hint`` is the concession label, not a canonical project_id — this is a
# staging surface and the resolution to a canonical project happens downstream.
CONCESSIONAIRES: dict[str, dict[str, str]] = {
    "AUTOPISTAS METROPOLITANAS DE PUERTO RICO": {
        "concessionaire": "Autopistas Metropolitanas de Puerto Rico",
        "project_hint": "PR-22 and PR-5 toll road concession",
        "spatial_extent": "corridor",
    },
    "AUTOPISTAS DE PUERTO RICO Y COMPAÑIA": {
        "concessionaire": "Autopistas de Puerto Rico y Compañía",
        "project_hint": "Teodoro Moscoso Bridge toll concession",
        "spatial_extent": "site",
    },
    "AEROSTAR AIRPORT HOLDINGS": {
        "concessionaire": "Aerostar Airport Holdings",
        "project_hint": "Luis Muñoz Marín Airport concession",
        "spatial_extent": "site",
    },
    "LUMA ENERGY": {
        "concessionaire": "LUMA Energy",
        "project_hint": "PREPA transmission and distribution operation",
        "spatial_extent": "islandwide",
    },
    "GENERA PR": {
        "concessionaire": "Genera PR",
        "project_hint": "PREPA generation operation",
        "spatial_extent": "islandwide",
    },
    "VEOLIA WATER": {
        "concessionaire": "Veolia Water Puerto Rico",
        "project_hint": "PRASA operation and maintenance agreement",
        "spatial_extent": "islandwide",
    },
}

# Extra columns this surface carries beyond the shared contract schema.
EXTRA_COLUMNS = ["concessionaire", "project_hint", "spatial_extent", "source_page"]
OUT_COLUMNS = CONTRACT_COLUMNS + EXTRA_COLUMNS


def _match_concessionaire(contractor: str) -> dict[str, str] | None:
    """Return the concession record for a contractor, or None.

    Matches on a normalized prefix so punctuation and suffix variants of the same
    firm collapse together ("AUTOPISTAS METROPOLITANAS DE PUERTO RICO, LLC" and
    "... LLC." are one concessionaire, not two).
    """
    norm = _normalize_name(contractor or "")
    for key, record in CONCESSIONAIRES.items():
        if norm.startswith(key) or key in norm:
            return record
    return None


def build_rows(root: Path | None = None) -> list[dict[str, Any]]:
    """Concession contract rows from the committed transition workbook."""
    root = Path(root or PROJECT_ROOT)
    path = root / SOURCE_XLSX
    if not path.exists():
        return []
    df = pd.read_excel(path, sheet_name=SHEET)
    rows: list[dict[str, Any]] = []
    for _, rec in df.iterrows():
        contractor = str(rec.get("contractor_name") or "").strip()
        match = _match_concessionaire(contractor)
        if not match:
            continue
        amount = rec.get("amount_numeric")
        rows.append(
            {
                "contract_id": str(rec.get("contract_number") or "").strip(),
                "vendor_name": contractor,
                "vendor_normalized": _normalize_name(contractor),
                "contract_type": str(rec.get("service_type") or "").strip(),
                # The report carries amendment rows at $0 that restate an earlier
                # award; they are kept rather than dropped so the amendment chain
                # stays visible, and they sum to nothing.
                "contract_value": "" if pd.isna(amount) else f"{float(amount):.2f}",
                "award_date": str(rec.get("award_date_raw") or "").strip(),
                "start_date": str(rec.get("start_date_raw") or "").strip(),
                "end_date": str(rec.get("end_date_raw") or "").strip(),
                "status": "active_at_transition",
                "description": str(rec.get("service_type") or "").strip(),
                "municipality": "",
                "agency": str(rec.get("agency_name") or "").strip(),
                "source_file": str(rec.get("source_pdf") or "").strip(),
                "concessionaire": match["concessionaire"],
                "project_hint": match["project_hint"],
                "spatial_extent": match["spatial_extent"],
                "source_page": str(rec.get("source_page") or "").strip(),
            }
        )
    rows.sort(key=lambda r: (r["vendor_normalized"], r["contract_id"]))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_concessionaire: dict[str, dict[str, Any]] = {}
    for r in rows:
        bucket = by_concessionaire.setdefault(
            r["concessionaire"],
            {"contracts": 0, "total_value": 0.0, "project_hint": r["project_hint"]},
        )
        bucket["contracts"] += 1
        if r["contract_value"]:
            bucket["total_value"] += float(r["contract_value"])
    return {
        "producer_script": "scripts/parse_act_transition_ppp.py",
        "source_inputs": [SOURCE_XLSX],
        "row_count": len(rows),
        "concessionaires": by_concessionaire,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _write(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract P3 concession contracts from the ACT/ACUDEN transition report."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="summarize without writing")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    logger = setup_logging("parse_act_transition_ppp")

    rows = build_rows(root)
    summary = summarize(rows)
    if not args.check:
        _write(rows, root / OUT)
        report_path = root / REPORT_OUT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        logger.info(f"  Written: {OUT} ({len(rows)} rows)")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
