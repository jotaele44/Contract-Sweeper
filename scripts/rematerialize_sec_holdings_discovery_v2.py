#!/usr/bin/env python3
"""Re-materialize legacy PR SEC holdings discovery without identifier conflation.

The legacy output mixed EFTS `file_num` values into a column named `filer_cik`.
This migration never mutates that raw file. It preserves the raw string, types
recognized 13F file numbers separately, and marks the entire legacy corpus as
municipal/debt discovery rather than corporate equity ownership.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from scripts.config import PROJECT_ROOT

_CIK = re.compile(r"^\d{1,10}$")
_FILE13F = re.compile(r"028-\d{3,}$")


def _clean_container(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text.strip("'\"").strip()


def classify_identifier(raw: str) -> tuple[str, str, str]:
    value = _clean_container(raw)
    if not value:
        return "", "", "NULL"
    if _CIK.fullmatch(value):
        return value.zfill(10), "", "CIK"
    if _FILE13F.fullmatch(value):
        return "", value, "FORM13F_FILE_NUMBER"
    return "", "", "UNRESOLVED_IDENTIFIER_FAMILY"


def run(*, root: Path, input_path: Path | None = None) -> dict[str, object]:
    source = input_path or root / "data" / "staging" / "processed" / "pr_sec_holdings.csv"
    target = root / "data" / "staging" / "processed" / "pr_sec_holdings_discovery_v2.csv"
    if not source.is_file():
        raise FileNotFoundError(source)

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "filer_cik" not in reader.fieldnames:
            raise ValueError("legacy holdings source missing filer_cik")
        rows = list(reader)
        input_fields = list(reader.fieldnames)

    output: list[dict[str, str]] = []
    states: dict[str, int] = {}
    for row in rows:
        raw = str(row.get("filer_cik") or "")
        cik, file_number, state = classify_identifier(raw)
        states[state] = states.get(state, 0) + 1
        migrated = dict(row)
        migrated["filer_cik_raw"] = raw
        migrated["filer_cik"] = cik
        migrated["form13f_file_number"] = file_number
        migrated["identifier_family_state"] = state
        migrated["scope_class"] = "PUERTO_RICO_MUNICIPAL_DEBT_DISCOVERY"
        migrated["corporate_equity_ownership_eligible"] = "false"
        migrated["canonicality"] = "NONCANONICAL_DISCOVERY"
        output.append(migrated)

    if len(output) != len(rows):
        raise AssertionError("row conservation failed")
    fields = input_fields + [
        "filer_cik_raw",
        "form13f_file_number",
        "identifier_family_state",
        "scope_class",
        "corporate_equity_ownership_eligible",
        "canonicality",
    ]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(output)

    return {
        "input_path": str(source),
        "output_path": str(target),
        "input_rows": len(rows),
        "output_rows": len(output),
        "row_conservation": True,
        "identifier_states": states,
        "corporate_equity_rows_promoted": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    result = run(root=args.root, input_path=args.input)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
