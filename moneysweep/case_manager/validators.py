"""Cross-record validation for Case Manager bundles."""

from __future__ import annotations

from .ids import is_deterministic_id


class ValidationError(ValueError):
    pass


def validate_append_only_events(events) -> None:
    """Require contiguous sequences, unique IDs, and an exact payload-hash chain."""
    seen_ids: set[str] = set()
    previous = None
    for expected, event in enumerate(sorted(events, key=lambda item: item.sequence), start=1):
        if event.sequence != expected:
            raise ValidationError("audit-event sequence must be contiguous from 1")
        if event.audit_event_id in seen_ids:
            raise ValidationError("audit-event IDs must be unique")
        if expected == 1 and event.previous_event_sha256 is not None:
            raise ValidationError("first audit event must not reference a predecessor")
        if previous is not None and event.previous_event_sha256 != previous.payload_sha256:
            raise ValidationError("audit-event predecessor hash must equal the prior payload hash")
        seen_ids.add(event.audit_event_id)
        previous = event


def validate_case_bundle(bundle: dict) -> None:
    """Validate referential and policy invariants without promoting evidence."""
    case = bundle["case"]
    if not is_deterministic_id(case.case_id, "case"):
        raise ValidationError("case_id is not deterministic")
    case_id = case.case_id
    evidence_ids = set(bundle.get("canonical_evidence_ids", ()))
    claim_ids = {item.claim_id for item in bundle.get("claims", ())}

    for link in bundle.get("case_evidence", ()):
        if link.case_id != case_id or link.evidence_id not in evidence_ids:
            raise ValidationError(
                "case evidence must reference this case and an existing canonical evidence ID"
            )
    for claim in bundle.get("claims", ()):
        if claim.case_id != case_id or not 0 <= claim.confidence <= 1:
            raise ValidationError("invalid claim case or confidence")
    for link in bundle.get("claim_evidence", ()):
        if link.claim_id not in claim_ids or link.evidence_id not in evidence_ids:
            raise ValidationError("claim evidence reference is unresolved")
    for contradiction in bundle.get("contradictions", ()):
        if contradiction.case_id != case_id or len(contradiction.claim_ids) < 2:
            raise ValidationError("contradiction must retain at least two claims")
        if not set(contradiction.claim_ids).issubset(claim_ids):
            raise ValidationError("contradiction references unknown claims")
        if contradiction.status == "resolved" and not contradiction.resolution_rationale:
            raise ValidationError("resolved contradiction requires rationale")
    for finding in bundle.get("findings", ()):
        if finding.case_id != case_id or finding.claim_id not in claim_ids:
            raise ValidationError("finding must reference this case and a distinct claim")
        if not 0 <= finding.confidence <= 1:
            raise ValidationError("finding confidence must be between 0 and 1")
        if finding.status == "accepted" and not finding.contradiction_reviewed:
            raise ValidationError("accepted finding requires contradiction review")
    for event in bundle.get("audit_events", ()):
        if event.case_id != case_id:
            raise ValidationError("audit events must reference this case")
    validate_append_only_events(bundle.get("audit_events", ()))
