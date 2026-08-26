#!/usr/bin/env python3
"""Materialize and certify the bounded BPOP SEC 13F eight-quarter corpus.

The certifier fails closed. It requires the exact eight frozen SEC archives,
unique exact-date shares-outstanding denominators for every required BPOP
period, zero unresolved restatement targets, row conservation, stable issuer
CUSIP bindings, and at least one OFG/EVTC regression observation. It does not
claim Morningstar metric equivalence and never aggregates options into shares
held.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from moneysweep.capital_control import apply_supersession, ingest
from moneysweep.capital_control.models import HoldingObservation, InvestorIdentity
from moneysweep.capital_control.sec13f import (
    Sec13FBulkAdapter,
    Sec13FError,
    adjudicate_sec13f_restatements,
)
from scripts.config import PROJECT_ROOT


def _load_registry(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("golden-case registry must be an object")
    return data


def _bindings(data: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    by_cusip: dict[str, str] = {}
    by_ticker: dict[str, dict[str, str]] = {}
    for raw in data.get("issuer_bindings", []):
        if not isinstance(raw, dict):
            continue
        item = {str(k): str(v) for k, v in raw.items() if v is not None}
        ticker = item["ticker"].upper()
        cusip = item["cusip"].upper()
        issuer_id = item["issuer_id"]
        if ticker in by_ticker or cusip in by_cusip:
            raise ValueError("duplicate golden issuer ticker/CUSIP")
        by_ticker[ticker] = item
        by_cusip[cusip] = issuer_id
    if set(by_ticker) != {"BPOP", "OFG", "EVTC"}:
        raise ValueError("golden issuer denominator must be exactly BPOP/OFG/EVTC")
    return by_cusip, by_ticker


def _read_denominators(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "as_of_date", "shares_outstanding", "concept", "accession_number"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"denominator file missing fields {sorted(required - set(reader.fieldnames or []))}")
        return list(reader)


def _select_bpop_denominators(
    rows: list[dict[str, str]], required_periods: tuple[date, ...]
) -> tuple[dict[date, float], list[dict[str, object]]]:
    selected: dict[date, float] = {}
    ledger: list[dict[str, object]] = []
    for period in required_periods:
        candidates = [
            row for row in rows
            if row.get("ticker", "").upper() == "BPOP"
            and row.get("as_of_date") == period.isoformat()
            and row.get("shares_outstanding", "").strip()
        ]
        values: set[float] = set()
        for row in candidates:
            try:
                values.add(float(row["shares_outstanding"]))
            except ValueError as exc:
                raise ValueError(f"invalid BPOP denominator at {period}: {row['shares_outstanding']!r}") from exc
        state = "PASS" if len(values) == 1 else "UNRESOLVED"
        value = next(iter(values)) if len(values) == 1 else None
        if value is not None and value <= 0:
            state = "UNRESOLVED"
            value = None
        if value is not None:
            selected[period] = value
        ledger.append(
            {
                "as_of_date": period.isoformat(),
                "candidate_count": len(candidates),
                "distinct_values": sorted(values),
                "selected_value": value,
                "state": state,
                "candidate_accessions": sorted({row.get("accession_number", "") for row in candidates}),
                "candidate_concepts": sorted({row.get("concept", "") for row in candidates}),
            }
        )
    return selected, ledger


def _flatten(
    row: HoldingObservation, *, active: bool, denominator: float | None
) -> dict[str, object]:
    payload = asdict(row)
    extra = dict(payload.pop("extra") or {})
    put_call = str(extra.get("put_call") or "").strip().upper()
    eligible = row.shares is not None and not put_call
    percent = row.shares / denominator * 100.0 if eligible and denominator else None
    payload.update(extra)
    payload["security_cusip"] = str(row.security_id or "").removeprefix("CUSIP:")
    payload["is_active"] = active
    payload["issuer_share_denominator"] = denominator
    payload["percent_issuer_shares_computed"] = percent
    payload["issuer_percent_eligibility"] = (
        "ELIGIBLE_COMMON_SHARE_POSITION"
        if eligible
        else "EXCLUDED_OPTION_OR_NONSHARE_POSITION"
    )
    payload["provider_percent_total_assets"] = None
    payload["provider_equivalence_state"] = "OPEN"
    return payload


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return 0
    fields: list[str] = []
    seen: set[str] = set()
    for row in materialized:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def run(*, root: Path) -> dict[str, object]:
    registry_path = root / "registries" / "capital_control_golden_cases.json"
    data = _load_registry(registry_path)
    issuer_bindings, by_ticker = _bindings(data)
    required_periods = tuple(date.fromisoformat(value) for value in data["bpop_required_periods"])
    required_archives = tuple(str(value) for value in data["bpop_required_archives"])
    if len(required_periods) != 8 or len(required_archives) != 8:
        raise ValueError("BPOP certification denominator must contain exactly eight periods/archives")

    archive_dir = root / "data" / "staging" / "raw" / "sec13f_bulk" / "bpop_8q_v1"
    archive_paths = tuple(archive_dir / name for name in required_archives)
    missing_files = [path.name for path in archive_paths if not path.is_file()]
    if missing_files:
        raise FileNotFoundError(f"missing frozen SEC archives: {missing_files}")

    denominator_rows = _read_denominators(
        root / "data" / "staging" / "processed" / "pr_sec_share_denominators_v2.csv"
    )
    denominators, denominator_ledger = _select_bpop_denominators(denominator_rows, required_periods)

    observations: list[HoldingObservation] = []
    investors: dict[str, InvestorIdentity] = {}
    archive_audits: list[dict[str, object]] = []
    target_cusips = tuple(sorted(issuer_bindings))
    for archive in archive_paths:
        adapter = Sec13FBulkAdapter(
            archive,
            target_cusips=target_cusips,
            issuer_bindings=issuer_bindings,
        )
        result = ingest(adapter)
        observations.extend(result.observations)
        for investor in adapter.iter_investors():
            incumbent = investors.get(investor.investor_id)
            if incumbent is not None and incumbent.raw_name != investor.raw_name:
                raise ValueError(f"holder CIK name contradiction across archives: {investor.investor_id}")
            investors[investor.investor_id] = investor
        audit = adapter.audit()
        archive_audits.append(
            {
                "archive": archive.name,
                "sha256": audit.raw_bytes_sha256,
                "byte_size": audit.raw_bytes_size,
                "schema_fingerprint": audit.schema_fingerprint,
                "source_row_counts": dict(audit.source_row_counts),
                "retained_target_rows": audit.retained_rows,
                "member_digests": [asdict(item) for item in audit.member_digests],
            }
        )

    source_count = len(observations)
    if len({row.observation_id for row in observations}) != source_count:
        raise ValueError("duplicate observation_id across archives")
    source_keys = [(row.source_id, row.source_record_id) for row in observations]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("duplicate source record across archives")

    adjudicated = adjudicate_sec13f_restatements(observations)
    if len(adjudicated.observations) != source_count:
        raise AssertionError("restatement adjudication violated row conservation")
    supersession = apply_supersession(adjudicated.observations)
    superseded = {row.observation_id: row for row in supersession.superseded}
    active_ids = {row.observation_id for row in supersession.active}
    preserved = tuple(superseded.get(row.observation_id, row) for row in adjudicated.observations)
    if len(preserved) != source_count:
        raise AssertionError("supersession violated row conservation")

    bpop_cusip = by_ticker["BPOP"]["cusip"].upper()
    bpop_rows = [row for row in preserved if row.security_id == f"CUSIP:{bpop_cusip}"]
    observed_periods = {row.as_of_date for row in bpop_rows}
    regression_counts = {
        ticker: sum(row.security_id == f"CUSIP:{item['cusip'].upper()}" for row in preserved)
        for ticker, item in by_ticker.items()
    }

    output_dir = root / "data" / "staging" / "processed" / "capital_control"
    manifest_dir = root / "data" / "manifests" / "capital_control"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    materialized_rows = [
        _flatten(
            row,
            active=row.observation_id in active_ids,
            denominator=denominators.get(row.as_of_date) if row.security_id == f"CUSIP:{bpop_cusip}" else None,
        )
        for row in preserved
    ]
    materialized_count = _write_csv(output_dir / "sec13f_pr_golden_holdings.csv", materialized_rows)
    _write_csv(output_dir / "sec13f_pr_golden_investors.csv", [asdict(v) for v in investors.values()])

    bpop_eligible = [
        row for row in materialized_rows
        if row.get("security_cusip") == bpop_cusip
        and row.get("issuer_percent_eligibility") == "ELIGIBLE_COMMON_SHARE_POSITION"
    ]
    gates = {
        "exact_archive_count_8": len(archive_audits) == 8,
        "archive_names_exact": tuple(item["archive"] for item in archive_audits) == required_archives,
        "all_archive_hashes_present": all(len(str(item["sha256"])) == 64 for item in archive_audits),
        "row_conservation": source_count == materialized_count == len(preserved),
        "source_record_unique": len(source_keys) == len(set(source_keys)),
        "restatement_residue_zero": len(adjudicated.issues) == 0,
        "bpop_all_eight_periods_present": observed_periods == set(required_periods),
        "bpop_exact_denominator_each_period": set(denominators) == set(required_periods),
        "bpop_eligible_rows_have_percent": all(row.get("percent_issuer_shares_computed") is not None for row in bpop_eligible),
        "bpop_rows_present": len(bpop_rows) > 0,
        "ofg_regression_rows_present": regression_counts["OFG"] > 0,
        "evtc_regression_rows_present": regression_counts["EVTC"] > 0,
        "issuer_bindings_pass": all(row.identity_status == "PASS" for row in preserved),
        "holder_ids_are_stable_cik_ids": all(row.holder_id.startswith("INV_CIK_") for row in preserved),
        "supersession_arithmetic": len(active_ids) + len(superseded) == len(preserved),
        "provider_equivalence_not_promoted": all(row.get("provider_equivalence_state") == "OPEN" for row in materialized_rows),
    }
    state = "PASS" if all(gates.values()) else "OPEN"
    certification = {
        "certification_id": "BPOP_SEC13F_8Q_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "SEC Form 13F BPOP ownership observations 2024Q2-2026Q1 plus OFG/EVTC parser regressions",
        "state": state,
        "bounded_claim_only": True,
        "source_observation_count": source_count,
        "active_observation_count": len(active_ids),
        "superseded_observation_count": len(superseded),
        "bpop_observation_count": len(bpop_rows),
        "bpop_eligible_common_share_rows": len(bpop_eligible),
        "regression_counts": regression_counts,
        "observed_bpop_periods": sorted(value.isoformat() for value in observed_periods),
        "denominator_ledger": denominator_ledger,
        "restatement_issues": [asdict(issue) for issue in adjudicated.issues],
        "archive_audits": archive_audits,
        "gates": gates,
        "morningstar_percent_total_assets_equivalence": "OPEN",
        "deep_dive_promotion": "BLOCKED" if state != "PASS" else "ELIGIBLE_FOR_SEPARATE_PROMOTION_VECTOR",
    }
    (manifest_dir / "bpop_sec13f_8q_certification.json").write_text(
        json.dumps(certification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return certification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        result = run(root=args.root)
    except (OSError, ValueError, Sec13FError) as exc:
        print(f"BPOP SEC13F certification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
