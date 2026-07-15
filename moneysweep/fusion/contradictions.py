"""Contradiction handling.

When two sources make conflicting claims about the same subject/predicate, both
claims are **retained side-by-side** — the store never overwrites or silently
reconciles. Each contradiction carries a status
(``none`` | ``unresolved`` | ``resolved``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from moneysweep.fusion.models import ContradictionStatus

__all__ = ["Claim", "Contradiction", "ContradictionStore"]


@dataclass(frozen=True)
class Claim:
    """A single source's assertion about a (subject, predicate) key."""

    value: Any
    source_record_id: str
    evidence_tier: str = "T2"


@dataclass
class Contradiction:
    """Two or more conflicting claims about the same key, preserved together."""

    subject_entity_id: str
    predicate: str
    claims: list[Claim] = field(default_factory=list)
    status: ContradictionStatus = ContradictionStatus.NONE

    def distinct_values(self) -> list[Any]:
        seen: list[Any] = []
        for c in self.claims:
            if c.value not in seen:
                seen.append(c.value)
        return seen

    @property
    def is_conflicting(self) -> bool:
        return len(self.distinct_values()) > 1


class ContradictionStore:
    """Collects claims and surfaces conflicts without discarding any source."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Contradiction] = {}

    def add_claim(
        self,
        subject_entity_id: str,
        predicate: str,
        value: Any,
        source_record_id: str,
        evidence_tier: str = "T2",
    ) -> Contradiction:
        """Record a claim. Never overwrites an existing one.

        The contradiction's status flips to ``unresolved`` as soon as a second,
        differing value is observed for the same key.
        """
        key = (subject_entity_id, predicate)
        entry = self._by_key.get(key)
        if entry is None:
            entry = Contradiction(subject_entity_id, predicate)
            self._by_key[key] = entry
        entry.claims.append(Claim(value, source_record_id, evidence_tier))
        if entry.is_conflicting and entry.status is ContradictionStatus.NONE:
            entry.status = ContradictionStatus.UNRESOLVED
        return entry

    def resolve(self, subject_entity_id: str, predicate: str) -> None:
        """Mark a contradiction resolved. Claims are kept for provenance."""
        entry = self._by_key.get((subject_entity_id, predicate))
        if entry is not None:
            entry.status = ContradictionStatus.RESOLVED

    def conflicts(self) -> list[Contradiction]:
        """All keys that carry more than one distinct value."""
        return [c for c in self._by_key.values() if c.is_conflicting]

    def get(self, subject_entity_id: str, predicate: str) -> Contradiction | None:
        return self._by_key.get((subject_entity_id, predicate))

    def __len__(self) -> int:
        return len(self._by_key)
