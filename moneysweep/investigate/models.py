"""Stable data contracts for selected-entity investigations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from moneysweep.query.entity_types import EntityIdentifier


class ResolutionState(str, Enum):
    RESOLVED = "RESOLVED"
    REVIEW = "REVIEW"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class IdentityEvidence:
    evidence_type: str
    source_path: str
    raw_value: str
    canonical_entity_id: str | None
    strength: str
    notes: str = ""


@dataclass(frozen=True)
class InvestigationTarget:
    """One fail-closed investigation seed.

    ``canonical_entity_id`` is the Money Sweep internal identity authority.
    External identifiers remain attached identifiers, never replacement IDs.
    ``candidates`` preserves the full candidate set when a lookup is ambiguous.
    """

    requested_value: str
    requested_kind: str = "name"
    resolution_state: ResolutionState = ResolutionState.UNRESOLVED
    canonical_entity_id: str | None = None
    canonical_name: str | None = None
    entity_type: str | None = None
    jurisdiction: str | None = None
    match_method: str | None = None
    matched_value: str | None = None
    aliases: tuple[str, ...] = ()
    external_identifiers: tuple[EntityIdentifier, ...] = ()
    candidates: tuple[str, ...] = ()
    evidence: tuple[IdentityEvidence, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.resolution_state is ResolutionState.RESOLVED

    def query_identifiers(self, *, include_names: bool = True) -> tuple[EntityIdentifier, ...]:
        identifiers = list(self.external_identifiers)
        if include_names and self.resolved and self.canonical_name:
            identifiers.append(EntityIdentifier(kind="name", value=self.canonical_name))
            for alias in self.aliases:
                identifiers.append(EntityIdentifier(kind="name", value=alias))
        dedup = {
            (ident.kind, ident.value.strip()): ident for ident in identifiers if ident.value.strip()
        }
        return tuple(dedup[key] for key in sorted(dedup))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolution_state"] = self.resolution_state.value
        payload["external_identifiers"] = [
            {"kind": ident.kind, "value": ident.value} for ident in self.external_identifiers
        ]
        return payload


@dataclass(frozen=True)
class InvestigationLimits:
    max_depth: int = 1
    max_nodes: int = 100
    max_edges: int = 250

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be >= 1")
        if self.max_edges < 1:
            raise ValueError("max_edges must be >= 1")


@dataclass
class InvestigationResult:
    targets: list[InvestigationTarget]
    modes: tuple[str, ...]
    lineage_edges: list[dict[str, Any]] = field(default_factory=list)
    local_correlations: list[dict[str, Any]] = field(default_factory=list)
    remote_source_summaries: dict[str, Any] = field(default_factory=dict)
    review_items: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "targets": [target.to_dict() for target in self.targets],
            "modes": list(self.modes),
            "lineage_edges": self.lineage_edges,
            "local_correlations": self.local_correlations,
            "remote_source_summaries": self.remote_source_summaries,
            "review_items": self.review_items,
            "notes": self.notes,
        }
