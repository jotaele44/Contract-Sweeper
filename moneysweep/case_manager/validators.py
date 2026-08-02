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
    for entity in bundle.get("case_entities", ()):
        if entity.case_id != case_id:
            raise ValidationError("case entities must reference this case")
    for case_event in bundle.get("case_events", ()):
        if case_event.case_id != case_id:
            raise ValidationError("case events must reference this case")
        if not set(case_event.source_evidence_ids).issubset(evidence_ids):
            raise ValidationError("case event evidence reference is unresolved")
        if not 0 <= case_event.certainty <= 1:
            raise ValidationError("case event certainty must be between 0 and 1")
    for lead in bundle.get("leads", ()):
        if lead.case_id != case_id:
            raise ValidationError("leads must reference this case")
        if not set(lead.closure_evidence_ids).issubset(evidence_ids):
            raise ValidationError("lead closure evidence reference is unresolved")
    snapshot_ids = {item.case_snapshot_id for item in bundle.get("snapshots", ())}
    for snapshot in bundle.get("snapshots", ()):
        if snapshot.case_id != case_id:
            raise ValidationError("snapshots must reference this case")
        if not set(snapshot.evidence_ids).issubset(evidence_ids):
            raise ValidationError("snapshot evidence reference is unresolved")
        if (
            snapshot.supersedes_snapshot_id is not None
            and snapshot.supersedes_snapshot_id not in snapshot_ids
        ):
            raise ValidationError("snapshot supersedes an unknown snapshot")
    for event in bundle.get("audit_events", ()):
        if event.case_id != case_id:
            raise ValidationError("audit events must reference this case")
    validate_append_only_events(bundle.get("audit_events", ()))
    _validate_deterministic_ids(bundle)


_ID_SPECS = (
    ("case_evidence", "case_evidence_id", "case_evidence"),
    ("claims", "claim_id", "claim"),
    ("claim_evidence", "claim_evidence_id", "claim_evidence"),
    ("case_entities", "case_entity_id", "case_entity"),
    ("case_events", "case_event_id", "case_event"),
    ("contradictions", "contradiction_id", "contradiction"),
    ("leads", "lead_id", "lead"),
    ("findings", "finding_id", "finding"),
    ("snapshots", "case_snapshot_id", "case_snapshot"),
    ("audit_events", "audit_event_id", "audit_event"),
)


def _validate_deterministic_ids(bundle: dict) -> None:
    """Every case-scoped record must carry a deterministic primary ID."""
    for key, attr, kind in _ID_SPECS:
        for record in bundle.get(key, ()):
            if not is_deterministic_id(getattr(record, attr), kind):
                raise ValidationError(f"{key} record has a non-deterministic {attr}")
