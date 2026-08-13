"""Government-entity organizational change control plane.

This module is append-only and side-effect free. It validates and classifies
adjudicated change events, derives timeline state, computes graph invalidation
scopes, and determines alert severity. It never rewrites canonical entities or
money-flow edges; downstream products must explicitly recompute from an event's
invalidation plan.

Candidate discovery and canonical identity are intentionally separate universes.
A detected candidate is not a binding event until the evidence and effective-date
gates below pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

EVENT_TYPES = frozenset({
    "DISSOLUTION", "ABOLITION", "MERGER", "CONSOLIDATION", "SPLIT",
    "REORGANIZATION", "RENAMING", "SUCCESSOR_CREATION", "PARENT_CHANGE",
    "TRANSFER_OF_FUNCTIONS", "TRANSFER_OF_ASSETS", "TRANSFER_OF_LIABILITIES",
    "TRANSFER_OF_PERSONNEL", "TRANSFER_OF_CONTRACTS", "TRANSFER_OF_APPROPRIATIONS",
    "LOSS_OF_STATUTORY_POWER", "GAIN_OF_STATUTORY_POWER",
    "PROCUREMENT_AUTHORITY_CHANGE", "BUDGET_AUTHORITY_CHANGE",
    "REGULATORY_AUTHORITY_CHANGE", "ENFORCEMENT_AUTHORITY_CHANGE",
    "LICENSING_AUTHORITY_CHANGE", "OVERSIGHT_CHANGE", "RECEIVERSHIP",
    "FISCAL_CONTROL", "PRIVATIZATION", "PPP_TRANSFER", "CONCESSION",
    "MUNICIPALIZATION", "CENTRALIZATION", "DECENTRALIZATION",
    "TEMPORARY_EMERGENCY_AUTHORITY", "SUNSET_EXTENSION", "SUNSET_EXPIRATION",
    "OPERATIONAL_SUSPENSION", "DEFUNDING", "MATERIAL_BUDGET_REDUCTION",
    "MATERIAL_HEADCOUNT_REDUCTION",
})

EVIDENCE_PRIORITY = (
    "ENACTED_LAW_OR_CONSTITUTION",
    "EXECUTIVE_ORDER_WITH_VALID_AUTHORITY",
    "REGULATION",
    "OFFICIAL_REORGANIZATION_PLAN",
    "APPROPRIATIONS_ACT",
    "OFFICIAL_GOVERNMENT_REGISTER",
    "AGENCY_OR_FISCAL_PLAN",
    "BUDGET_DOCUMENT",
    "PROCUREMENT_OR_CONTRACT_TRANSFER_RECORD",
    "OFFICIAL_ORGANIZATIONAL_CHART",
    "AUTHORITATIVE_PRESS_RELEASE",
    "LEGISLATIVE_PROPOSAL",
    "NEWS_REPORT",
    "OTHER_SECONDARY_REPORT",
)
EVIDENCE_RANK = {name: index for index, name in enumerate(EVIDENCE_PRIORITY)}

# Evidence sufficient to establish a legal structural succession on its own.
SUCCESSION_BINDING_EVIDENCE = frozenset({
    "ENACTED_LAW_OR_CONSTITUTION",
    "EXECUTIVE_ORDER_WITH_VALID_AUTHORITY",
    "REGULATION",
    "OFFICIAL_REORGANIZATION_PLAN",
    "OFFICIAL_GOVERNMENT_REGISTER",
})
# Evidence that may establish an effective legal/administrative state.
LEGAL_BINDING_EVIDENCE = SUCCESSION_BINDING_EVIDENCE | frozenset({"APPROPRIATIONS_ACT"})
# Evidence that may establish an implemented operational transfer without
# asserting legal succession between the participating entities.
OPERATIONAL_BINDING_EVIDENCE = LEGAL_BINDING_EVIDENCE | frozenset({
    "PROCUREMENT_OR_CONTRACT_TRANSFER_RECORD",
    "OFFICIAL_ORGANIZATIONAL_CHART",
})
PROPOSAL_EVIDENCE = frozenset({"LEGISLATIVE_PROPOSAL"})

ENTITY_STATES = frozenset({
    "ACTIVE", "ACTIVE_RESTRUCTURING_PENDING", "AUTHORITY_REDUCED",
    "AUTHORITY_EXPANDED", "FUNCTIONS_PARTIALLY_TRANSFERRED",
    "FUNCTIONS_FULLY_TRANSFERRED", "MERGER_PENDING", "SUCCESSOR_PENDING",
    "DISSOLUTION_PENDING", "DISSOLVED", "SUPERSEDED",
    "TEMPORARILY_SUSPENDED", "UNKNOWN",
})
CERTIFICATION_STATES = frozenset({
    "PASS", "FAIL", "OPEN", "BLOCKED", "PROVISIONAL", "AUDIT_ONLY",
    "NONCANONICAL", "CANDIDATE_NOT_IDENTITY", "UNRESOLVED", "SUPERSEDED",
})

S4_EVENTS = frozenset({
    "DISSOLUTION", "ABOLITION", "MERGER", "CONSOLIDATION", "SPLIT",
    "SUCCESSOR_CREATION", "PRIVATIZATION", "PPP_TRANSFER",
})
S3_EVENTS = frozenset({
    "TRANSFER_OF_FUNCTIONS", "TRANSFER_OF_ASSETS", "TRANSFER_OF_LIABILITIES",
    "TRANSFER_OF_CONTRACTS", "TRANSFER_OF_APPROPRIATIONS",
    "LOSS_OF_STATUTORY_POWER", "GAIN_OF_STATUTORY_POWER",
    "PROCUREMENT_AUTHORITY_CHANGE", "BUDGET_AUTHORITY_CHANGE",
    "REGULATORY_AUTHORITY_CHANGE", "ENFORCEMENT_AUTHORITY_CHANGE",
    "LICENSING_AUTHORITY_CHANGE", "OVERSIGHT_CHANGE", "RECEIVERSHIP",
    "FISCAL_CONTROL", "CONCESSION", "SUNSET_EXPIRATION", "DEFUNDING",
})
S2_EVENTS = frozenset({
    "REORGANIZATION", "PARENT_CHANGE", "TRANSFER_OF_PERSONNEL",
    "MUNICIPALIZATION", "CENTRALIZATION", "DECENTRALIZATION",
    "TEMPORARY_EMERGENCY_AUTHORITY", "OPERATIONAL_SUSPENSION",
    "MATERIAL_BUDGET_REDUCTION", "MATERIAL_HEADCOUNT_REDUCTION",
})
S1_EVENTS = frozenset({"SUNSET_EXTENSION"})

GRAPH_SCOPES = frozenset({
    "ENTITY_GRAPH", "CONTRACT_GRAPH", "GRANT_GRAPH", "APPROPRIATION_GRAPH",
    "CAMPAIGN_AND_LOBBYING_GRAPH", "PPP_GRAPH", "VENDOR_GRAPH",
    "PERSONNEL_GRAPH", "PROPERTY_AND_ASSET_GRAPH", "REGULATORY_GRAPH",
    "HISTORICAL_CONTINUITY_GRAPH",
})

_EVENT_SCOPES = {
    "PARENT_CHANGE": {"ENTITY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "TRANSFER_OF_CONTRACTS": {"ENTITY_GRAPH", "CONTRACT_GRAPH", "VENDOR_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "TRANSFER_OF_APPROPRIATIONS": {"ENTITY_GRAPH", "APPROPRIATION_GRAPH", "GRANT_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "TRANSFER_OF_ASSETS": {"ENTITY_GRAPH", "PROPERTY_AND_ASSET_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "TRANSFER_OF_PERSONNEL": {"ENTITY_GRAPH", "PERSONNEL_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "PROCUREMENT_AUTHORITY_CHANGE": {"ENTITY_GRAPH", "CONTRACT_GRAPH", "VENDOR_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "REGULATORY_AUTHORITY_CHANGE": {"ENTITY_GRAPH", "REGULATORY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "ENFORCEMENT_AUTHORITY_CHANGE": {"ENTITY_GRAPH", "REGULATORY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "LICENSING_AUTHORITY_CHANGE": {"ENTITY_GRAPH", "REGULATORY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "BUDGET_AUTHORITY_CHANGE": {"ENTITY_GRAPH", "APPROPRIATION_GRAPH", "GRANT_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "PPP_TRANSFER": {"ENTITY_GRAPH", "CONTRACT_GRAPH", "PPP_GRAPH", "VENDOR_GRAPH", "PROPERTY_AND_ASSET_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
    "PRIVATIZATION": {"ENTITY_GRAPH", "CONTRACT_GRAPH", "PPP_GRAPH", "VENDOR_GRAPH", "PERSONNEL_GRAPH", "PROPERTY_AND_ASSET_GRAPH", "REGULATORY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"},
}
EDGE_ALTERING_EVENTS = frozenset({"PARENT_CHANGE"})

STRUCTURAL_SUCCESSION_EVENTS = frozenset({
    "DISSOLUTION", "ABOLITION", "MERGER", "CONSOLIDATION", "SPLIT",
    "SUCCESSOR_CREATION",
})
OPERATIONAL_TRANSFER_EVENTS = frozenset({
    "TRANSFER_OF_FUNCTIONS", "TRANSFER_OF_ASSETS", "TRANSFER_OF_LIABILITIES",
    "TRANSFER_OF_PERSONNEL", "TRANSFER_OF_CONTRACTS", "TRANSFER_OF_APPROPRIATIONS",
    "PROCUREMENT_AUTHORITY_CHANGE", "BUDGET_AUTHORITY_CHANGE",
    "REGULATORY_AUTHORITY_CHANGE", "ENFORCEMENT_AUTHORITY_CHANGE",
    "LICENSING_AUTHORITY_CHANGE", "OVERSIGHT_CHANGE", "CONCESSION", "PPP_TRANSFER",
})

REQUIRED_FIELDS = frozenset({
    "change_event_id", "affected_entity_id", "event_type", "status",
    "source_provenance", "confidence", "certification_state",
})


class ChangeEventError(ValueError):
    """Raised when a change event violates a fail-closed invariant."""


@dataclass(frozen=True)
class Evaluation:
    severity: str
    alert: bool
    binding: bool
    timeline_state: str
    succession_cardinality: str
    invalidation_scopes: tuple[str, ...]
    reasons: tuple[str, ...]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ChangeEventError("relationship/transfer fields must be arrays")
    return value


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ChangeEventError(f"{field} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ChangeEventError(f"{field} must be YYYY-MM-DD") from exc


def _evidence_types(event: Mapping[str, Any]) -> set[str]:
    sources = event.get("source_provenance")
    if not isinstance(sources, list) or not sources:
        raise ChangeEventError("source_provenance must contain at least one source assertion reference")
    evidence: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise ChangeEventError("every source_provenance item must be an object")
        assertion_id = source.get("source_assertion_id")
        if not isinstance(assertion_id, str) or not assertion_id.strip():
            raise ChangeEventError("every source_provenance item needs source_assertion_id")
        evidence_type = source.get("evidence_type")
        if evidence_type not in EVIDENCE_RANK:
            raise ChangeEventError("every source_provenance item needs a recognized evidence_type")
        evidence.add(str(evidence_type))
    return evidence


def succession_cardinality(event: Mapping[str, Any]) -> str:
    predecessors = _as_list(event.get("predecessor_entities"))
    successors = _as_list(event.get("successor_entities"))
    if not predecessors or not successors:
        return "UNRESOLVED"
    if len(predecessors) == 1 and len(successors) == 1:
        return "1:1"
    if len(predecessors) == 1:
        return "1:N"
    if len(successors) == 1:
        return "N:1"
    return "N:N"


def validate_event(event: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - event.keys())
    if missing:
        raise ChangeEventError(f"missing required fields: {missing}")
    for field in ("change_event_id", "affected_entity_id"):
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ChangeEventError(f"{field} must be a non-empty string")
    if event["event_type"] not in EVENT_TYPES:
        raise ChangeEventError(f"unsupported event_type: {event['event_type']}")
    if event["status"] not in ENTITY_STATES:
        raise ChangeEventError(f"unsupported status: {event['status']}")
    if event["certification_state"] not in CERTIFICATION_STATES:
        raise ChangeEventError(f"unsupported certification_state: {event['certification_state']}")
    try:
        confidence = float(event["confidence"])
    except (TypeError, ValueError) as exc:
        raise ChangeEventError("confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ChangeEventError("confidence must be within [0, 1]")

    predecessors = _as_list(event.get("predecessor_entities"))
    successors = _as_list(event.get("successor_entities"))
    for values, field in ((predecessors, "predecessor_entities"), (successors, "successor_entities")):
        if len(values) != len(set(values)):
            raise ChangeEventError(f"{field} contains duplicates")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ChangeEventError(f"{field} must contain non-empty entity IDs")
    for field in (
        "powers_before", "powers_after", "functions_transferred", "assets_transferred",
        "liabilities_transferred", "appropriations_transferred", "contracts_transferred",
        "personnel_transferred",
    ):
        _as_list(event.get(field))

    instrument = _parse_date(event.get("instrument_date"), "instrument_date")
    effective = _parse_date(event.get("effective_date"), "effective_date")
    announcement = _parse_date(event.get("announcement_date"), "announcement_date")
    implementation = _parse_date(event.get("implementation_date"), "implementation_date")
    if instrument and effective and effective < instrument:
        raise ChangeEventError("effective_date cannot precede instrument_date")
    if announcement and implementation and implementation < announcement:
        raise ChangeEventError("implementation_date cannot precede announcement_date")

    evidence_types = _evidence_types(event)
    if predecessors or successors:
        if not evidence_types.intersection(SUCCESSION_BINDING_EVIDENCE):
            raise ChangeEventError("predecessor/successor binding requires authoritative succession evidence")
    if evidence_types.intersection(PROPOSAL_EVIDENCE) and not evidence_types.intersection(OPERATIONAL_BINDING_EVIDENCE):
        if effective or event["status"] in {"DISSOLVED", "SUPERSEDED", "FUNCTIONS_FULLY_TRANSFERRED"}:
            raise ChangeEventError("proposal-only evidence cannot establish an effective/binding state")
    if event["event_type"] == "RENAMING" and (predecessors or successors):
        raise ChangeEventError("renaming cannot establish predecessor/successor identity")


def is_binding(event: Mapping[str, Any]) -> bool:
    evidence = _evidence_types(event)
    if event.get("effective_date") in (None, ""):
        return False
    if event["event_type"] in STRUCTURAL_SUCCESSION_EVENTS:
        return bool(evidence.intersection(LEGAL_BINDING_EVIDENCE))
    if event["event_type"] in OPERATIONAL_TRANSFER_EVENTS:
        return bool(evidence.intersection(OPERATIONAL_BINDING_EVIDENCE))
    return bool(evidence.intersection(LEGAL_BINDING_EVIDENCE))


def derive_severity(event: Mapping[str, Any]) -> str:
    kind = event["event_type"]
    if kind in S4_EVENTS:
        return "S4"
    if kind in S3_EVENTS:
        return "S3"
    if kind in S2_EVENTS:
        return "S2"
    if kind in S1_EVENTS:
        return "S1"
    return "S0"


def invalidation_scopes(event: Mapping[str, Any]) -> tuple[str, ...]:
    kind = event["event_type"]
    if kind in S4_EVENTS or kind in {"TRANSFER_OF_FUNCTIONS", "FISCAL_CONTROL"}:
        scopes = set(GRAPH_SCOPES)
    else:
        scopes = set(_EVENT_SCOPES.get(kind, {"ENTITY_GRAPH", "HISTORICAL_CONTINUITY_GRAPH"}))
    if event.get("contracts_transferred"):
        scopes.update({"CONTRACT_GRAPH", "VENDOR_GRAPH"})
    if event.get("appropriations_transferred"):
        scopes.update({"APPROPRIATION_GRAPH", "GRANT_GRAPH"})
    if event.get("assets_transferred"):
        scopes.add("PROPERTY_AND_ASSET_GRAPH")
    if event.get("personnel_transferred"):
        scopes.add("PERSONNEL_GRAPH")
    return tuple(sorted(scopes))


def timeline_state(event: Mapping[str, Any]) -> str:
    """Return the event-carried state after enforcing pending/binding semantics."""
    state = event["status"]
    if not is_binding(event) and state in {"DISSOLVED", "SUPERSEDED", "FUNCTIONS_FULLY_TRANSFERRED"}:
        return "UNKNOWN"
    return state


def evaluate_event(event: Mapping[str, Any]) -> Evaluation:
    validate_event(event)
    severity = derive_severity(event)
    binding = is_binding(event)
    scopes = invalidation_scopes(event)
    cardinality = succession_cardinality(event)
    reasons: list[str] = []
    if severity in {"S3", "S4"}:
        reasons.append("MAJOR_OR_STRUCTURAL_CHANGE")
    if any(s in scopes for s in ("CONTRACT_GRAPH", "APPROPRIATION_GRAPH", "PROPERTY_AND_ASSET_GRAPH", "REGULATORY_GRAPH")):
        reasons.append("MONEY_OR_CONTROL_EDGE_RECOMPUTE")
    if event["event_type"] in EDGE_ALTERING_EVENTS:
        reasons.append("ENTITY_HIERARCHY_RECOMPUTE")
    if event.get("predecessor_entities") or event.get("successor_entities"):
        reasons.append("SUCCESSION_RECOMPUTE")
    if cardinality == "UNRESOLVED" and event["event_type"] in STRUCTURAL_SUCCESSION_EVENTS:
        reasons.append("SUCCESSION_CARDINALITY_UNRESOLVED")
    if not binding:
        reasons.append("NONBINDING_OR_NOT_YET_EFFECTIVE")
    alert = (
        severity in {"S3", "S4"}
        or "MONEY_OR_CONTROL_EDGE_RECOMPUTE" in reasons
        or "ENTITY_HIERARCHY_RECOMPUTE" in reasons
        or "SUCCESSION_RECOMPUTE" in reasons
    )
    return Evaluation(
        severity=severity,
        alert=alert,
        binding=binding,
        timeline_state=timeline_state(event),
        succession_cardinality=cardinality,
        invalidation_scopes=scopes,
        reasons=tuple(reasons),
    )


def evaluate_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate events deterministically without collapsing historical rows."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in events:
        event = dict(raw)
        event_id = str(event.get("change_event_id", ""))
        if event_id in seen:
            raise ChangeEventError(f"duplicate change_event_id: {event_id}")
        seen.add(event_id)
        result = evaluate_event(event)
        rows.append({
            **event,
            "derived": {
                "severity": result.severity,
                "alert": result.alert,
                "binding": result.binding,
                "timeline_state": result.timeline_state,
                "succession_cardinality": result.succession_cardinality,
                "invalidation_scopes": list(result.invalidation_scopes),
                "reasons": list(result.reasons),
            },
        })
    return sorted(rows, key=lambda r: (r.get("effective_date") or "9999-12-31", r["change_event_id"]))
