#!/usr/bin/env python3
"""Build the canonical federal financial-program registry from SAM Assistance Listings.

This is ontology-first and fail-closed. It does not infer Puerto Rico activity from
program eligibility. Until award-level evidence is supplied, every financial listing
is classified as ``requires_award_level_test``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

SOURCE_URL = (
    "https://s3.amazonaws.com/falextracts/Assistance%20Listings/datagov/"
    "AssistanceListings_DataGov_PUBLIC_CURRENT.csv"
)
FINANCIAL_TOKENS = (
    "GRANT",
    "COOPERATIVE AGREEMENT",
    "DIRECT PAYMENT",
    "LOAN",
    "INSURANCE",
    "FINANCIAL ASSISTANCE",
    "SALE, EXCHANGE, OR DONATION",
)
PR_NEXUS_STATES = {
    "confirmed_pr_activity",
    "pr_eligible_no_activity_recovered",
    "not_pr_applicable",
    "historical",
    "unresolved",
    "requires_award_level_test",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire(path: Path, url: str = SOURCE_URL) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, path.open("wb") as output:  # noqa: S310 - fixed GSA/S3 URL
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def is_financial(types_of_assistance: str) -> bool:
    value = (types_of_assistance or "").upper()
    return any(token in value for token in FINANCIAL_TOKENS)


def load_overrides(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict] = {}
    for row in payload:
        program_number = str(row["program_number"]).strip()
        state = row["pr_nexus_state"]
        if state not in PR_NEXUS_STATES:
            raise ValueError(f"invalid PR nexus state for {program_number}: {state}")
        if state != "requires_award_level_test" and not row.get("evidence_ref"):
            raise ValueError(f"evidence_ref required to promote {program_number} to {state}")
        result[program_number] = row
    return result


def build(source: Path, output: Path, coverage: Path, overrides: dict[str, dict]) -> dict:
    source_hash = sha256_file(source)
    seen: set[str] = set()
    all_rows = 0
    financial_rows = 0
    excluded_nonfinancial = 0
    nexus_counts = {state: 0 for state in sorted(PR_NEXUS_STATES)}

    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="cp1252", newline="") as src, output.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        required = {
            "Program Title",
            "Program Number",
            "Federal Agency (030)",
            "Types of Assistance (060)",
            "Published Date",
            "URL",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"SAM extract missing required columns: {sorted(missing)}")

        for raw in reader:
            all_rows += 1
            program_number = raw["Program Number"].strip()
            if not program_number:
                raise ValueError(f"blank Program Number at source row {all_rows + 1}")
            if program_number in seen:
                raise ValueError(f"duplicate Program Number: {program_number}")
            seen.add(program_number)

            assistance_type = raw["Types of Assistance (060)"].strip()
            if not is_financial(assistance_type):
                excluded_nonfinancial += 1
                continue

            financial_rows += 1
            override = overrides.get(program_number, {})
            nexus_state = override.get("pr_nexus_state", "requires_award_level_test")
            nexus_counts[nexus_state] += 1
            record = {
                "schema_version": "federal_financial_program_registry_v1",
                "program_number": program_number,
                "program_title": raw["Program Title"].strip(),
                "federal_agency": raw["Federal Agency (030)"].strip(),
                "types_of_assistance": assistance_type,
                "published_date": raw["Published Date"].strip() or None,
                "source_url": raw["URL"].strip() or None,
                "source_extract_sha256": source_hash,
                "pr_nexus_state": nexus_state,
                "pr_nexus_evidence_ref": override.get("evidence_ref"),
            }
            dst.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "schema_version": "federal_financial_program_coverage_v1",
        "source_url": SOURCE_URL,
        "source_sha256": source_hash,
        "assistance_listing_rows": all_rows,
        "unique_program_numbers": len(seen),
        "financial_program_rows": financial_rows,
        "nonfinancial_assistance_rows": excluded_nonfinancial,
        "pr_nexus_state_counts": nexus_counts,
        "pr_nexus_classified_rows": sum(nexus_counts.values()),
        "pr_nexus_classification_pct": (
            100.0 if financial_rows == 0 else round(100.0 * sum(nexus_counts.values()) / financial_rows, 8)
        ),
        "global_fain_backfill_allowed": False,
    }
    if summary["pr_nexus_classified_rows"] != financial_rows:
        raise RuntimeError("PR nexus classification denominator mismatch")
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/raw/sam/AssistanceListings_DataGov_PUBLIC_CURRENT.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/federal_financial_program_registry.jsonl"))
    parser.add_argument("--coverage", type=Path, default=Path("data/exports/federal_financial_program_coverage.json"))
    parser.add_argument("--pr-nexus-overrides", type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()

    if args.download:
        acquire(args.source)
    if not args.source.exists():
        parser.error(f"source does not exist: {args.source}; pass --download to acquire the current SAM extract")

    summary = build(args.source, args.output, args.coverage, load_overrides(args.pr_nexus_overrides))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
