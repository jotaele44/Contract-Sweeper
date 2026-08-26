#!/usr/bin/env python3
"""Build the MoneySweep SEC 13F capital/control materialization."""

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


def _load_golden_cases(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issuers = data.get("issuers")
    if not isinstance(issuers, list) or not issuers:
        raise ValueError("golden-case registry has no issuers")
    return data


def _issuer_bindings(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in data["issuers"]:
        if not isinstance(item, dict):
            continue
        cusip = str(item.get("cusip") or "").strip().upper()
        issuer_id = str(item.get("issuer_id") or "").strip()
        if not cusip or not issuer_id:
            raise ValueError("golden issuer binding missing CUSIP or issuer_id")
        if cusip in out and out[cusip] != issuer_id:
            raise ValueError(f"conflicting issuer binding for {cusip}")
        out[cusip] = issuer_id
    return out


def _bpop_contract(data: dict[str, Any]) -> tuple[str, tuple[date, ...], tuple[str, ...]]:
    bpop = next(
        item for item in data["issuers"]
        if isinstance(item, dict) and item.get("ticker") == "BPOP"
    )
    cusip = str(bpop["cusip"]).upper()
    periods = tuple(date.fromisoformat(str(value)) for value in bpop["required_periods"])
    archives = tuple(str(value) for value in data["bpop_eight_quarter_archive_basenames"])
    return cusip, periods, archives


def _flatten(row: HoldingObservation, *, active_ids: set[str]) -> dict[str, object]:
    payload = asdict(row)
    extra = dict(payload.pop("extra") or {})
    security_id = str(row.security_id or "")
    payload["security_cusip"] = security_id.removeprefix("CUSIP:") if security_id.startswith("CUSIP:") else ""
    payload["is_active"] = row.observation_id in active_ids
    for key, value in sorted(extra.items()):
        if key in payload:
            raise ValueError(f"extra field collides with canonical field: {key}")
        payload[key] = value
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
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime, Path)):
        return str(value) if isinstance(value, Path) else value.isoformat()
    raise TypeError(type(value).__name__)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _unique_source_records(rows: tuple[HoldingObservation, ...]) -> bool:
    keys = [(row.source_id, row.source_record_id) for row in rows]
    return len(keys) == len(set(keys))


def _certify(
    *,
    observations: tuple[HoldingObservation, ...],
    archive_names: tuple[str, ...],
    bpop_cusip: str,
    required_periods: tuple[date, ...],
    required_archives: tuple[str, ...],
    restatement_issue_count: int,
) -> dict[str, object]:
    bpop = tuple(row for row in observations if row.security_id == f"CUSIP:{bpop_cusip}")
    observed_periods = {row.as_of_date for row in bpop}
    missing_periods = sorted(set(required_periods) - observed_periods)
    archive_set = set(archive_names)
    missing_archives = sorted(set(required_archives) - archive_set)
    unexpected_archives = sorted(archive_set - set(required_archives))
    gates = {
        "required_archives_frozen": not missing_archives,
        "exact_required_archive_set": not missing_archives and not unexpected_archives,
        "bpop_eight_periods_present": not missing_periods and len(required_periods) == 8,
        "source_record_unique": _unique_source_records(observations),
        "bpop_issuer_identity_bound": all(row.identity_status == "PASS" for row in bpop),
        "required_security_nonnull": all(row.security_id for row in observations),
        "required_holder_nonnull": all(row.holder_id for row in observations),
        "temporal_order_valid": all(row.report_date >= row.as_of_date for row in observations),
        "restatement_residue_zero": restatement_issue_count == 0,
        "row_count_positive": len(observations) > 0,
    }
    return {
        "scope": "BPOP canonical SEC 13F eight-quarter corpus as of the supplied frozen archive set",
        "certification_state": "PASS" if all(gates.values()) else "OPEN",
        "bounded_claim_only": True,
        "bpop_cusip": bpop_cusip,
        "required_periods": [value.isoformat() for value in required_periods],
        "observed_periods": sorted(value.isoformat() for value in observed_periods),
        "missing_periods": [value.isoformat() for value in missing_periods],
        "required_archives": list(required_archives),
        "supplied_archives": list(archive_names),
        "missing_archives": missing_archives,
        "unexpected_archives": unexpected_archives,
        "total_observations": len(observations),
        "bpop_observations": len(bpop),
        "restatement_issue_count": restatement_issue_count,
        "gates": gates,
    }


