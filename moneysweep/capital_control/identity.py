from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import PASS_BINDING_BASES


EVIDENCE_PRIORITY = {
    "STABLE_ID": 700,
    "AUTHORITATIVE_BINDING": 600,
    "AUTHORITATIVE_ALIAS_WITH_CORROBORATION": 400,
    "HISTORICAL_CONTINUITY_WITH_CORROBORATION": 300,
    "HEURISTIC_DISCOVERY_ONLY": 100,
    "NONE": 0,
}


@dataclass(frozen=True)
class IdentityCandidate:
    candidate_id: str
    binding_basis: str
    evidence_value: str


@dataclass(frozen=True)
class IdentityResolution:
    status: str
    selected_id: str | None
    candidates: tuple[IdentityCandidate, ...]
    reason: str


def resolve_identity_candidates(candidates: Iterable[IdentityCandidate]) -> IdentityResolution:
    preserved = tuple(candidates)
    if not preserved:
        return IdentityResolution("UNRESOLVED", None, preserved, "no candidates")

    ranked = sorted(
        preserved,
        key=lambda candidate: EVIDENCE_PRIORITY.get(candidate.binding_basis, -1),
        reverse=True,
    )
    top_score = EVIDENCE_PRIORITY.get(ranked[0].binding_basis, -1)
    top = tuple(
        candidate
        for candidate in ranked
        if EVIDENCE_PRIORITY.get(candidate.binding_basis, -1) == top_score
    )
    distinct_top_ids = {candidate.candidate_id for candidate in top}
    if len(distinct_top_ids) != 1:
        return IdentityResolution("UNRESOLVED", None, preserved, "tied top evidence")

    selected = top[0]
    if selected.binding_basis not in PASS_BINDING_BASES:
        return IdentityResolution(
            "CANDIDATE_NOT_IDENTITY",
            None,
            preserved,
            "best evidence is discovery-only or otherwise non-binding",
        )
    return IdentityResolution("PASS", selected.candidate_id, preserved, "binding evidence selected")
