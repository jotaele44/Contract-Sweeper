"""Resolution decisions from match scores + identifier evidence.

Thresholds mirror ``config/domains/fusion.yml``:

    >= 0.95   auto_merge            (ONLY with a unique authoritative id)
    0.85-0.949 suggested_merge      (human review required)
    0.65-0.849 possible_relationship (do NOT merge)
    < 0.65    separate

Non-merged candidates are preserved as suggested merges or possible relationships;
they are never deleted. A high score alone can never auto-merge — an auto-merge
additionally requires a unique authoritative identifier held in common.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from moneysweep.entity_resolution.keys import Identifier, has_unique_authoritative_id
from moneysweep.entity_resolution.scoring import MatchFeatures, score_match

__all__ = [
    "MergeDecision",
    "ResolutionResult",
    "resolve",
    "AUTO_MERGE",
    "SUGGESTED_MERGE",
    "POSSIBLE_RELATIONSHIP",
]

AUTO_MERGE = 0.95
SUGGESTED_MERGE = 0.85
POSSIBLE_RELATIONSHIP = 0.65


class MergeDecision(str, Enum):
    AUTO_MERGE = "auto_merge"
    SUGGESTED_MERGE = "suggested_merge"
    POSSIBLE_RELATIONSHIP = "possible_relationship"
    SEPARATE = "separate"


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of comparing two entity records."""

    decision: MergeDecision
    score: float
    has_unique_authoritative_id: bool
    reason: str

    @property
    def merged(self) -> bool:
        return self.decision is MergeDecision.AUTO_MERGE


def resolve(
    features: MatchFeatures,
    left_identifiers: list[Identifier] | None = None,
    right_identifiers: list[Identifier] | None = None,
) -> ResolutionResult:
    """Decide how two entity records relate.

    ``left_identifiers`` / ``right_identifiers`` are used only to gate auto-merge:
    a score in the auto-merge band is downgraded to a *suggested* merge unless the
    two records share a unique authoritative identifier.
    """
    score = score_match(features)
    left_identifiers = left_identifiers or []
    right_identifiers = right_identifiers or []
    unique_auth = has_unique_authoritative_id(left_identifiers, right_identifiers)

    if score >= AUTO_MERGE:
        if unique_auth:
            return ResolutionResult(
                MergeDecision.AUTO_MERGE,
                score,
                True,
                "score in auto-merge band and a unique authoritative id is shared",
            )
        # High score but no authoritative anchor -> never auto-merge.
        return ResolutionResult(
            MergeDecision.SUGGESTED_MERGE,
            score,
            False,
            "score in auto-merge band but no unique authoritative id; human review required",
        )
    if score >= SUGGESTED_MERGE:
        return ResolutionResult(
            MergeDecision.SUGGESTED_MERGE,
            score,
            unique_auth,
            "suggested merge; human review required",
        )
    if score >= POSSIBLE_RELATIONSHIP:
        return ResolutionResult(
            MergeDecision.POSSIBLE_RELATIONSHIP,
            score,
            unique_auth,
            "possible relationship; do not merge",
        )
    return ResolutionResult(
        MergeDecision.SEPARATE,
        score,
        unique_auth,
        "below possible-relationship threshold; keep separate",
    )
