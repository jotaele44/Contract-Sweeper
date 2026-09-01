from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


CERTIFICATION_ID = "BPOP_SEC13F_8Q_v1"
BPOP_CIK = "0000763901"
BPOP_CUSIP = "733174700"
BPOP_ISSUER_ID = f"ISSUER_CIK_{BPOP_CIK}"
BPOP_PERIODS = (
    "2024-06-30",
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
    "2026-03-31",
)


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
            "accession_number",
            "infotable_sk",
            "filer_cik",
            "source_document_sha256",
            "issuer_percent_eligibility",
            "issuer_share_denominator",
            "percent_issuer_shares_computed",
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
        number = float(text)
    except ValueError as exc:
        raise OwnershipDeepDiveError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(number):
        raise OwnershipDeepDiveError(f"non-finite numeric value: {value!r}")
    return number


def _certified_scope(certification: Mapping[str, Any]) -> CertifiedOwnershipScope:
    state = str(certification.get("state") or "")
    if state != "PASS":
        raise OwnershipDeepDiveError(
            f"ownership certification state is {state or 'UNKNOWN'}, not PASS"
        )
    certification_id = str(certification.get("certification_id") or "")
    if certification_id != CERTIFICATION_ID:
        raise OwnershipDeepDiveError(
            f"unexpected ownership certification id: {certification_id or 'MISSING'}"
        )
    if certification.get("bounded_claim_only") is not True:
        raise OwnershipDeepDiveError("ownership certification is not explicitly bounded")
    if certification.get("deep_dive_promotion") != "ELIGIBLE_FOR_SEPARATE_PROMOTION_VECTOR":
        raise OwnershipDeepDiveError("upstream certification did not authorize a promotion vector")

    raw_gates = certification.get("gates")
    if not isinstance(raw_gates, Mapping) or not raw_gates:
        raise OwnershipDeepDiveError("ownership certification gates are absent")
    failed_gates = sorted(str(key) for key, value in raw_gates.items() if value is not True)
    if failed_gates:
        raise OwnershipDeepDiveError(
            f"ownership certification contains non-PASS gates: {failed_gates}"
        )

    equivalence = str(certification.get("morningstar_percent_total_assets_equivalence") or "")
    if equivalence != "OPEN":
        raise OwnershipDeepDiveError(
            "provider-equivalence state must remain OPEN for SEC ownership promotion"
        )
    periods = tuple(str(value) for value in certification.get("observed_bpop_periods", []))
    if tuple(sorted(periods)) != BPOP_PERIODS:
        raise OwnershipDeepDiveError(
            "certified BPOP periods differ from the exact eight-quarter promotion contract"
        )

    regression_raw = certification.get("regression_counts") or {}
    if not isinstance(regression_raw, Mapping):
        raise OwnershipDeepDiveError("regression_counts must be an object")
    regression_counts = {str(key): int(value) for key, value in regression_raw.items()}
    if regression_counts.get("OFG", 0) <= 0 or regression_counts.get("EVTC", 0) <= 0:
        raise OwnershipDeepDiveError("OFG and EVTC real-source regression coverage is required")
    return CertifiedOwnershipScope(
        certification_id=certification_id,
        state=state,
        scope=str(certification.get("scope") or ""),
        bounded_claim_only=True,
        required_periods=BPOP_PERIODS,
        morningstar_equivalence=equivalence,
        regression_counts=regression_counts,
    )


def _validate_source_identity(row: Mapping[str, object]) -> None:
    observation_id = str(row.get("observation_id") or "")
    accession = str(row.get("accession_number") or "").strip()
    infotable_sk = str(row.get("infotable_sk") or "").strip()
    source_record_id = str(row.get("source_record_id") or "").strip()
    filer_cik = str(row.get("filer_cik") or "").strip()
    holder_id = str(row.get("holder_id") or "").strip()
    source_hash = str(row.get("source_document_sha256") or "").strip().lower()
    issuer_id = str(row.get("issuer_id") or "").strip()

    if not observation_id or not accession or not infotable_sk:
        raise OwnershipDeepDiveError("observation/accession/INFOTABLE_SK identity is incomplete")
    if source_record_id != f"{accession}:{infotable_sk}":
        raise OwnershipDeepDiveError(
            f"{observation_id}: source_record_id does not match accession + INFOTABLE_SK"
        )
    if filer_cik != filer_cik.zfill(10) or not filer_cik.isdigit():
        raise OwnershipDeepDiveError(f"{observation_id}: invalid SEC filer CIK")
    if holder_id != f"INV_CIK_{filer_cik}":
        raise OwnershipDeepDiveError(f"{observation_id}: holder ID is not bound to filer CIK")
    if issuer_id != BPOP_ISSUER_ID:
        raise OwnershipDeepDiveError(f"{observation_id}: issuer ID is outside BPOP scope")
    if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
        raise OwnershipDeepDiveError(f"{observation_id}: invalid source-document SHA256")


