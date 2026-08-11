"""MoneySweep Case Manager schema foundation.

This package is deliberately UI-agnostic and does not mutate canonical evidence.
"""

from .ids import deterministic_id
from .models import (
    AuditEvent,
    Case,
    CaseEntity,
    CaseEvent,
    CaseEvidence,
    CaseSnapshot,
    Claim,
    ClaimEvidence,
    Contradiction,
    Finding,
    Lead,
)
from .validators import ValidationError, validate_append_only_events, validate_case_bundle

__all__ = [
    "AuditEvent",
    "Case",
    "CaseEntity",
    "CaseEvent",
    "CaseEvidence",
    "CaseSnapshot",
    "Claim",
    "ClaimEvidence",
    "Contradiction",
    "Finding",
    "Lead",
    "ValidationError",
    "deterministic_id",
    "validate_append_only_events",
    "validate_case_bundle",
]
