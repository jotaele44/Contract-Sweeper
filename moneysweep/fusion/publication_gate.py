"""Publication gate.

Decides whether a relationship edge may be published. Enforces the mandatory
controls from ``docs/publication_and_correction_policy.md`` and
``docs/nonprofit_layer_legal_scope.md``:

* evidence-required — an edge without a ``source_record_id`` can never be public;
* review — reaching ``public`` requires fact-check and publication approval;
* inferred edges are never published automatically (they require human review);
* no guilt-by-association — an edge whose only basis is shared proximity/association
  is rejected;
* PII minimization — an edge flagged as carrying non-minimized PII is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from moneysweep.fusion.models import AssertionType, PublicationStatus, RelationshipEdge

__all__ = ["PublicationGateError", "PublicationDecision", "check_publishable"]


class PublicationGateError(ValueError):
    """Raised (by strict callers) when an edge fails the publication gate."""


@dataclass(frozen=True)
class PublicationDecision:
    publishable: bool
    reasons: tuple[str, ...]

    def raise_if_blocked(self) -> None:
        if not self.publishable:
            raise PublicationGateError("; ".join(self.reasons))


def check_publishable(
    edge: RelationshipEdge,
    *,
    fact_checked: bool = False,
    publication_approved: bool = False,
    guilt_by_association_only: bool = False,
    pii_minimized: bool = True,
) -> PublicationDecision:
    """Return a :class:`PublicationDecision` for ``edge``.

    ``fact_checked`` / ``publication_approved`` come from the review pipeline
    (``schemas/publication_review.schema.json``). ``guilt_by_association_only``
    marks an edge whose sole basis is shared association — always rejected.
    """
    reasons: list[str] = []

    if not edge.source_record_id:
        reasons.append("edge has no source_record_id (evidence-required rule)")

    if edge.assertion_type is AssertionType.INFERRED:
        reasons.append(
            "inferred edges are never published automatically; human review required"
        )

    if guilt_by_association_only:
        reasons.append(
            "edge basis is shared association only; guilt-by-association is prohibited"
        )

    if not pii_minimized:
        reasons.append("edge carries non-minimized PII")

    # To reach public, the review pipeline must have completed.
    if edge.publication_status is PublicationStatus.PUBLIC:
        if not fact_checked:
            reasons.append("public edge requires completed fact_check")
        if not publication_approved:
            reasons.append("public edge requires publication approval")
    else:
        # Anything not already approved through the pipeline is not publishable.
        if not (fact_checked and publication_approved):
            reasons.append(
                "edge has not passed fact_check + publication approval"
            )

    return PublicationDecision(publishable=not reasons, reasons=tuple(reasons))
