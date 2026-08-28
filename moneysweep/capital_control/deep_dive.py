from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


class OwnershipDeepDiveError(ValueError):
    pass


@dataclass(frozen=True)
class CertifiedOwnershipScope:
    certification_id: str
    state: str
    scope: str
    bounded_claim_only: bool
    required_periods: tuple[str, ...]
    morningstar_equivalence: str
    regression_counts: Mapping[str, int]


def load_certification(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise OwnershipDeepDiveError(f"ownership certification is not mounted: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise OwnershipDeepDiveError("ownership certification must be a JSON object")
    return data


def load_materialized_holdings(path: Path | str) -> tuple[dict[str, str], ...]:
    source = Path(path)
    if not source.is_file():
        raise OwnershipDeepDiveError(f"ownership holdings are not mounted: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "observation_id",
            "holder_id",
            "issuer_id",
            "as_of_date",
            "report_date",
            "source_record_id",
            "security_cusip",
            "amendment_status",
            "is_active",
            "provider_metric_equivalence",
        }
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise OwnershipDeepDiveError(
                f"ownership holdings missing required fields: {sorted(missing)}"
            )
        return tuple(dict(row) for row in reader)


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    if text in {"", "none", "null"}:
        return None
    raise OwnershipDeepDiveError(f"invalid tri-state boolean: {value!r}")


def _number(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise OwnershipDeepDiveError(f"invalid numeric value: {value!r}") from exc


def _certified_scope(certification: Mapping[str, Any]) -> CertifiedOwnershipScope:
    state = str(certification.get("state") or "")
    if state != "PASS":
        raise OwnershipDeepDiveError(f"ownership certification state is {state or 'UNKNOWN'}, not PASS")
    if certification.get("bounded_claim_only") is not True:
        raise OwnershipDeepDiveError("ownership certification is not explicitly bounded")
    equivalence = str(certification.get("morningstar_percent_total_assets_equivalence") or "")
    if equivalence != "OPEN":
        raise OwnershipDeepDiveError(
            "provider-equivalence state must remain OPEN for SEC ownership promotion"
        )
    periods = tuple(str(value) for value in certification.get("observed_bpop_periods", []))
    if len(periods) != 8 or len(set(periods)) != 8:
        raise OwnershipDeepDiveError("certified BPOP scope must contain exactly eight distinct periods")
    regression_raw = certification.get("regression_counts") or {}
    if not isinstance(regression_raw, Mapping):
        raise OwnershipDeepDiveError("regression_counts must be an object")
    regression_counts = {str(key): int(value) for key, value in regression_raw.items()}
    if regression_counts.get("OFG", 0) <= 0 or regression_counts.get("EVTC", 0) <= 0:
        raise OwnershipDeepDiveError("OFG and EVTC real-source regression coverage is required")
    return CertifiedOwnershipScope(
        certification_id=str(certification.get("certification_id") or ""),
        state=state,
        scope=str(certification.get("scope") or ""),
        bounded_claim_only=True,
        required_periods=tuple(sorted(periods)),
        morningstar_equivalence=equivalence,
        regression_counts=regression_counts,
    )


def build_ownership_deep_dive(
    rows: Iterable[Mapping[str, object]],
    certification: Mapping[str, Any],
    *,
    ticker: str,
    cusip: str,
) -> dict[str, object]:
    """Build a read-only Deep Dive view from an independently certified scope.

    The view intentionally returns whole source observations. It does not sum
    positions across managers, securities, other-manager allocations, or
    amendments because those aggregations can synthesize a record that never
    existed in the source.
    """
    scope = _certified_scope(certification)
    ticker = ticker.strip().upper()
    cusip = cusip.strip().upper()
    if ticker != "BPOP" or cusip != "733174700":
        raise OwnershipDeepDiveError(
            "Deep Dive promotion is currently certified only for BPOP / CUSIP 733174700"
        )

    materialized = [dict(row) for row in rows if str(row.get("security_cusip") or "").upper() == cusip]
    if not materialized:
        raise OwnershipDeepDiveError("certified BPOP holdings contain zero matching observations")

    observation_ids = [str(row.get("observation_id") or "") for row in materialized]
    if any(not value for value in observation_ids) or len(observation_ids) != len(set(observation_ids)):
        raise OwnershipDeepDiveError("observation IDs must be present and unique")

    periods = {str(row.get("as_of_date") or "") for row in materialized}
    if periods != set(scope.required_periods):
        raise OwnershipDeepDiveError(
            "materialized BPOP periods differ from the certified eight-period denominator"
        )

    normalized: list[dict[str, object]] = []
    active_count = 0
    superseded_count = 0
    holder_period_rows: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in materialized:
        if str(row.get("provider_metric_equivalence") or "") != "OPEN":
            raise OwnershipDeepDiveError("provider metric equivalence was promoted unexpectedly")
        active = _as_bool(row.get("is_active"))
        amendment_status = str(row.get("amendment_status") or "")
        if active is True:
            active_count += 1
        elif active is False or amendment_status == "SUPERSEDED":
            superseded_count += 1
        else:
            raise OwnershipDeepDiveError(
                f"observation {row.get('observation_id')} lacks active/superseded adjudication"
            )
        normalized_row = dict(row)
        normalized_row["is_active"] = active
        for field in (
            "shares",
            "market_value",
            "percent_issuer_shares_computed",
            "issuer_share_denominator",
            "percent_13f_reportable_value",
        ):
            if field in normalized_row:
                normalized_row[field] = _number(normalized_row.get(field))
        normalized.append(normalized_row)
        holder_period_rows[str(row.get("holder_id") or "")][str(row.get("as_of_date") or "")].append(
            str(row.get("observation_id") or "")
        )

    if active_count + superseded_count != len(normalized):
        raise OwnershipDeepDiveError("active + superseded arithmetic does not close")

    latest_period = max(scope.required_periods)
    latest_rows = [
        row for row in normalized if row["is_active"] is True and row.get("as_of_date") == latest_period
    ]
    latest_rows.sort(
        key=lambda row: (
            -float(row.get("percent_issuer_shares_computed") or -1.0),
            str(row.get("holder_id") or ""),
            str(row.get("observation_id") or ""),
        )
    )

    period_ledger = []
    for period in scope.required_periods:
        period_rows = [row for row in normalized if row.get("as_of_date") == period]
        active_rows = [row for row in period_rows if row["is_active"] is True]
        period_ledger.append(
            {
                "asOfDate": period,
                "observationCount": len(period_rows),
                "activeObservationCount": len(active_rows),
                "holderCount": len({str(row.get("holder_id") or "") for row in active_rows}),
                "denominatorValues": sorted(
                    {
                        float(row["issuer_share_denominator"])
                        for row in active_rows
                        if row.get("issuer_share_denominator") is not None
                    }
                ),
            }
        )

    return {
        "ticker": ticker,
        "cusip": cusip,
        "certification": {
            "certificationId": scope.certification_id,
            "state": scope.state,
            "scope": scope.scope,
            "boundedClaimOnly": scope.bounded_claim_only,
            "requiredPeriods": list(scope.required_periods),
            "morningstarPercentTotalAssetsEquivalence": scope.morningstar_equivalence,
        },
        "regressionCoverage": dict(scope.regression_counts),
        "latestPeriod": latest_period,
        "observationCount": len(normalized),
        "activeObservationCount": active_count,
        "supersededObservationCount": superseded_count,
        "periodLedger": period_ledger,
        "latestObservations": latest_rows,
        "observations": sorted(
            normalized,
            key=lambda row: (
                str(row.get("as_of_date") or ""),
                str(row.get("holder_id") or ""),
                str(row.get("observation_id") or ""),
            ),
        ),
        "holderPeriodObservationIds": {
            holder: {period: list(ids) for period, ids in sorted(periods_map.items())}
            for holder, periods_map in sorted(holder_period_rows.items())
        },
        "aggregationPolicy": "WHOLE_SOURCE_OBSERVATIONS_ONLY_NO_CROSS_HOLDER_SUMMATION",
        "providerEquivalence": "OPEN",
    }
