"""Coverage-contract control plane — multi-dimensional completeness evaluation.

Replaces the binary "min_rows reached ⇒ complete" reading of the source
registry with contract-driven evaluation (gap-closure phase 1):

* **Coverage contracts** (``registries/coverage_contracts.yaml`` → generated
  ``.json``, schema ``schemas/coverage_contract.schema.json``) declare what
  *complete* means per source: record grain, authoritative universe
  (denominator) and its measurement method, uniqueness key, required-field
  completeness floors, and monetary reconciliation.
* **Status vector** — seven orthogonal dimensions replace the single
  materialization flag: ``wired_status``, ``acquisition_status``,
  ``materialization_status``, ``coverage_status``, ``reconciliation_status``,
  ``freshness_status``, ``certification_status`` — plus a ``materiality_label``.
* **The load-bearing invariant**: ``validated_complete`` (and
  ``certified_complete``) require ``coverage_status == "meets_contract"``,
  which requires a contract with universe evidence. ``min_rows: 1`` alone can
  never produce a complete label anywhere.

Stdlib-only, like the sibling validators (no ``jsonschema``/PyYAML at runtime
— reads the generated JSON, mirroring ``moneysweep/runtime/source_registry.py``).

CLI::

    python -m moneysweep.validation.completeness --root . [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_JSON = "registries/coverage_contracts.json"
SCHEMA_VERSION = "coverage_contracts_v1"

# ---------------------------------------------------------------------------
# Vocabularies (the JSON schema mirrors these; this module is authoritative
# at runtime, the same self-contained-validator pattern as
# update_controller/policy.py).
# ---------------------------------------------------------------------------
CANONICAL_GRAINS = frozenset(
    {
        "contract",
        "award",
        "transaction",
        "subaward",
        "entity",
        "filing",
        "project",
        "activity",
        "donation",
        "registration",
        "audit_report",
        "security",
        "loan",
        "payment",
    }
)
GEOGRAPHY_SCOPES = frozenset({"PR", "US_PR", "US", "global"})
UNIVERSE_METHODS = frozenset(
    {
        "api_metadata",
        "bulk_file_metadata",
        "committed_extract_page_validation",
        "portal_count",
        "document_index",
        "operator_attestation",
    }
)
PERIOD_TYPES = frozenset({"snapshot", "rolling", "bounded"})

WIRED_STATUSES = (
    "wired_adapter",
    "wired_producer",
    "manual_dropzone",
    "scraper_stub",
    "deferred",
    "semantic_duplicate",
    "broken",
)
ACQUISITION_STATUSES = (
    "automated",
    "acquired_ingested",
    "acquired_not_ingested",
    "not_acquired",
)
MATERIALIZATION_STATUSES = (
    "fully_materialized",
    "partially_materialized",
    "not_materialized",
    "no_outputs_declared",
)
COVERAGE_STATUSES = ("meets_contract", "below_contract", "unverifiable", "uncontracted")
RECONCILIATION_STATUSES = (
    "reconciled",
    "variance_exceeds_tolerance",
    "not_evaluated",
    "not_applicable",
)
FRESHNESS_STATUSES = ("fresh", "stale", "unknown")
CERTIFICATION_STATUSES = ("certified_complete", "provisional", "uncertified")
MATERIALITY_LABELS = (
    "empty",
    "fixture",
    "seed",
    "partial",
    "substantial",
    "validated_complete",
    "complete_stale",
)

# path_type (build_source_recovery_matrix._classify) -> wired_status
_PATH_TYPE_TO_WIRED = {
    "api_adapter": "wired_adapter",
    "api_producer": "wired_producer",
    "manual_export": "manual_dropzone",
    "scraper_needed": "scraper_stub",
    "deferred_stub": "deferred",
    "semantic_duplicate": "semantic_duplicate",
    "broken_producer": "broken",
}

# Row-count tiers shared with scripts/audit_materialization_coverage.py
# (kept numerically identical; that module remains the tier authority for
# its own reports).
_TIER_BULK_MIN = 1000
_TIER_MODERATE_MIN = 50


@dataclass(frozen=True)
class StatusVector:
    """One source's completeness state across all control-plane dimensions."""

    source_id: str
    wired_status: str
    acquisition_status: str
    materialization_status: str
    coverage_status: str
    reconciliation_status: str
    freshness_status: str
    certification_status: str
    materiality_label: str
    has_contract: bool
    coverage_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["coverage_reasons"] = ";".join(self.coverage_reasons)
        return d


