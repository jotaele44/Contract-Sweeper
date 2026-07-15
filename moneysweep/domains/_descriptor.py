"""Shared, dependency-free domain descriptor type."""

from __future__ import annotations

from dataclasses import dataclass, field

ACCESS_CLASSES = ("public", "restricted_public", "internal")


@dataclass(frozen=True)
class DomainDescriptor:
    """A bounded domain: its id, the record families it owns, and its defaults."""

    domain: str
    title: str
    record_families: tuple[str, ...]
    access_class_default: str = "public"
    edge_predicates: tuple[str, ...] = field(default_factory=tuple)

    def owns(self, record_type: str) -> bool:
        """True if ``record_type`` is one of this domain's declared families."""
        return record_type in self.record_families

    def default_access_class(self) -> str:
        return self.access_class_default
