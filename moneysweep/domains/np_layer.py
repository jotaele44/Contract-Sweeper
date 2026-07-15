"""NP_LAYER — nonprofit / public-interest domain descriptor.

Governs intake, review, and publication of publicly available records. Publication
eligibility here is intentionally conservative: a record is publication-eligible only
when it is public-access and its review pipeline has been satisfied. See
``docs/nonprofit_layer_legal_scope.md`` and
``docs/publication_and_correction_policy.md``.
"""

from __future__ import annotations

from moneysweep.domains._descriptor import DomainDescriptor

# Ordered pipeline; a record may only advance one state at a time.
REVIEW_STATES = ("internal", "legal_review", "fact_check", "public")

NP_LAYER = DomainDescriptor(
    domain="np_layer",
    title="Nonprofit / Public-Interest Layer",
    record_families=(
        "public_record_request",
        "public_record_response",
        "public_record_denial",
        "publication_package",
        "correction_notice",
    ),
    access_class_default="public",
)


def is_publication_eligible(*, access_class: str, review_status: str) -> bool:
    """A record is publication-eligible only if public and fact-checked/approved.

    Restricted or internal access-class records are never publication-eligible,
    regardless of review state.
    """
    if access_class != "public":
        return False
    return review_status in ("fact_check", "public")


def next_review_state(current: str) -> str | None:
    """Return the next state in the pipeline, or ``None`` if already ``public``."""
    if current not in REVIEW_STATES:
        raise ValueError(f"unknown review state: {current!r}")
    idx = REVIEW_STATES.index(current)
    if idx + 1 >= len(REVIEW_STATES):
        return None
    return REVIEW_STATES[idx + 1]