# ---------------------------------------------------------------------------
# Loading + structural validation
# ---------------------------------------------------------------------------
def load_coverage_contracts(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Contracts keyed by source_id, with file defaults merged in."""
    root = root or REPO_ROOT
    path = root / CONTRACTS_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    defaults = data.get("defaults") or {}
    out: dict[str, dict[str, Any]] = {}
    for entry in data.get("contracts") or []:
        sid = str(entry.get("source_id") or "")
        if sid:
            out[sid] = {**defaults, **entry}
    return out


def _registry_source_ids(root: Path) -> set[str]:
    from moneysweep.runtime.source_registry import load_source_registry

    return {s.get("source_id", "") for s in load_source_registry(root).get("sources", [])}


_ALLOWED_ENTRY_KEYS = frozenset(
    {
        "source_id",
        "contract_version",
        "canonical_grain",
        "geography_scope",
        "period",
        "authoritative_universe_method",
        "authoritative_universe_ref",
        "authoritative_universe_total",
        "uniqueness_key",
        "minimum_coverage_pct",
        "required_field_thresholds",
        "monetary_reconciliation",
        "pagination_required",
        "production_fixtures_forbidden",
        "notes",
    }
)


def validate_contracts(root: Path | None = None) -> list[str]:
    """Structural + cross-registry validation. Returns human-readable errors."""
    root = root or REPO_ROOT
    path = root / CONTRACTS_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return [f"{CONTRACTS_JSON} is missing — regenerate from the YAML"]
    except ValueError as exc:
        return [f"{CONTRACTS_JSON} is not valid JSON: {exc}"]

    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, got {data.get('schema_version')!r}"
        )
    registry_ids = _registry_source_ids(root)
    seen: set[str] = set()
    for i, entry in enumerate(data.get("contracts") or []):
        sid = str(entry.get("source_id") or "")
        label = sid or f"contracts[{i}]"
        unknown = set(entry) - _ALLOWED_ENTRY_KEYS
        if unknown:
            errors.append(f"{label}: unknown keys {sorted(unknown)}")
        if not sid:
            errors.append(f"contracts[{i}]: source_id is required")
        elif sid in seen:
            errors.append(f"{label}: duplicate contract for source_id")
        elif sid not in registry_ids:
            errors.append(f"{label}: source_id not in the live source registry")
        seen.add(sid)

        version = entry.get("contract_version")
        if not isinstance(version, int) or version < 1:
            errors.append(f"{label}: contract_version must be an integer >= 1")
        if entry.get("canonical_grain") not in CANONICAL_GRAINS:
            errors.append(
                f"{label}: canonical_grain {entry.get('canonical_grain')!r} not in vocabulary"
            )
        if entry.get("geography_scope") not in GEOGRAPHY_SCOPES:
            errors.append(
                f"{label}: geography_scope {entry.get('geography_scope')!r} not in vocabulary"
            )

        key = entry.get("uniqueness_key")
        if not isinstance(key, list) or not key or not all(isinstance(k, str) and k for k in key):
            errors.append(f"{label}: uniqueness_key must be a non-empty list of field names")

        method = entry.get("authoritative_universe_method")
        if method is not None and method not in UNIVERSE_METHODS:
            errors.append(f"{label}: authoritative_universe_method {method!r} not in vocabulary")
        min_cov = entry.get("minimum_coverage_pct")
        if min_cov is not None:
            if not isinstance(min_cov, (int, float)) or not 0 < float(min_cov) <= 100:
                errors.append(f"{label}: minimum_coverage_pct must be in (0, 100]")
            if method is None:
                errors.append(
                    f"{label}: minimum_coverage_pct requires an "
                    "authoritative_universe_method (a floor with no denominator "
                    "method is unverifiable by construction)"
                )
        total = entry.get("authoritative_universe_total")
        if total is not None and (not isinstance(total, int) or total < 0):
            errors.append(
                f"{label}: authoritative_universe_total must be a non-negative integer or null"
            )

        thresholds = entry.get("required_field_thresholds") or {}
        if not isinstance(thresholds, dict):
            errors.append(f"{label}: required_field_thresholds must be a mapping")
        else:
            for fld, pct in thresholds.items():
                if not isinstance(pct, (int, float)) or not 0 <= float(pct) <= 100:
                    errors.append(f"{label}: required_field_thresholds[{fld}] must be in [0, 100]")

        monetary = entry.get("monetary_reconciliation")
        if monetary is not None:
            if not isinstance(monetary, dict):
                errors.append(f"{label}: monetary_reconciliation must be a mapping")
            else:
                if not monetary.get("amount_field"):
                    errors.append(f"{label}: monetary_reconciliation.amount_field is required")
                tol = monetary.get("tolerance_pct")
                if not isinstance(tol, (int, float)) or float(tol) <= 0:
                    errors.append(f"{label}: monetary_reconciliation.tolerance_pct must be > 0")
                ref = monetary.get("reference_total")
                if ref is not None and not isinstance(ref, (int, float)):
                    errors.append(
                        f"{label}: monetary_reconciliation.reference_total must be a number or null"
                    )

        period = entry.get("period")
        if period is not None:
            if not isinstance(period, dict):
                errors.append(f"{label}: period must be a mapping")
            elif period.get("period_type") not in PERIOD_TYPES:
                errors.append(
                    f"{label}: period.period_type {period.get('period_type')!r} not in vocabulary"
                )
            else:
                start, end = period.get("start"), period.get("end")
                if isinstance(start, str) and isinstance(end, str) and start > end:
                    errors.append(f"{label}: period.start {start} is after period.end {end}")
    return errors


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate_coverage(
    contract: dict[str, Any] | None,
    *,
    unique_rows: int,
    field_completeness_pct: dict[str, float] | None = None,
) -> tuple[str, list[str]]:
    """Evaluate one source's corpus against its contract.

    ``unique_rows`` is the deduplicated local record count at the contract's
    canonical grain. ``field_completeness_pct`` maps field name → percent
    non-empty (0-100); fields the caller did not measure are treated as
    unverifiable, not as failing.
    """
    if not contract:
        return "uncontracted", ["no coverage contract declared"]
    reasons: list[str] = []
    verifiable = True

    total = contract.get("authoritative_universe_total")
    min_cov = contract.get("minimum_coverage_pct")
    if min_cov is not None:
        if total is None:
            verifiable = False
            reasons.append(
                "authoritative_universe_total not yet measured "
                f"(method: {contract.get('authoritative_universe_method')})"
            )
        elif total == 0:
            verifiable = False
            reasons.append("declared universe total is 0 — contract needs remeasurement")
        else:
            coverage = 100.0 * unique_rows / float(total)
            if coverage < float(min_cov):
                reasons.append(f"coverage {coverage:.1f}% of {total} < floor {float(min_cov):.1f}%")

    thresholds = contract.get("required_field_thresholds") or {}
    measured = field_completeness_pct or {}
    for fld in sorted(thresholds):
        floor = float(thresholds[fld])
        got = measured.get(fld)
        if got is None:
            verifiable = False
            reasons.append(f"field {fld}: completeness not measured (floor {floor:.1f}%)")
        elif float(got) < floor:
            reasons.append(f"field {fld}: completeness {float(got):.1f}% < floor {floor:.1f}%")

    failures = [r for r in reasons if "<" in r]
    if failures:
        return "below_contract", reasons
    if not verifiable:
        return "unverifiable", reasons
    return "meets_contract", reasons


def evaluate_monetary(
    contract: dict[str, Any] | None,
    *,
    observed_total: float | None = None,
) -> str:
    """Monetary reconciliation status for one source."""
    monetary = (contract or {}).get("monetary_reconciliation")
    if not monetary:
        return "not_applicable"
    reference = monetary.get("reference_total")
    if reference is None or observed_total is None:
        return "not_evaluated"
    tolerance = float(monetary.get("tolerance_pct", 1.0))
    if reference == 0:
        return "reconciled" if observed_total == 0 else "variance_exceeds_tolerance"
    variance = abs(observed_total - float(reference)) / abs(float(reference)) * 100.0
    return "reconciled" if variance <= tolerance else "variance_exceeds_tolerance"


def materiality_label(
    rows: int,
    *,
    fixture_detected: bool,
    coverage_status: str,
    freshness_status: str,
) -> str:
    """Materiality label for a corpus.

    The invariant this function carries: ``validated_complete`` is reachable
    ONLY through ``coverage_status == "meets_contract"`` — i.e. through a
    contract with measured universe evidence — never through row counts alone.
    """
    if rows <= 0:
        return "empty"
    if fixture_detected:
        return "fixture"
    if coverage_status == "meets_contract":
        return "complete_stale" if freshness_status == "stale" else "validated_complete"
    if rows >= _TIER_BULK_MIN:
        return "substantial"
    if rows >= _TIER_MODERATE_MIN:
        return "partial"
    return "seed"


def certification_status(
    *,
    materialization_status: str,
    coverage_status: str,
    reconciliation_status: str,
    freshness_status: str,
    fixture_detected: bool,
) -> str:
    """Roll-up production gate for one source."""
    if fixture_detected:
        return "uncertified"
    if (
        materialization_status == "fully_materialized"
        and coverage_status == "meets_contract"
        and reconciliation_status in ("reconciled", "not_applicable")
        and freshness_status != "stale"
    ):
        return "certified_complete"
    if materialization_status == "fully_materialized" and (
        coverage_status in ("uncontracted", "unverifiable")
        or (coverage_status == "meets_contract" and reconciliation_status == "not_evaluated")
    ):
        return "provisional"
    return "uncertified"


def compute_status_vector(
    source: dict[str, Any],
    *,
    path_type: str,
    materialization_status: str,
    local_rows: int,
    contract: dict[str, Any] | None,
    field_completeness_pct: dict[str, float] | None = None,
    observed_monetary_total: float | None = None,
    fixture_detected: bool = False,
    freshness_status: str = "unknown",
    acquisition_status: str | None = None,
) -> StatusVector:
    """Assemble the full status vector for one source.

    Callers supply the signals the existing machinery already computes:
    ``path_type`` from ``build_source_recovery_matrix._classify``,
    ``materialization_status`` from ``gap_analysis_builder._source_status``,
    freshness from the update controller. ``acquisition_status`` may be
    overridden (e.g. from the unresolved-gap ledger); otherwise it is derived.
    """
    sid = str(source.get("source_id") or "")
    wired = _PATH_TYPE_TO_WIRED.get(path_type, "broken")

    if acquisition_status is None:
        if local_rows > 0 or materialization_status == "fully_materialized":
            acquisition_status = (
                "automated" if wired in ("wired_adapter", "wired_producer") else "acquired_ingested"
            )
        elif wired in ("wired_adapter", "wired_producer"):
            acquisition_status = "automated"
        else:
            acquisition_status = "not_acquired"

    coverage, reasons = evaluate_coverage(
        contract,
        unique_rows=local_rows,
        field_completeness_pct=field_completeness_pct,
    )
    reconciliation = evaluate_monetary(contract, observed_total=observed_monetary_total)
    label = materiality_label(
        local_rows,
        fixture_detected=fixture_detected,
        coverage_status=coverage,
        freshness_status=freshness_status,
    )
    certification = certification_status(
        materialization_status=materialization_status,
        coverage_status=coverage,
        reconciliation_status=reconciliation,
        freshness_status=freshness_status,
        fixture_detected=fixture_detected,
    )
    return StatusVector(
        source_id=sid,
        wired_status=wired,
        acquisition_status=acquisition_status,
        materialization_status=materialization_status,
        coverage_status=coverage,
        reconciliation_status=reconciliation,
        freshness_status=freshness_status,
        certification_status=certification,
        materiality_label=label,
        has_contract=contract is not None,
        coverage_reasons=tuple(reasons),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    errors = validate_contracts(Path(args.root))
    contracts = load_coverage_contracts(Path(args.root))
    if args.json:
        print(
            json.dumps(
                {"ok": not errors, "contracts": len(contracts), "errors": errors},
                indent=2,
            )
        )
    else:
        for e in errors:
            print(f"CONTRACT ERROR: {e}", file=sys.stderr)
        print(f"coverage contracts: {len(contracts)} loaded, {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
