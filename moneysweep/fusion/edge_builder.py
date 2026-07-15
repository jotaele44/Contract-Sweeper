"""Construct relationship edges with the fusion safety rules enforced.

``build_edge`` is the only sanctioned way to create a :class:`RelationshipEdge`.
It rejects:

* a missing/empty ``source_record_id`` (the evidence-required rule),
* any predicate outside the approved whitelist (blocks conclusory verbs such as
  ``INFLUENCED``),
* an invalid evidence tier.

Edge ids are deterministic (``moneysweep.runtime.canonical_ids.edge_id``).
"""

from __future__ import annotations

from moneysweep.fusion.models import (
    APPROVED_PREDICATES,
    AssertionType,
    ContradictionStatus,
    PublicationStatus,
    RelationshipEdge,
)
from moneysweep.runtime import canonical_ids

__all__ = ["EdgeValidationError", "build_edge"]


class EdgeValidationError(ValueError):
    """Raised when an edge would violate a fusion safety rule."""


def build_edge(
    *,
    subject_entity_id: str,
    predicate: str,
    object_entity_id: str,
    source_record_id: str,
    evidence_tier: str = "T2",
    assertion_type: AssertionType | str = AssertionType.EXPLICIT,
    confidence: float = 0.0,
    valid_from: str | None = None,
    valid_to: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    publication_status: PublicationStatus | str = PublicationStatus.INTERNAL,
    contradiction_status: ContradictionStatus | str = ContradictionStatus.NONE,
) -> RelationshipEdge:
    """Build a validated :class:`RelationshipEdge`.

    Raises :class:`EdgeValidationError` if any safety rule is violated.
    """
    if not source_record_id:
        raise EdgeValidationError(
            "every edge requires a source_record_id (evidence-required rule)"
        )
    if predicate not in APPROVED_PREDICATES:
        raise EdgeValidationError(
            f"predicate {predicate!r} is not in the approved whitelist; "
            "conclusory predicates (e.g. INFLUENCED) are prohibited"
        )

    assertion = AssertionType(assertion_type) if not isinstance(assertion_type, AssertionType) else assertion_type
    pub = (
        PublicationStatus(publication_status)
        if not isinstance(publication_status, PublicationStatus)
        else publication_status
    )
    contra = (
        ContradictionStatus(contradiction_status)
        if not isinstance(contradiction_status, ContradictionStatus)
        else contradiction_status
    )

    edge_id = canonical_ids.edge_id(subject_entity_id, predicate, object_entity_id)

    try:
        return RelationshipEdge(
            edge_id=edge_id,
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_entity_id=object_entity_id,
            source_record_id=source_record_id,
            evidence_tier=evidence_tier,
            assertion_type=assertion,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            amount=amount,
            currency=currency,
            publication_status=pub,
            contradiction_status=contra,
        )
    except ValueError as exc:  # tier/predicate/source re-validated in __post_init__
        raise EdgeValidationError(str(exc)) from exc