def _validate_eligible_percent(row: Mapping[str, object]) -> None:
    if row.get("issuer_percent_eligibility") != "ELIGIBLE_COMMON_SHARE_POSITION":
        return
    shares_value = _number(row.get("shares"))
    denominator_value = _number(row.get("issuer_share_denominator"))
    percent_value = _number(row.get("percent_issuer_shares_computed"))
    if shares_value is None or denominator_value is None or percent_value is None:
        raise OwnershipDeepDiveError(
            f"{row.get('observation_id')}: eligible common-share position lacks denominator/percent"
        )
    if shares_value < 0 or denominator_value <= 0:
        raise OwnershipDeepDiveError(
            f"{row.get('observation_id')}: invalid shares or issuer denominator"
        )
    expected = shares_value / denominator_value * 100.0
    if not math.isclose(percent_value, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise OwnershipDeepDiveError(
            f"{row.get('observation_id')}: issuer percentage arithmetic does not close"
        )


def _sort_percent(row: Mapping[str, object]) -> float:
    value = _number(row.get("percent_issuer_shares_computed"))
    return value if value is not None else -1.0


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
    if ticker != "BPOP" or cusip != BPOP_CUSIP:
        raise OwnershipDeepDiveError(
            f"Deep Dive promotion is currently certified only for BPOP / CUSIP {BPOP_CUSIP}"
        )

    materialized = [
        dict(row) for row in rows if str(row.get("security_cusip") or "").strip().upper() == cusip
    ]
    if not materialized:
        raise OwnershipDeepDiveError("certified BPOP holdings contain zero matching observations")

    observation_ids = [str(row.get("observation_id") or "") for row in materialized]
    if any(not value for value in observation_ids) or len(observation_ids) != len(
        set(observation_ids)
    ):
        raise OwnershipDeepDiveError("observation IDs must be present and unique")
    source_record_ids = [str(row.get("source_record_id") or "") for row in materialized]
    if any(not value for value in source_record_ids) or len(source_record_ids) != len(
        set(source_record_ids)
    ):
        raise OwnershipDeepDiveError("source record IDs must be present and unique")

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
        _validate_source_identity(row)
        if str(row.get("provider_metric_equivalence") or "") != "OPEN":
            raise OwnershipDeepDiveError("provider metric equivalence was promoted unexpectedly")
        active = _as_bool(row.get("is_active"))
        amendment_status = str(row.get("amendment_status") or "")
        if active is True and amendment_status == "SUPERSEDED":
            raise OwnershipDeepDiveError(
                f"observation {row.get('observation_id')} is both active and SUPERSEDED"
            )
        if active is True:
            active_count += 1
        elif active is False and amendment_status == "SUPERSEDED":
            superseded_count += 1
        else:
            raise OwnershipDeepDiveError(
                f"observation {row.get('observation_id')} lacks closed active/superseded state"
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
        _validate_eligible_percent(normalized_row)
        normalized.append(normalized_row)
        holder_period_rows[str(row.get("holder_id") or "")][
            str(row.get("as_of_date") or "")
        ].append(str(row.get("observation_id") or ""))

    if active_count + superseded_count != len(normalized):
        raise OwnershipDeepDiveError("active + superseded arithmetic does not close")

    period_ledger = []
    for period in scope.required_periods:
        period_rows = [row for row in normalized if row.get("as_of_date") == period]
        active_rows = [row for row in period_rows if row["is_active"] is True]
        denominators: set[float] = set()
        for row in active_rows:
            if row.get("issuer_percent_eligibility") != "ELIGIBLE_COMMON_SHARE_POSITION":
                continue
            denominator = _number(row.get("issuer_share_denominator"))
            if denominator is not None:
                denominators.add(denominator)
        if len(denominators) != 1:
            raise OwnershipDeepDiveError(
                f"{period}: active eligible BPOP rows lack one exact positive denominator"
            )
        denominator_value = next(iter(denominators))
        if denominator_value <= 0:
            raise OwnershipDeepDiveError(
                f"{period}: active eligible BPOP rows lack one exact positive denominator"
            )
        period_ledger.append(
            {
                "asOfDate": period,
                "observationCount": len(period_rows),
                "activeObservationCount": len(active_rows),
                "holderCount": len({str(row.get("holder_id") or "") for row in active_rows}),
                "denominatorValues": sorted(denominators),
            }
        )

    latest_period = max(scope.required_periods)
    latest_rows = [
        row
        for row in normalized
        if row["is_active"] is True and row.get("as_of_date") == latest_period
    ]
    latest_rows.sort(
        key=lambda row: (
            -_sort_percent(row),
            str(row.get("holder_id") or ""),
            str(row.get("observation_id") or ""),
        )
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
