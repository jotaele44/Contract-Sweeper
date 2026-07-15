"""Fusion data models.

Dataclasses for canonical entities, evidence, relationship edges, and cross-layer
observations. The predicate whitelist is fixed and deliberately excludes any
conclusory verb (INFLUENCED, CAPTURED, ...). Every edge must carry a
``source_record_id`` and an ``assertion_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "APPROVED_PREDICATES",
    "EVIDENCE_TIERS",
    "AssertionType",
    "PublicationStatus",
    "ContradictionStatus",
    "CanonicalEntity",
    "EvidenceRecord",
    "RelationshipEdge",
    "FusionObservation",
]

# Fixed predicate whitelist (config/domains/fusion.yml). No conclusory verbs.
APPROVED_PREDICATES: frozenset[str] = frozenset(
    {
        "AWARDED_CONTRACT_TO",
        "AMENDS_CONTRACT",
        "TRANSFERRED_FUNDS_TO",
        "RECEIVED_GRANT_FROM",
        "SUBCONTRACTED_TO",
        "LOBBIED_FOR",
        "AUTHORIZED_PERSON_FOR",
        "EMPLOYED_BY",
        "BOARD_MEMBER_OF",
        "REGISTERED_AS",
        "OWNS",
        "CONTROLS",
        "AFFILIATED_WITH",
        "OPERATES_PROJECT",
        "LOCATED_AT",
        "SERVES_MUNICIPALITY",
        "FUNDED_PROJECT",
        "INSPECTED_ASSET",
        "REPORTED_EXPENDITURE_FOR",
        "PREPARED_REPORT_FOR",
    }
)

EVIDENCE_TIERS = ("T1", "T2", "T3", "T4")


class AssertionType(str, Enum):
    EXPLICIT = "explicit"
    DERIVED = "derived"
    INFERRED = "inferred"


class PublicationStatus(str, Enum):
    INTERNAL = "internal"
    REVIEW = "review"
    PUBLIC = "public"


class ContradictionStatus(str, Enum):
    NONE = "none"
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class CanonicalEntity:
    """A resolved entity, present in one or more domains."""

    entity_id: str
    canonical_name: str
    entity_type: str = "organization"
    domains_present: tuple[str, ...] = field(default_factory=tuple)
    jurisdiction: str | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    """A source-backed claim. Mirrors schemas/canonical_v1/evidence.schema.json."""

    evidence_id: str
    source_type: str
    source_name: str
    claim: str
    evidence_tier: str = "T2"
    source_path_or_url: str | None = None
    page_or_line_ref: str | None = None
    review_status: str = "pending"

    def __post_init__(self) -> None:
        if self.evidence_tier not in EVIDENCE_TIERS:
            raise ValueError(f"invalid evidence_tier: {self.evidence_tier!r}")


@dataclass(frozen=True)
class RelationshipEdge:
    """A typed, evidence-backed edge between two canonical entities.

    Constructed via ``edge_builder.build_edge`` (which enforces the invariants);
    the dataclass also validates predicate, tier, and source on init so a
    hand-built edge cannot bypass the rules.
    """

    edge_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    source_record_id: str
    evidence_tier: str = "T2"
    assertion_type: AssertionType = AssertionType.EXPLICIT
    confidence: float = 0.0
    valid_from: str | None = None
    valid_to: str | None = None
    amount: float | None = None
    currency: str | None = None
    publication_status: PublicationStatus = PublicationStatus.INTERNAL
    contradiction_status: ContradictionStatus = ContradictionStatus.NONE

    def __post_init__(self) -> None:
        if self.predicate not in APPROVED_PREDICATES:
            raise ValueError(f"predicate not in approved whitelist: {self.predicate!r}")
        if self.evidence_tier not in EVIDENCE_TIERS:
            raise ValueError(f"invalid evidence_tier: {self.evidence_tier!r}")
        if not self.source_record_id:
            raise ValueError("every edge requires a non-empty source_record_id")


@dataclass(frozen=True)
class FusionObservation:
    """A documented, non-conclusory cross-layer observation.

    ``influence_conclusion`` is always ``None`` by construction; influence is an
    analytical hypothesis, never a fusion output.
    """

    observation_id: str
    canonical_entity_id: str
    domains_present: tuple[str, ...]
    documented_edge_ids: tuple[str, ...] = field(default_factory=tuple)
    documented_predicates: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    contradiction_status: ContradictionStatus = ContradictionStatus.NONE
    publication_status: PublicationStatus = PublicationStatus.INTERNAL

    @property
    def influence_conclusion(self) -> None:
        return None
