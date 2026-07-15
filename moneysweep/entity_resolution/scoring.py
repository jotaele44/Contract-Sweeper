"""Match scoring for entity resolution.

Combines the documented match features into a single confidence in ``[0, 1]``.

Safety invariant: **name similarity alone must never reach the auto-merge band.**
When the only positive evidence is name / registered-alias similarity, the score
is capped strictly below the auto-merge threshold (``NAME_ONLY_CAP`` < 0.95), so a
name-only candidate can at most become a *suggested* merge requiring human review.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MatchFeatures", "score_match", "NAME_ONLY_CAP"]

# Ceiling applied when name/alias similarity is the *only* positive signal.
# Sits below the resolver's auto_merge threshold (0.95) by design.
NAME_ONLY_CAP = 0.90

# Feature weights. Non-name evidence is what lets a match cross into the
# auto-merge band; name evidence on its own is capped (see NAME_ONLY_CAP).
_WEIGHTS = {
    "exact_identifier": 0.60,
    "address_similarity": 0.18,
    "telephone_match": 0.12,
    "officer_or_authorized_person_overlap": 0.18,
    "parent_subsidiary_relationship": 0.12,
    "contract_number_context": 0.12,
    "lobby_client_context": 0.12,
    "temporal_overlap": 0.06,
    "municipality_and_project_context": 0.12,
    # Name evidence. Weighted so a strong name+alias match reaches the
    # suggested-merge band (human review) but is still capped below auto-merge.
    "normalized_legal_name": 0.55,
    "registered_alias": 0.35,
}

_NAME_FEATURES = frozenset({"normalized_legal_name", "registered_alias"})


@dataclass(frozen=True)
class MatchFeatures:
    """Evidence for a candidate match between two entity records.

    Float features are similarities in ``[0, 1]``; boolean features are presence
    flags. All default to "no evidence".
    """

    exact_identifier: bool = False
    normalized_legal_name: float = 0.0
    registered_alias: bool = False
    address_similarity: float = 0.0
    telephone_match: bool = False
    officer_or_authorized_person_overlap: float = 0.0
    parent_subsidiary_relationship: bool = False
    contract_number_context: bool = False
    lobby_client_context: bool = False
    temporal_overlap: bool = False
    municipality_and_project_context: bool = False

    def _contributions(self) -> dict[str, float]:
        raw = {
            "exact_identifier": 1.0 if self.exact_identifier else 0.0,
            "normalized_legal_name": _clamp01(self.normalized_legal_name),
            "registered_alias": 1.0 if self.registered_alias else 0.0,
            "address_similarity": _clamp01(self.address_similarity),
            "telephone_match": 1.0 if self.telephone_match else 0.0,
            "officer_or_authorized_person_overlap": _clamp01(
                self.officer_or_authorized_person_overlap
            ),
            "parent_subsidiary_relationship": 1.0 if self.parent_subsidiary_relationship else 0.0,
            "contract_number_context": 1.0 if self.contract_number_context else 0.0,
            "lobby_client_context": 1.0 if self.lobby_client_context else 0.0,
            "temporal_overlap": 1.0 if self.temporal_overlap else 0.0,
            "municipality_and_project_context": 1.0
            if self.municipality_and_project_context
            else 0.0,
        }
        return {k: v * _WEIGHTS[k] for k, v in raw.items()}

    def has_non_name_evidence(self) -> bool:
        """True if any positive evidence beyond name/alias similarity is present."""
        contribs = self._contributions()
        return any(v > 0.0 for k, v in contribs.items() if k not in _NAME_FEATURES)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x)


def score_match(features: MatchFeatures) -> float:
    """Return a match confidence in ``[0, 1]`` for ``features``.

    If the only positive evidence is name/alias similarity, the result is capped
    at ``NAME_ONLY_CAP`` so it cannot reach the auto-merge band.
    """
    score = _clamp01(sum(features._contributions().values()))
    if not features.has_non_name_evidence():
        score = min(score, NAME_ONLY_CAP)
    return score
