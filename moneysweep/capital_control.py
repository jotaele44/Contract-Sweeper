"""Capital-and-control domain primitives for MoneySweep.

The module deliberately separates a reported legal holder from an investor family
and ultimate parent.  Normalized names are discovery aids only; they are never
accepted as identity proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable


class PositionClass(StrEnum):
    BENEFICIAL_OWNER = "BENEFICIAL_OWNER"
    INVESTMENT_ADVISER = "INVESTMENT_ADVISER"
    FUND = "FUND"
    NOMINEE = "NOMINEE"
    CUSTODIAN = "CUSTODIAN"
    TRUSTEE = "TRUSTEE"
    PENSION = "PENSION"
    INSIDER = "INSIDER"
    CORPORATE_PARENT = "CORPORATE_PARENT"
    GOVERNMENT = "GOVERNMENT"
    SOVEREIGN_FUND = "SOVEREIGN_FUND"
    UNKNOWN = "UNKNOWN"


class RelationType(StrEnum):
    BENEFICIAL_OWNERSHIP = "BENEFICIAL_OWNERSHIP"
    INVESTMENT_DISCRETION = "INVESTMENT_DISCRETION"
    VOTING_AUTHORITY = "VOTING_AUTHORITY"
    DISPOSITIVE_AUTHORITY = "DISPOSITIVE_AUTHORITY"
    DIRECT_EQUITY = "DIRECT_EQUITY"
    INDIRECT_EQUITY = "INDIRECT_EQUITY"
    FUND_HOLDING = "FUND_HOLDING"
    NOMINEE = "NOMINEE"
    CUSTODY = "CUSTODY"
    TRUST = "TRUST"
    INSIDER = "INSIDER"
    PARENT_CONTROL = "PARENT_CONTROL"
    DEBT = "DEBT"
    LENDING = "LENDING"
    BONDHOLDING = "BONDHOLDING"
    GUARANTEE = "GUARANTEE"
    LIEN = "LIEN"
    MORTGAGE = "MORTGAGE"
    COLLATERAL = "COLLATERAL"
    JV_INTEREST = "JV_INTEREST"
    PRIVATE_EQUITY_SPONSORSHIP = "PRIVATE_EQUITY_SPONSORSHIP"
    UNKNOWN = "UNKNOWN"


class IdentityStatus(StrEnum):
    CERTIFIED = "CERTIFIED"
    PROVISIONAL = "PROVISIONAL"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class HoldingObservation:
    observation_id: str
    issuer_id: str
    security_id: str
    holder_legal_entity_id: str
    holder_reported_name_raw: str
    as_of_date: date
    report_date: date
    source_id: str
    source_document_id: str
    position_class: PositionClass
    relation_type: RelationType
    identity_status: IdentityStatus
    investor_family_id: str | None = None
    ultimate_parent_id: str | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    percent_class: Decimal | None = None
    percent_issuer: Decimal | None = None
    voting_percent: Decimal | None = None
    sole_voting_power: Decimal | None = None
    shared_voting_power: Decimal | None = None
    sole_dispositive_power: Decimal | None = None
    shared_dispositive_power: Decimal | None = None
    amendment_sequence: int = 0
    supersedes_observation_id: str | None = None

    @property
    def position_key(self) -> tuple[str, str, str, date, PositionClass, RelationType]:
        return (
            self.issuer_id,
            self.security_id,
            self.holder_legal_entity_id,
            self.as_of_date,
            self.position_class,
            self.relation_type,
        )


def decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None


def validate_observation(row: HoldingObservation) -> list[str]:
    """Return fail-closed invariant violations for one observation."""
    errors: list[str] = []
    required = {
        "observation_id": row.observation_id,
        "issuer_id": row.issuer_id,
        "security_id": row.security_id,
        "holder_legal_entity_id": row.holder_legal_entity_id,
        "holder_reported_name_raw": row.holder_reported_name_raw,
        "source_id": row.source_id,
        "source_document_id": row.source_document_id,
    }
    errors.extend(f"missing {name}" for name, value in required.items() if not str(value).strip())
    if row.report_date < row.as_of_date:
        errors.append("report_date precedes as_of_date")
    if row.amendment_sequence < 0:
        errors.append("amendment_sequence must be >= 0")
    for name in ("percent_class", "percent_issuer", "voting_percent"):
        value = getattr(row, name)
        if value is not None and (value < 0 or value > 100):
            errors.append(f"{name} outside 0..100")
    if row.position_class == PositionClass.INVESTMENT_ADVISER and row.relation_type == RelationType.DIRECT_EQUITY:
        errors.append("investment adviser cannot imply direct equity without a distinct ownership observation")
    return errors


def effective_observations(rows: Iterable[HoldingObservation]) -> list[HoldingObservation]:
    """Resolve amendments deterministically without multiplying a position.

    Highest amendment sequence wins within a position key.  Equal top sequence is
    unresolved unless it is the exact same observation id, so tied records are
    intentionally omitted rather than heuristically selected.
    """
    grouped: dict[tuple, list[HoldingObservation]] = {}
    for row in rows:
        grouped.setdefault(row.position_key, []).append(row)
    effective: list[HoldingObservation] = []
    for key in sorted(grouped, key=str):
        candidates = grouped[key]
        top_sequence = max(row.amendment_sequence for row in candidates)
        top = [row for row in candidates if row.amendment_sequence == top_sequence]
        ids = {row.observation_id for row in top}
        if len(ids) != 1:
            continue
        effective.append(sorted(top, key=lambda row: row.observation_id)[0])
    return effective


def holder_set(
    rows: Iterable[HoldingObservation],
    *,
    issuer_id: str,
    identity_level: str = "legal_holder",
) -> set[str]:
    if identity_level not in {"legal_holder", "investor_family", "ultimate_parent"}:
        raise ValueError(f"unsupported identity_level: {identity_level}")
    values: set[str] = set()
    for row in effective_observations(rows):
        if row.issuer_id != issuer_id:
            continue
        value = {
            "legal_holder": row.holder_legal_entity_id,
            "investor_family": row.investor_family_id,
            "ultimate_parent": row.ultimate_parent_id,
        }[identity_level]
        if value:
            values.add(value)
    return values


def compare_issuers(
    rows: Iterable[HoldingObservation],
    issuer_a: str,
    issuer_b: str,
    *,
    identity_level: str = "legal_holder",
) -> dict[str, list[str]]:
    """Compute complete set equivalence diagnostics for two issuer universes."""
    frozen = list(rows)
    a = holder_set(frozen, issuer_id=issuer_a, identity_level=identity_level)
    b = holder_set(frozen, issuer_id=issuer_b, identity_level=identity_level)
    return {
        "intersection": sorted(a & b),
        "a_only": sorted(a - b),
        "b_only": sorted(b - a),
        "union": sorted(a | b),
        "symmetric_difference": sorted(a ^ b),
    }
