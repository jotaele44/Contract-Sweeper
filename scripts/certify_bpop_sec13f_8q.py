#!/usr/bin/env python3
"""Materialize and certify the bounded BPOP SEC 13F eight-quarter corpus.

The certifier fails closed. It requires the exact eight frozen SEC archives,
unique exact-date shares-outstanding denominators for every required BPOP
period, closed filing-level restatement lineage, row conservation, stable issuer
CUSIP bindings, and at least one OFG/EVTC regression observation. It does not
claim Morningstar metric equivalence and never aggregates options into shares
held.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from moneysweep.capital_control import ingest
from moneysweep.capital_control.models import HoldingObservation, InvestorIdentity
from moneysweep.capital_control.sec13f import (
    FilingRestatementLineage,
    Sec13FBulkAdapter,
    Sec13FError,
    adjudicate_sec13f_filing_restatements,
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
    for index, raw in enumerate(data.get("issuer_bindings", [])):
        if not isinstance(raw, dict):
            raise ValueError(f"issuer_bindings[{index}] must be an object")
        item = {str(k): str(v) for k, v in raw.items() if v is not None}
        required = {"ticker", "cusip", "issuer_id"}
        missing = sorted(required - set(item))
        if missing:
            raise ValueError(f"issuer_bindings[{index}] missing required fields: {missing}")
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
            raise ValueError(
                f"denominator file missing fields {sorted(required - set(reader.fieldnames or []))}"
            )
        return list(reader)


def _freeze_identity_issues(
    freeze: dict[str, Any],
    archive_audits: Iterable[dict[str, object]],
    required_archives: Iterable[str],
) -> list[str]:
    required = tuple(required_archives)
    raw_expected = freeze.get("archives")
    if not isinstance(raw_expected, list):
        return ["freeze manifest archives must be a list"]
    expected = {str(item.get("filename")): item for item in raw_expected if isinstance(item, dict)}
    actual = {str(item.get("archive")): item for item in archive_audits}
    issues: list[str] = []
    if freeze.get("archive_count") != len(required):
        issues.append("freeze manifest archive_count differs from required denominator")
    if set(expected) != set(required):
        issues.append("freeze manifest archive names differ from required denominator")
    if set(actual) != set(required):
        issues.append("audited archive names differ from required denominator")
    for name in required:
        expected_item = expected.get(name)
        actual_item = actual.get(name)
        if expected_item is None or actual_item is None:
            continue
        for field in ("byte_size", "sha256"):
            if actual_item.get(field) != expected_item.get(field):
                issues.append(f"{name}: {field} differs from frozen manifest")
        expected_members = sorted(
            (
                str(member.get("path")),
                member.get("uncompressed_size"),
                str(member.get("sha256")),
            )
            for member in expected_item.get("members", [])
            if isinstance(member, dict)
        )
        actual_members = sorted(
            (
                str(member.get("path")),
                member.get("uncompressed_size"),
                str(member.get("sha256")),
            )
            for member in actual_item.get("member_digests", [])
            if isinstance(member, dict)
        )
        if actual_members != expected_members:
            issues.append(f"{name}: member path/size/SHA payload differs from frozen manifest")
    return issues


def _select_bpop_denominators(
    rows: list[dict[str, str]], required_periods: tuple[date, ...]
) -> tuple[dict[date, float], list[dict[str, object]]]:
    selected: dict[date, float] = {}
    ledger: list[dict[str, object]] = []
    for period in required_periods:
        candidates = [
            row
            for row in rows
            if row.get("ticker", "").upper() == "BPOP"
            and row.get("as_of_date") == period.isoformat()
            and row.get("shares_outstanding", "").strip()
        ]
        values: set[float] = set()
        for row in candidates:
            try:
                values.add(float(row["shares_outstanding"]))
            except ValueError as exc:
                raise ValueError(
                    f"invalid BPOP denominator at {period}: {row['shares_outstanding']!r}"
                ) from exc
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
                "candidate_accessions": sorted(
                    {row.get("accession_number", "") for row in candidates}
                ),
                "candidate_concepts": sorted({row.get("concept", "") for row in candidates}),
            }
        )
    return selected, ledger


def _flatten(
    row: HoldingObservation, *, active: bool | None, denominator: float | None
) -> dict[str, object]:
    payload = asdict(row)
    extra = dict(payload.pop("extra") or {})
    put_call = str(extra.get("put_call") or "").strip().upper()
    shares = row.shares
    eligible = shares is not None and not put_call
    percent = (
        shares / denominator * 100.0
        if shares is not None and not put_call and denominator is not None and denominator > 0
        else None
    )
    payload.update(extra)
    payload["security_cusip"] = str(row.security_id or "").removeprefix("CUSIP:")
    payload["is_active"] = active
    payload["issuer_share_denominator"] = denominator
    payload["percent_issuer_shares_computed"] = percent
    payload["issuer_percent_eligibility"] = (
        "ELIGIBLE_COMMON_SHARE_POSITION" if eligible else "EXCLUDED_OPTION_OR_NONSHARE_POSITION"
    )
    payload["provider_percent_total_assets"] = None
    if payload.get("provider_metric_equivalence") != "OPEN":
        raise ValueError(f"provider metric equivalence must remain OPEN: {row.observation_id}")
    return payload


def _partition_required_periods(
    rows: Iterable[HoldingObservation], required_periods: Iterable[date]
) -> tuple[tuple[HoldingObservation, ...], tuple[HoldingObservation, ...]]:
    required = frozenset(required_periods)
    if not required:
        raise ValueError("required period denominator must not be empty")
    candidates = tuple(rows)
    in_scope: list[HoldingObservation] = []
    excluded: list[HoldingObservation] = []
    for row in candidates:
        (in_scope if row.as_of_date in required else excluded).append(row)
    if len(in_scope) + len(excluded) != len(candidates):
        raise AssertionError("period partition arithmetic failed")
    return tuple(in_scope), tuple(excluded)


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


def _holder_name_manifestations(
    rows: Iterable[HoldingObservation],
) -> list[dict[str, object]]:
    """Preserve raw SEC filer names without treating name drift as identity drift.

    CIK is the stable SEC filer identity. FILINGMANAGER_NAME is a source
    manifestation and can legitimately vary over time. The manifestation key
    is bounded to the filing accession/archive so every distinct observed raw
    string remains auditable without multiplying canonical investor identity.
    """
    manifestations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        raw_name = str(row.extra.get("filing_manager_name_raw") or "")
        accession = str(row.extra.get("accession_number") or "")
        archive = str(row.extra.get("source_archive") or "")
        if not raw_name or not accession or not archive:
            raise ValueError(
                f"holder name manifestation missing raw provenance: {row.observation_id}"
            )
        key = (row.holder_id, accession, archive, raw_name)
        if key in seen:
            continue
        seen.add(key)
        manifestations.append(
            {
                "holder_id": row.holder_id,
                "filer_cik": str(row.extra.get("filer_cik") or ""),
                "filing_manager_name_raw": raw_name,
                "accession_number": accession,
                "source_archive": archive,
                "as_of_date": row.as_of_date.isoformat(),
                "report_date": row.report_date.isoformat(),
                "identity_binding": "STABLE_CIK",
                "name_identity_role": "SOURCE_MANIFESTATION_NOT_IDENTITY_PROOF",
            }
        )
    return manifestations


def _holder_identity_cardinality_closed(
    holder_ids: set[str], materialized_investor_ids: set[str]
) -> bool:
    """Compare identities only within the certification period partition."""
    return holder_ids == materialized_investor_ids


def _serialize_filing_lineage(lineage: FilingRestatementLineage) -> dict[str, object]:
    payload = asdict(lineage)
    payload["as_of_date"] = lineage.as_of_date.isoformat()
    return payload


def run(*, root: Path) -> dict[str, object]:
    registry_path = root / "registries" / "capital_control_golden_cases.json"
    data = _load_registry(registry_path)
    issuer_bindings, by_ticker = _bindings(data)
    required_periods = tuple(date.fromisoformat(value) for value in data["bpop_required_periods"])
    required_archives = tuple(str(value) for value in data["bpop_required_archives"])
    if len(required_periods) != 8 or len(required_archives) != 8:
        raise ValueError(
            "BPOP certification denominator must contain exactly eight periods/archives"
        )

    archive_dir = root / "data" / "staging" / "raw" / "sec13f_bulk" / "bpop_8q_v1"
    archive_paths = tuple(archive_dir / name for name in required_archives)
    missing_files = [path.name for path in archive_paths if not path.is_file()]
    if missing_files:
        raise FileNotFoundError(f"missing frozen SEC archives: {missing_files}")
    freeze_manifest = _load_registry(
        root / "data" / "manifests" / "capital_control" / "bpop_8q_freeze_manifest.json"
    )

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
            # The CIK is the authoritative legal-entity identity. A different
            # raw SEC manager-name string in another archive is preserved below
            # as a NAME manifestation; it does not override the stable ID.
            investors.setdefault(investor.investor_id, investor)
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
    freeze_identity_issues = _freeze_identity_issues(
        freeze_manifest, archive_audits, required_archives
    )

    discovery_count = len(observations)
    if len({row.observation_id for row in observations}) != discovery_count:
        raise ValueError("duplicate observation_id across archives")
    discovery_keys = [(row.source_id, row.source_record_id) for row in observations]
    if len(discovery_keys) != len(set(discovery_keys)):
        raise ValueError("duplicate source record across archives")

    scoped_observations, excluded_observations = _partition_required_periods(
        observations, required_periods
    )
    source_count = len(scoped_observations)
    if discovery_count != source_count + len(excluded_observations):
        raise AssertionError("discovery period partition violated row conservation")

    filing_adjudication = adjudicate_sec13f_filing_restatements(scoped_observations)
    superseded_ids = set(filing_adjudication.superseded_observation_ids)
    active_ids = set(filing_adjudication.active_observation_ids)
    lineage_by_observation = {
        observation_id: lineage
        for lineage in filing_adjudication.lineages
        for observation_id in lineage.filing_observation_ids
    }
    preserved = []
    for row in scoped_observations:
        lineage = lineage_by_observation.get(row.observation_id)
        extra = dict(row.extra)
        if lineage is not None:
            extra["filing_restatement_state"] = lineage.state
            extra["supersedes_filing_accession_numbers"] = "|".join(
                lineage.prior_filing_accession_numbers
            )
        preserved.append(
            replace(
                row,
                amendment_status=(
                    "SUPERSEDED" if row.observation_id in superseded_ids else row.amendment_status
                ),
                extra=extra,
            )
        )
    preserved = tuple(preserved)
    if len(preserved) != source_count:
        raise AssertionError("supersession violated row conservation")

    name_manifestations = _holder_name_manifestations(preserved)
    names_by_holder: dict[str, set[str]] = {}
    for item in name_manifestations:
        holder_id = str(item["holder_id"])
        names_by_holder.setdefault(holder_id, set()).add(str(item["filing_manager_name_raw"]))
    name_variations = {
        holder_id: sorted(names) for holder_id, names in names_by_holder.items() if len(names) > 1
    }

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
            denominator=denominators.get(row.as_of_date)
            if row.security_id == f"CUSIP:{bpop_cusip}"
            else None,
        )
        for row in preserved
    ]
    materialized_count = _write_csv(output_dir / "sec13f_pr_golden_holdings.csv", materialized_rows)
    excluded_rows = []
    for row in excluded_observations:
        payload = _flatten(row, active=None, denominator=None)
        payload["certification_scope_state"] = "OUTSIDE_REQUIRED_PERIOD"
        payload["certification_exclusion_reason"] = "PERIODOFREPORT_NOT_IN_GOLDEN_DENOMINATOR"
        excluded_rows.append(payload)
    excluded_count = _write_csv(output_dir / "sec13f_pr_golden_excluded_periods.csv", excluded_rows)
    holder_ids_in_observations = {row.holder_id for row in preserved}
    investor_rows: list[dict[str, object]] = []
    for investor in investors.values():
        if investor.investor_id not in holder_ids_in_observations:
            continue
        payload: dict[str, object] = asdict(investor)
        payload["raw_name_role"] = "REPRESENTATIVE_ONLY"
        payload["name_manifestation_count"] = len(names_by_holder.get(investor.investor_id, set()))
        payload["name_variation_state"] = (
            "NAME_VARIATION_STABLE_ID_BOUND"
            if investor.investor_id in name_variations
            else "SINGLE_RAW_NAME_OBSERVED"
        )
        investor_rows.append(payload)
    materialized_investor_ids = {
        str(row["investor_id"]) for row in investor_rows
    }
    _write_csv(output_dir / "sec13f_pr_golden_investors.csv", investor_rows)
    _write_csv(output_dir / "sec13f_holder_name_manifestations.csv", name_manifestations)

    bpop_eligible = [
        row
        for row in materialized_rows
        if row.get("security_cusip") == bpop_cusip
        and row.get("issuer_percent_eligibility") == "ELIGIBLE_COMMON_SHARE_POSITION"
    ]
    gates = {
        "exact_archive_count_8": len(archive_audits) == 8,
        "archive_names_exact": tuple(item["archive"] for item in archive_audits)
        == required_archives,
        "all_archive_hashes_present": all(
            len(str(item["sha256"])) == 64 for item in archive_audits
        ),
        "freeze_manifest_identity_exact": not freeze_identity_issues,
        "row_conservation": source_count == materialized_count == len(preserved),
        "source_record_unique": len(discovery_keys) == len(set(discovery_keys)),
        "period_partition_conservation": discovery_count == source_count + excluded_count,
        "restatement_filing_lineage_closed": sum(
            len(lineage.filing_observation_ids)
            for lineage in filing_adjudication.lineages
        )
        == sum(
            str(row.extra.get("source_amendment_type") or "").strip().upper()
            in {"RESTATEMENT", "RESTATED"}
            for row in preserved
        ),
        "bpop_all_eight_periods_present": observed_periods == set(required_periods),
        "bpop_exact_denominator_each_period": set(denominators) == set(required_periods),
        "bpop_eligible_rows_have_percent": all(
            row.get("percent_issuer_shares_computed") is not None for row in bpop_eligible
        ),
        "bpop_rows_present": len(bpop_rows) > 0,
        "ofg_regression_rows_present": regression_counts["OFG"] > 0,
        "evtc_regression_rows_present": regression_counts["EVTC"] > 0,
        "issuer_bindings_pass": all(row.identity_status == "PASS" for row in preserved),
        "holder_ids_are_stable_cik_ids": all(
            row.holder_id.startswith("INV_CIK_") for row in preserved
        ),
        "holder_identity_cardinality_closed": _holder_identity_cardinality_closed(
            holder_ids_in_observations, materialized_investor_ids
        ),
        "holder_name_manifestations_preserved": holder_ids_in_observations == set(names_by_holder),
        "supersession_arithmetic": len(active_ids) + len(superseded_ids) == len(preserved),
        "provider_equivalence_not_promoted": all(
            row.get("provider_metric_equivalence") == "OPEN" for row in materialized_rows
        ),
    }
    state = "PASS" if all(gates.values()) else "OPEN"
    certification = {
        "certification_id": "BPOP_SEC13F_8Q_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "SEC Form 13F BPOP ownership observations 2024Q2-2026Q1 plus OFG/EVTC parser regressions",
        "state": state,
        "bounded_claim_only": True,
        "discovered_observation_count": discovery_count,
        "source_observation_count": source_count,
        "excluded_out_of_period_count": excluded_count,
        "active_observation_count": len(active_ids),
        "superseded_observation_count": len(superseded_ids),
        "bpop_observation_count": len(bpop_rows),
        "bpop_eligible_common_share_rows": len(bpop_eligible),
        "regression_counts": regression_counts,
        "observed_bpop_periods": sorted(value.isoformat() for value in observed_periods),
        "denominator_ledger": denominator_ledger,
        "filing_restatement_lineages": [
            _serialize_filing_lineage(lineage)
            for lineage in filing_adjudication.lineages
        ],
        "filing_restatement_count": len(filing_adjudication.lineages),
        "filing_restatements_without_prior_target_rows": sum(
            not lineage.prior_filing_accession_numbers
            for lineage in filing_adjudication.lineages
        ),
        "holder_name_variation_count": len(name_variations),
        "holder_name_variations": name_variations,
        "holder_name_variation_adjudication": (
            "NAME source manifestations preserved; stable SEC CIK remains authoritative identity"
        ),
        "archive_audits": archive_audits,
        "freeze_identity_issues": freeze_identity_issues,
        "gates": gates,
        "morningstar_percent_total_assets_equivalence": "OPEN",
        "deep_dive_promotion": "BLOCKED"
        if state != "PASS"
        else "ELIGIBLE_FOR_SEPARATE_PROMOTION_VECTOR",
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
    except (OSError, ValueError, Sec13FError, AssertionError) as exc:
        print(f"BPOP SEC13F certification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
