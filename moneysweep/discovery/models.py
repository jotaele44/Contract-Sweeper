"""Evidence-preserving Stage-1 discovery graph models.

These models intentionally keep RAW, NORMALIZED, and canonical-candidate names
separate. Discovery/search results are candidates, not identity proof. Every
relationship and candidate carries source-addressable evidence references.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from moneysweep.entity_resolution.keys import Identifier


class IdentityState(str, Enum):
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class CertificationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    PROVISIONAL = "PROVISIONAL"
    AUDIT_ONLY = "AUDIT_ONLY"
    NONCANONICAL = "NONCANONICAL"
    CANDIDATE_NOT_IDENTITY = "CANDIDATE_NOT_IDENTITY"
    UNRESOLVED = "UNRESOLVED"
    SUPERSEDED = "SUPERSEDED"


class Cardinality(str, Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
    MANY_TO_MANY = "N:N"
    ZERO_TO_ONE = "0:1"
    UNRESOLVED = "UNRESOLVED"


class ContradictionKind(str, Enum):
    BYTE = "BYTE"
    SCHEMA = "SCHEMA"
    GEOMETRY = "GEOMETRY"
    NAME = "NAME"
    COUNT = "COUNT"
    CLASS = "CLASS"
    IDENTITY = "IDENTITY"
    TIME = "TIME"
    SCOPE = "SCOPE"


@dataclass(frozen=True)
class SourceEvidence:
    evidence_ref: str
    source_id: str
    retrieved_at: str
    source_record_id: str | None = None
    url: str | None = None
    sha256: str | None = None
    assertion_type: str = "explicit"


@dataclass(frozen=True)
class EntityCandidate:
    candidate_id: str
    entity_type: str
    raw_names: tuple[str, ...]
    normalized_names: tuple[str, ...]
    identifiers: tuple[Identifier, ...]
    identity_state: IdentityState
    certification_state: CertificationState
    evidence_refs: tuple[str, ...]
    canonical_candidate: str | None = None
    addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.raw_names:
            raise ValueError("candidate must preserve at least one raw name")
        if not self.evidence_refs:
            raise ValueError("candidate must carry at least one evidence reference")
        if self.identity_state is IdentityState.CONFIRMED and (
            self.certification_state is CertificationState.CANDIDATE_NOT_IDENTITY
        ):
            raise ValueError("candidate-not-identity evidence cannot be CONFIRMED")


@dataclass(frozen=True)
class RelationshipAssertion:
    left_candidate_id: str
    predicate: str
    right_candidate_id: str
    cardinality: Cardinality
    evidence_refs: tuple[str, ...]
    valid_from: str | None = None
    valid_to: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_refs:
            raise ValueError("relationship requires evidence")


@dataclass(frozen=True)
class Contradiction:
    kind: ContradictionKind
    candidate_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    state: str = "OPEN"
    note: str | None = None


@dataclass(frozen=True)
class DiscoveryStagePacket:
    case_id: str
    created_at: str
    subject_seeds: tuple[str, ...]
    candidates: tuple[EntityCandidate, ...]
    relationships: tuple[RelationshipAssertion, ...]
    contradictions: tuple[Contradiction, ...]
    explicit_exclusions: tuple[str, ...]
    source_manifest: tuple[SourceEvidence, ...]
    schema_version: str = field(default="discovery_stage_packet_v1", init=False)

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id is required")
        if not self.subject_seeds:
            raise ValueError("at least one subject seed is required")

        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate candidate_id")

        evidence_refs = [evidence.evidence_ref for evidence in self.source_manifest]
        if len(evidence_refs) != len(set(evidence_refs)):
            raise ValueError("duplicate evidence_ref")
        evidence_set = set(evidence_refs)

        for candidate in self.candidates:
            missing = set(candidate.evidence_refs) - evidence_set
            if missing:
                raise ValueError(f"candidate has unknown evidence refs: {sorted(missing)}")

        candidate_set = set(candidate_ids)
        for relationship in self.relationships:
            if relationship.left_candidate_id not in candidate_set:
                raise ValueError("relationship left endpoint is not a candidate")
            if relationship.right_candidate_id not in candidate_set:
                raise ValueError("relationship right endpoint is not a candidate")
            missing = set(relationship.evidence_refs) - evidence_set
            if missing:
                raise ValueError(f"relationship has unknown evidence refs: {sorted(missing)}")

    def stage2_subject_ids(self) -> tuple[str, ...]:
        """Return only adjudicated subjects eligible for ordinary Stage-2 corpus use."""
        return tuple(
            candidate.candidate_id
            for candidate in self.candidates
            if candidate.identity_state in {IdentityState.CONFIRMED, IdentityState.PROBABLE}
            and candidate.certification_state
            not in {CertificationState.CANDIDATE_NOT_IDENTITY, CertificationState.UNRESOLVED}
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible representation."""
        payload = asdict(self)
        payload["schema_version"] = self.schema_version
        return payload
