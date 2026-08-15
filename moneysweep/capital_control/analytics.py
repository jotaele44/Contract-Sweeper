from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import HoldingObservation, InvestorIdentity
from .supersession import apply_supersession


@dataclass(frozen=True)
class PairwiseSetComparison:
    intersection: frozenset[str]
    a_only: frozenset[str]
    b_only: frozenset[str]
    union: frozenset[str]
    symmetric_difference: frozenset[str]


def compare_sets(a: Iterable[str], b: Iterable[str]) -> PairwiseSetComparison:
    left = frozenset(a)
    right = frozenset(b)
    return PairwiseSetComparison(
        intersection=left & right,
        a_only=left - right,
        b_only=right - left,
        union=left | right,
        symmetric_difference=left ^ right,
    )


def current_positions(observations: Iterable[HoldingObservation]) -> tuple[HoldingObservation, ...]:
    active = apply_supersession(observations).active
    newest: dict[tuple[str, str, str | None, str | None, str], HoldingObservation] = {}
    for row in active:
        key = (
            row.holder_id,
            row.issuer_id,
            row.security_id,
            row.security_class_raw,
            row.position_class,
        )
        incumbent = newest.get(key)
        if incumbent is None:
            newest[key] = row
            continue
        candidate_rank = (row.as_of_date, row.report_date)
        incumbent_rank = (incumbent.as_of_date, incumbent.report_date)
        if candidate_rank > incumbent_rank:
            newest[key] = row
        elif candidate_rank == incumbent_rank and row.observation_id != incumbent.observation_id:
            raise ValueError("tied current observations require explicit adjudication")
    return tuple(
        sorted(
            newest.values(),
            key=lambda row: (row.issuer_id, row.holder_id, row.position_class, row.observation_id),
        )
    )


def rollup_positions(
    observations: Iterable[HoldingObservation],
    identities: Mapping[str, InvestorIdentity],
    level: str,
) -> Mapping[str, tuple[HoldingObservation, ...]]:
    if level not in {"LEGAL_HOLDER", "INVESTOR_FAMILY", "ULTIMATE_PARENT"}:
        raise ValueError("unsupported rollup level")
    grouped: dict[str, list[HoldingObservation]] = {}
    for row in current_positions(observations):
        identity = identities.get(row.holder_id)
        if identity is None:
            key = row.holder_id
        elif level == "LEGAL_HOLDER":
            key = identity.legal_entity_id or identity.investor_id
        elif level == "INVESTOR_FAMILY":
            key = identity.investor_family_id or identity.legal_entity_id or identity.investor_id
        else:
            key = (
                identity.ultimate_parent_id
                or identity.investor_family_id
                or identity.legal_entity_id
                or identity.investor_id
            )
        grouped.setdefault(key, []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}
