"""Entity resolution: normalization, identifier keys, scoring, and the resolver.

Deterministic and dependency-light. Reuses the repo's existing name-normalization
(``moneysweep.runtime.name_normalization``) and deterministic-id
(``moneysweep.runtime.canonical_ids``) machinery rather than re-implementing them.
"""

from __future__ import annotations

from moneysweep.entity_resolution.keys import (
    IDENTIFIER_HIERARCHY,
    Identifier,
    best_identifier,
    has_unique_authoritative_id,
    internal_canonical_id,
)
from moneysweep.entity_resolution.resolver import (
    MergeDecision,
    ResolutionResult,
    resolve,
)
from moneysweep.entity_resolution.scoring import MatchFeatures, score_match

__all__ = [
    "IDENTIFIER_HIERARCHY",
    "Identifier",
    "best_identifier",
    "has_unique_authoritative_id",
    "internal_canonical_id",
    "MatchFeatures",
    "score_match",
    "MergeDecision",
    "ResolutionResult",
    "resolve",
]
