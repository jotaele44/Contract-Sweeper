#!/usr/bin/env python3
"""Fail-closed issuer-parameterized SEC Form 13F certification.

This engine reuses the frozen eight-quarter SEC bulk snapshot first certified for
BPOP. Each issuer is adjudicated independently. Parser/regression success never
inherits certification across issuers, provider metric equivalence remains OPEN,
and no synthetic holder or row identity is created.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from pathlib import Path

from moneysweep.capital_control import ingest
from moneysweep.capital_control.models import HoldingObservation, InvestorIdentity
from moneysweep.capital_control.sec13f import (
    Sec13FBulkAdapter,
    Sec13FError,
    adjudicate_sec13f_filing_restatements,
)
from scripts.certify_bpop_sec13f_8q import (
    _bindings,
    _flatten,
    _freeze_identity_issues,
    _holder_identity_cardinality_closed,
    _holder_name_manifestations,
    _load_registry,
    _partition_required_periods,
    _read_denominators,
    _serialize_filing_lineage,
    _write_csv,
)
from scripts.config import PROJECT_ROOT

SUPPORTED_ISSUERS = {
    "BPOP": {
        "cik": "0000763901",
        "issuer_id": "ISSUER_CIK_0000763901",
        "cusip": "733174700",
        "negative_identity": [],
    },
    "OFG": {
        "cik": "0001030469",
        "issuer_id": "ISSUER_CIK_0001030469",
        "cusip": "67103X102",
        "negative_identity": ["CIK:0001016178"],
    },
    "EVTC": {
        "cik": "0001559865",
        "issuer_id": "ISSUER_CIK_0001559865",
        "cusip": "30040P103",
        "negative_identity": ["TICKER:EVRI", "NEAR_NAME_ONLY"],
    },
}


def _select_exact_denominators(
    rows: list[dict[str, str]], ticker: str, required_periods: tuple[date, ...]
) -> tuple[dict[date, float], list[dict[str, object]]]:
    selected: dict[date, float] = {}
    ledger: list[dict[str, object]] = []
    for period in required_periods:
        candidates = [
            row
            for row in rows
            if row.get("ticker", "").upper() == ticker
            and row.get("as_of_date") == period.isoformat()
            and row.get("shares_outstanding", "").strip()
        ]
        values: set[float] = set()
        malformed: list[str] = []
        for row in candidates:
            raw = row.get("shares_outstanding", "")
            try:
                values.add(float(raw))
            except ValueError:
                malformed.append(raw)
        value = next(iter(values)) if len(values) == 1 and not malformed else None
        state = "PASS" if value is not None and value > 0 else "UNRESOLVED"
        if state == "PASS" and value is not None:
            selected[period] = value
        ledger.append(
            {
                "ticker": ticker,
                "as_of_date": period.isoformat(),
                "candidate_count": len(candidates),
                "distinct_values": sorted(values),
                "malformed_values": malformed,
                "selected_value": value if state == "PASS" else None,
                "state": state,
                "candidate_accessions": sorted(
                    {row.get("accession_number", "") for row in candidates}
                ),
                "candidate_concepts": sorted({row.get("concept", "") for row in candidates}),
            }
        )
    return selected, ledger


def _assert_profile_binding(ticker: str, by_ticker: dict[str, dict[str, str]]) -> dict[str, str]:
    profile = SUPPORTED_ISSUERS[ticker]
    binding = by_ticker.get(ticker)
    if binding is None:
        raise ValueError(f"missing registry binding for {ticker}")
    expected = {
        "issuer_id": str(profile["issuer_id"]),
        "cusip": str(profile["cusip"]),
        "cik": str(profile["cik"]),
    }
    for field, value in expected.items():
        if binding.get(field) != value:
            raise ValueError(
                f"{ticker} registry {field} mismatch: {binding.get(field)!r} != {value!r}"
            )
    return binding


def run(*, root: Path, ticker: str) -> dict[str, object]:
    ticker = ticker.strip().upper()
    if ticker not in SUPPORTED_ISSUERS:
        raise ValueError(f"unsupported issuer: {ticker}")

    registry = _load_registry(root / "registries" / "capital_control_golden_cases.json")
    _, all_by_ticker = _bindings(registry)
    binding = _assert_profile_binding(ticker, all_by_ticker)
    required_periods = tuple(
        date.fromisoformat(value) for value in registry["bpop_required_periods"]
    )
    required_archives = tuple(str(value) for value in registry["bpop_required_archives"])
    if len(required_periods) != 8 or len(required_archives) != 8:
        raise ValueError(
            "issuer certifier requires the frozen eight-period/eight-archive denominator"
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
    denominators, denominator_ledger = _select_exact_denominators(
        denominator_rows, ticker, required_periods
    )

    issuer_bindings = {binding["cusip"].upper(): binding["issuer_id"]}
    observations: list[HoldingObservation] = []
    investors: dict[str, InvestorIdentity] = {}
    archive_audits: list[dict[str, object]] = []
    for archive in archive_paths:
        adapter = Sec13FBulkAdapter(
            archive,
            target_cusips=(binding["cusip"].upper(),),
            issuer_bindings=issuer_bindings,
        )
        result = ingest(adapter)
        observations.extend(result.observations)
        for investor in adapter.iter_investors():
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
    observation_ids = [row.observation_id for row in observations]
    source_keys = [(row.source_id, row.source_record_id) for row in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError(f"{ticker}: duplicate observation_id across archives")
    if len(source_keys) != len(set(source_keys)):
        raise ValueError(f"{ticker}: duplicate source record across archives")

    scoped, excluded = _partition_required_periods(observations, required_periods)
    filing_adjudication = adjudicate_sec13f_filing_restatements(scoped)
    active_ids = set(filing_adjudication.active_observation_ids)
    superseded_ids = set(filing_adjudication.superseded_observation_ids)
    lineage_by_observation = {
        observation_id: lineage
        for lineage in filing_adjudication.lineages
        for observation_id in lineage.filing_observation_ids
    }
    preserved_rows: list[HoldingObservation] = []
    for row in scoped:
        lineage = lineage_by_observation.get(row.observation_id)
        extra = dict(row.extra)
        if lineage is not None:
            extra["filing_restatement_state"] = lineage.state
            extra["supersedes_filing_accession_numbers"] = "|".join(
                lineage.prior_filing_accession_numbers
            )
        preserved_rows.append(
            replace(
                row,
                amendment_status=(
                    "SUPERSEDED" if row.observation_id in superseded_ids else row.amendment_status
                ),
                extra=extra,
            )
        )
    preserved = tuple(preserved_rows)

    name_manifestations = _holder_name_manifestations(preserved)
    names_by_holder: dict[str, set[str]] = {}
    for item in name_manifestations:
        names_by_holder.setdefault(str(item["holder_id"]), set()).add(
            str(item["filing_manager_name_raw"])
        )

    materialized_rows = [
        _flatten(
            row,
            active=row.observation_id in active_ids,
            denominator=denominators.get(row.as_of_date),
        )
        for row in preserved
    ]
    output_dir = root / "data" / "staging" / "processed" / "capital_control" / ticker.lower()
    manifest_dir = root / "data" / "manifests" / "capital_control"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    materialized_count = _write_csv(output_dir / "holdings.csv", materialized_rows)

    excluded_rows: list[dict[str, object]] = []
    for row in excluded:
        excluded_payload = _flatten(row, active=None, denominator=None)
        excluded_payload["certification_scope_state"] = "OUTSIDE_REQUIRED_PERIOD"
        excluded_payload["certification_exclusion_reason"] = (
            "PERIODOFREPORT_NOT_IN_CERTIFICATION_DENOMINATOR"
        )
        excluded_rows.append(excluded_payload)
    excluded_count = _write_csv(output_dir / "excluded_periods.csv", excluded_rows)

    holder_ids = {row.holder_id for row in preserved}
    investor_rows: list[dict[str, object]] = []
    for investor in investors.values():
        if investor.investor_id not in holder_ids:
            continue
        investor_payload: dict[str, object] = asdict(investor)
        investor_payload["raw_name_role"] = "REPRESENTATIVE_ONLY"
        investor_payload["name_manifestation_count"] = len(
            names_by_holder.get(investor.investor_id, set())
        )
        investor_rows.append(investor_payload)
    _write_csv(output_dir / "investors.csv", investor_rows)
    _write_csv(output_dir / "holder_name_manifestations.csv", name_manifestations)
    materialized_investor_ids = {str(row["investor_id"]) for row in investor_rows}

    eligible = [
        row
        for row in materialized_rows
        if row.get("issuer_percent_eligibility") == "ELIGIBLE_COMMON_SHARE_POSITION"
    ]
    observed_periods = {row.as_of_date for row in preserved}
    expected_security_id = f"CUSIP:{binding['cusip'].upper()}"
    profile = SUPPORTED_ISSUERS[ticker]
    gates = {
        "exact_archive_count_8": len(archive_audits) == 8,
        "archive_names_exact": tuple(item["archive"] for item in archive_audits)
        == required_archives,
        "all_archive_hashes_present": all(
            len(str(item["sha256"])) == 64 for item in archive_audits
        ),
        "freeze_manifest_identity_exact": not freeze_identity_issues,
        "row_conservation": len(scoped) == materialized_count == len(preserved),
        "period_partition_conservation": discovery_count == len(scoped) + excluded_count,
        "observation_id_unique": len(observation_ids) == len(set(observation_ids)),
        "source_record_unique": len(source_keys) == len(set(source_keys)),
        "issuer_rows_present": len(preserved) > 0,
        "all_required_periods_present": observed_periods == set(required_periods),
        "exact_denominator_each_period": set(denominators) == set(required_periods),
        "eligible_rows_have_percent": all(
            row.get("percent_issuer_shares_computed") is not None for row in eligible
        ),
        "issuer_binding_exact": all(
            row.issuer_id == binding["issuer_id"] and row.security_id == expected_security_id
            for row in preserved
        ),
        "holder_ids_are_stable_cik_ids": all(
            row.holder_id.startswith("INV_CIK_") for row in preserved
        ),
        "holder_identity_cardinality_closed": _holder_identity_cardinality_closed(
            holder_ids, materialized_investor_ids
        ),
        "holder_name_manifestations_preserved": holder_ids == set(names_by_holder),
        "supersession_arithmetic": len(active_ids) + len(superseded_ids) == len(preserved),
        "restatement_filing_lineage_closed": sum(
            len(lineage.filing_observation_ids) for lineage in filing_adjudication.lineages
        )
        == sum(
            str(row.extra.get("source_amendment_type") or "").strip().upper()
            in {"RESTATEMENT", "RESTATED"}
            for row in preserved
        ),
        "provider_equivalence_not_promoted": all(
            row.get("provider_metric_equivalence") == "OPEN" for row in materialized_rows
        ),
        "negative_identity_controls_bound": bool(profile["negative_identity"]) or ticker == "BPOP",
    }
    state = "PASS" if all(gates.values()) else "OPEN"
    residue = sorted(name for name, passed in gates.items() if not passed)
    certification: dict[str, object] = {
        "schema": "moneysweep.sec13f-issuer-certification/v1",
        "certification_id": f"{ticker}_SEC13F_8Q_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "issuer_cik": profile["cik"],
        "issuer_id": binding["issuer_id"],
        "cusip": binding["cusip"],
        "scope": f"SEC Form 13F {ticker} ownership observations over the frozen BPOP eight-quarter archive snapshot",
        "state": state,
        "deep_dive_promotion": "ELIGIBLE" if state == "PASS" else "NOT_ELIGIBLE",
        "bounded_claim_only": True,
        "certification_inheritance": "FORBIDDEN",
        "synthetic_row_identity": "FORBIDDEN",
        "aggregation_policy": "WHOLE_SOURCE_OBSERVATIONS_ONLY_NO_CROSS_HOLDER_SUMMATION",
        "provider_equivalence": "OPEN",
        "negative_identity_controls": profile["negative_identity"],
        "required_periods": [value.isoformat() for value in required_periods],
        "observed_periods": sorted(value.isoformat() for value in observed_periods),
        "denominator_ledger": denominator_ledger,
        "archive_audits": archive_audits,
        "freeze_identity_issues": freeze_identity_issues,
        "discovered_observation_count": discovery_count,
        "source_observation_count": len(scoped),
        "excluded_out_of_period_count": excluded_count,
        "active_observation_count": len(active_ids),
        "superseded_observation_count": len(superseded_ids),
        "eligible_common_share_rows": len(eligible),
        "filing_restatement_lineages": [
            _serialize_filing_lineage(lineage) for lineage in filing_adjudication.lineages
        ],
        "gates": gates,
        "unresolved_residue": residue,
    }
    manifest_path = manifest_dir / f"{ticker.lower()}_sec13f_8q_certification_v1.json"
    manifest_path.write_text(
        json.dumps(certification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return certification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", choices=tuple(SUPPORTED_ISSUERS))
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    try:
        certification = run(root=args.root, ticker=args.ticker)
    except (FileNotFoundError, ValueError, Sec13FError) as exc:
        print(f"CERTIFICATION_BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(certification, indent=2, sort_keys=True))
    return 0 if certification["state"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