def run(
    *,
    archives: tuple[Path, ...],
    golden_cases_path: Path,
    out_dir: Path,
    manifest_dir: Path,
) -> dict[str, object]:
    if not archives:
        raise ValueError("at least one frozen SEC 13F archive is required")
    data = _load_golden_cases(golden_cases_path)
    bindings = _issuer_bindings(data)
    target_cusips = tuple(sorted(bindings))
    bpop_cusip, required_periods, required_archives = _bpop_contract(data)
    archive_names = tuple(path.name for path in archives)
    if len(archive_names) != len(set(archive_names)):
        raise ValueError("duplicate archive basenames supplied")

    observations: list[HoldingObservation] = []
    investors: dict[str, InvestorIdentity] = {}
    manifests: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for archive in archives:
        adapter = Sec13FBulkAdapter(archive, target_cusips=target_cusips, issuer_bindings=bindings)
        result = ingest(adapter)
        observations.extend(result.observations)
        for investor in adapter.iter_investors():
            investors.setdefault(investor.investor_id, investor)
        manifests.append(asdict(result.manifest))
        audit = adapter.audit()
        audits.append(
            {
                "archive_path": audit.archive_path,
                "raw_bytes_size": audit.raw_bytes_size,
                "raw_bytes_sha256": audit.raw_bytes_sha256,
                "schema_fingerprint": audit.schema_fingerprint,
                "source_row_counts": dict(audit.source_row_counts),
                "retained_rows": audit.retained_rows,
                "target_cusips": list(audit.target_cusips),
                "member_digests": [asdict(item) for item in audit.member_digests],
            }
        )

    original_count = len(observations)
    if len({row.observation_id for row in observations}) != original_count:
        raise ValueError("duplicate observation_id across archive manifestations")
    if not _unique_source_records(tuple(observations)):
        raise ValueError("duplicate source record across archive manifestations")

    adjudicated = adjudicate_sec13f_restatements(observations)
    if len(adjudicated.observations) != original_count:
        raise AssertionError("restatement adjudication violated row conservation")
    supersession = apply_supersession(adjudicated.observations)
    superseded_by_id = {row.observation_id: row for row in supersession.superseded}
    preserved = tuple(superseded_by_id.get(row.observation_id, row) for row in adjudicated.observations)
    active_ids = {row.observation_id for row in supersession.active}
    if len(preserved) != original_count:
        raise AssertionError("supersession violated row conservation")

    holdings_path = out_dir / "sec13f_holdings.csv"
    investors_path = out_dir / "sec13f_investors.csv"
    holdings_count = _write_csv(holdings_path, (_flatten(row, active_ids=active_ids) for row in preserved))
    investor_count = _write_csv(
        investors_path,
        (asdict(item) for item in sorted(investors.values(), key=lambda item: item.investor_id)),
    )
    if holdings_count != original_count:
        raise AssertionError("materialized holdings count does not close")

    certification = _certify(
        observations=preserved,
        archive_names=archive_names,
        bpop_cusip=bpop_cusip,
        required_periods=required_periods,
        required_archives=required_archives,
        restatement_issue_count=len(adjudicated.issues),
    )
    receipt = {
        "receipt_version": "sec13f_capital_control_v0_2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": [str(path) for path in archives],
        "input_archive_count": len(archives),
        "target_cusips": list(target_cusips),
        "source_observation_count": original_count,
        "retained_observation_count": len(preserved),
        "active_observation_count": len(active_ids),
        "superseded_observation_count": len(superseded_by_id),
        "investor_count": investor_count,
        "arithmetic_closure": len(active_ids) + len(superseded_by_id) == len(preserved),
        "restatement_issues": [asdict(issue) for issue in adjudicated.issues],
        "outputs": {"holdings": str(holdings_path), "investors": str(investors_path)},
        "certification": certification,
    }
    _write_json(manifest_dir / "sec13f_source_manifests.json", manifests)
    _write_json(manifest_dir / "sec13f_archive_audits.json", audits)
    _write_json(manifest_dir / "sec13f_build_receipt.json", receipt)
    _write_json(manifest_dir / "sec13f_bpop_certification.json", certification)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="append", type=Path, required=True)
    parser.add_argument("--golden-cases", type=Path, default=Path("registries/capital_control_golden_cases.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/staging/processed/capital_control"))
    parser.add_argument("--manifest-dir", type=Path, default=Path("data/manifests/capital_control"))
    args = parser.parse_args(argv)
    try:
        receipt = run(
            archives=tuple(args.archive),
            golden_cases_path=args.golden_cases,
            out_dir=args.out_dir,
            manifest_dir=args.manifest_dir,
        )
    except (OSError, ValueError, Sec13FError) as exc:
        print(f"SEC 13F capital/control build failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True, default=_json_default))
    certification = receipt.get("certification")
    state = certification.get("certification_state") if isinstance(certification, dict) else None
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
