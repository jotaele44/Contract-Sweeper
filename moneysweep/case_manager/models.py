"""UI-agnostic Case Manager domain records.

Records are immutable dataclasses. Persistence layers may append new versions/events but
must not rewrite prior audit events or canonical evidence rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Visibility = Literal["public", "internal", "restricted"]
ReviewStatus = Literal["pending", "accepted", "rejected"]
EvidenceRelation = Literal["support", "contradict", "qualify", "supersede"]

@dataclass(frozen=True, slots=True)
class Case:
    case_id: str; title: str; case_type: str; status: str; scope: str
    priority: str = "normal"; owner: str | None = None; visibility: Visibility = "internal"
    opened_at: str | None = None; closed_at: str | None = None

@dataclass(frozen=True, slots=True)
class CaseEvidence:
    case_evidence_id: str; case_id: str; evidence_id: str; role: str
    relevance: str = "material"; review_status: ReviewStatus = "pending"
    visibility: Visibility = "internal"; analyst_note: str | None = None

@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str; case_id: str; statement: str; claim_type: str; status: str
    confidence: float; language_tier: Literal["observed", "linked", "inferred", "blocked"]
    visibility: Visibility = "internal"

@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    claim_evidence_id: str; claim_id: str; evidence_id: str; relation: EvidenceRelation
    rationale: str | None = None

@dataclass(frozen=True, slots=True)
class CaseEntity:
    case_entity_id: str; case_id: str; entity_id: str; role: str
    valid_from: str | None = None; valid_to: str | None = None; visibility: Visibility = "internal"

@dataclass(frozen=True, slots=True)
class CaseEvent:
    case_event_id: str; case_id: str; event_type: str; occurred_at: str
    description: str; source_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    amount_usd: str | None = None; certainty: float = 1.0; visibility: Visibility = "internal"

@dataclass(frozen=True, slots=True)
class Contradiction:
    contradiction_id: str; case_id: str; claim_ids: tuple[str, ...]; contradiction_type: str
    severity: str; status: Literal["open", "resolved", "held_apart"] = "open"
    resolution_rationale: str | None = None; assigned_reviewer: str | None = None

@dataclass(frozen=True, slots=True)
class Lead:
    lead_id: str; case_id: str; question: str; status: str = "open"
    acquisition_target: str | None = None; owner: str | None = None; due_at: str | None = None
    closure_evidence_ids: tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str; case_id: str; claim_id: str; conclusion: str; confidence: float
    reviewer: str; contradiction_reviewed: bool; status: Literal["draft", "accepted", "withdrawn"] = "draft"
    visibility: Visibility = "internal"

@dataclass(frozen=True, slots=True)
class CaseSnapshot:
    case_snapshot_id: str; case_id: str; created_at: str; manifest_sha256: str
    evidence_ids: tuple[str, ...]; supersedes_snapshot_id: str | None = None
    redaction_profile: str = "internal"

@dataclass(frozen=True, slots=True)
class AuditEvent:
    audit_event_id: str; case_id: str; sequence: int; occurred_at: str; actor: str
    action: str; object_type: str; object_id: str; payload_sha256: str
    previous_event_sha256: str | None = None
