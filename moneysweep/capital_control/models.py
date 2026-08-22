from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping


IDENTITY_LEVELS = {
    "LEGAL_ENTITY",
    "FUND_OR_VEHICLE",
    "INVESTOR_FAMILY",
    "ULTIMATE_PARENT",
    "PERSON",
    "UNKNOWN",
}
IDENTITY_STATUSES = {
    "PASS",
    "PROVISIONAL",
    "CANDIDATE_NOT_IDENTITY",
    "UNRESOLVED",
    "SUPERSEDED",
}
PASS_BINDING_BASES = {
    "STABLE_ID",
    "AUTHORITATIVE_BINDING",
    "AUTHORITATIVE_ALIAS_WITH_CORROBORATION",
    "HISTORICAL_CONTINUITY_WITH_CORROBORATION",
}
BINDING_BASES = PASS_BINDING_BASES | {"HEURISTIC_DISCOVERY_ONLY", "NONE"}
POSITION_CLASSES = {
    "BENEFICIAL_OWNERSHIP",
    "INVESTMENT_DISCRETION",
    "VOTING_AUTHORITY",
    "DISPOSITIVE_AUTHORITY",
    "DIRECT_EQUITY",
    "INDIRECT_EQUITY",
    "FUND_HOLDING",
    "NOMINEE",
    "CUSTODY",
    "TRUST",
    "INSIDER",
    "PARENT_CONTROL",
    "DEBT",
    "LENDING",
    "BONDHOLDING",
    "GUARANTEE",
    "LIEN",
    "MORTGAGE",
    "COLLATERAL",
    "JV_INTEREST",
    "PRIVATE_EQUITY_SPONSORSHIP",
    "UNKNOWN",
}
DIRECTNESS_STATES = {"DIRECT", "INDIRECT", "MIXED", "UNKNOWN"}
TRISTATE_STATES = {"YES", "NO", "UNKNOWN"}
AMENDMENT_STATUSES = {"ORIGINAL", "AMENDED", "SUPERSEDED", "UNKNOWN"}
SOURCE_FAMILIES = {
    "REGULATORY_HOLDINGS",
    "BENEFICIAL_OWNERSHIP",
    "PROXY_OR_ANNUAL_REPORT",
    "INSIDER_FILING",
    "FUND_HOLDINGS",
    "PENSION_DISCLOSURE",
    "CORPORATE_REGISTRY",
    "TRANSACTION_DOCUMENT",
    "BANKRUPTCY_EXHIBIT",
    "ACQUISITION_FILING",
    "DEBT_OR_LIEN_RECORD",
    "OTHER_AUTHORITATIVE",
    "DISCOVERY_ONLY",
}
BYTE_STATUSES = {"FROZEN", "REMOTE_ONLY", "UNAVAILABLE", "UNRESOLVED"}
CANONICALITY_STATES = {
    "CANONICAL",
    "CORROBORATING",
    "DISCOVERY_ONLY",
    "NONCANONICAL",
    "UNRESOLVED",
}


@dataclass(frozen=True)
class InvestorIdentity:
    investor_id: str
    raw_name: str
    identity_level: str
    identity_status: str
    source_id: str
    normalized_name: str | None = None
    canonical_name: str | None = None
    legal_entity_id: str | None = None
    investor_family_id: str | None = None
    ultimate_parent_id: str | None = None
    binding_basis: str = "NONE"
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None


@dataclass(frozen=True)
class HoldingObservation:
    observation_id: str
    holder_id: str
    issuer_id: str
    position_class: str
    as_of_date: date
    report_date: date
    source_id: str
    source_record_id: str
    identity_status: str
    security_id: str | None = None
    security_class_raw: str | None = None
    direct_or_indirect: str = "UNKNOWN"
    shares: float | None = None
    principal_amount: float | None = None
    market_value: float | None = None
    currency: str | None = None
    percent_class: float | None = None
    percent_issuer: float | None = None
    sole_voting_power: float | None = None
    shared_voting_power: float | None = None
    sole_dispositive_power: float | None = None
    shared_dispositive_power: float | None = None
    beneficial_owner_status: str = "UNKNOWN"
    investment_adviser_status: str = "UNKNOWN"
    control_status: str = "UNKNOWN"
    amendment_status: str = "UNKNOWN"
    supersedes_observation_id: str | None = None
    source_document_sha256: str | None = None
    notes: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceManifest:
    source_id: str
    source_family: str
    source_authority: str
    retrieval_utc: datetime
    source_url_or_locator: str
    byte_status: str
    source_as_of_date: date | None = None
    refresh_date: date | None = None
    query_identity: str | None = None
    page_or_offset: str | None = None
    raw_bytes_sha256: str | None = None
    raw_bytes_size: int | None = None
    schema_fingerprint: str | None = None
    record_count: int | None = None
    canonicality: str = "UNRESOLVED"
    notes: str | None = None
