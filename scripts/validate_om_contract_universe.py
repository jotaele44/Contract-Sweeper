#!/usr/bin/env python3
"""Fail-closed validator for the Puerto Rico O&M contract universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/om_contract_universe"
REQUIRED_FILES = [
    "source_materialization.csv",
    "om_contract_universe.csv",
    "coverage_by_agency.csv",
    "coverage_by_municipality.csv",
    "coverage_by_fiscal_year.csv",
    "coverage_by_category.csv",
    "coverage_by_contractor.csv",
    "coverage_by_source.csv",
    "unresolved_gap_ledger.csv",
    "summary.json",
]


def validate(report_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (report_dir / name).exists():
            errors.append(f"missing required artifact: {name}")
    if errors:
        return False, errors

    summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "NON_PRODUCTION_DIAGNOSTIC":
        errors.append("summary status must remain NON_PRODUCTION_DIAGNOSTIC until certified")
    if summary.get("complete_claim_allowed") is not False:
        errors.append("complete_claim_allowed must be false before certification")

    gaps = pd.read_csv(report_dir / "unresolved_gap_ledger.csv", dtype=str, keep_default_na=False)
    if not {"blocker_id", "severity", "detail"}.issubset(gaps.columns):
        errors.append("gap ledger schema is invalid")
    required_blockers = {
        "MUNICIPALITY_78_ACCOUNTING",
        "PUBLIC_CORPORATION_ACCOUNTING",
        "OCPR_FULL_MATERIALIZATION",
    }
    present = set(gaps.get("blocker_id", []))
    missing = sorted(required_blockers - present)
    if missing:
        errors.append("required blockers missing: " + ", ".join(missing))

    status = pd.read_csv(
        report_dir / "source_materialization.csv", dtype=str, keep_default_na=False
    )
    required_sources = {
        "ocpr_contracts",
        "asg_emergency_purchases",
        "compras_pr",
        "cor3",
        "usaspending_prime",
        "usaspending_subawards",
        "prasa",
        "prepa_luma_genera",
        "dtop_road_contracts",
        "transit_contracts",
        "ports_airports_contracts",
        "p3_authority",
    }
    missing_sources = sorted(required_sources - set(status.get("source_id", [])))
    if missing_sources:
        errors.append("source inventory missing: " + ", ".join(missing_sources))

    receipt_path = (
        report_dir.parents[1] / "data/staging/checkpoints/ocpr_contracts/completion_receipt.json"
    )
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("status") != "COMPLETE":
            errors.append("OCPR completion receipt exists but is not COMPLETE")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    ok, errors = validate(args.report_dir.resolve())
    result = {
        "validator": "om_contract_universe_v1",
        "structural_validation": "PASS" if ok else "FAIL",
        "certification": "BLOCKED",
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
