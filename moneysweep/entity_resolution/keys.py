"""Canonical identifier hierarchy and deterministic internal IDs.

The identifier hierarchy mirrors ``config/domains/fusion.yml``. Only identifiers
marked ``authoritative`` can, on their own, justify an auto-merge (see
``resolver.py``). Identifiers carry temporal validity so obsolete historical ids
(notably DUNS) are *preserved*, not discarded — they still resolve longitudinal
records for the period they were valid.

Deterministic internal IDs are produced by the repo's existing
``moneysweep.runtime.canonical_ids`` helpers (pure functions of the payload), not
random UUIDs, so the same real-world entity yields the same id across runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from moneysweep.runtime import canonical_ids

__all__ = [
    "IdentifierKey",
    "IDENTIFIER_HIERARCHY",
    "AUTHORITATIVE_KEYS",
    "Identifier",
    "identifier_priority",
    "is_authoritative",
    "best_identifier",
    "has_unique_authoritative_id",
    "internal_canonical_id",
]


@dataclass(frozen=True)
class IdentifierKey:
    """A kind of identifier and its resolution weight."""

    priority: int
    key: str
    authoritative: bool


# Priority 1 == strongest. Ordering matches config/domains/fusion.yml.
IDENTIFIER_HIERARCHY: tuple[IdentifierKey, ...] = (
    IdentifierKey(1, "uei", True),
    IdentifierKey(2, "cage", True),
    IdentifierKey(3, "pr_corp_reg", True),
    # ASG's Licitador ID, issued by the central procurement authority to every
    # vendor in the RUL/RUP registries (source: asg_suppliers). Authoritative —
    # one ID is one registered bidder — but ranked below pr_corp_reg because it
    # covers only vendors that registered to bid, not every PR corporation.
    IdentifierKey(4, "asg_licitador_id", True),
    IdentifierKey(5, "ein", True),
    IdentifierKey(6, "duns", True),
    IdentifierKey(7, "agency_code", True),
    IdentifierKey(8, "municipality_code", True),
    IdentifierKey(9, "lobby_reg_number", False),
    IdentifierKey(10, "vendor_id", False),
    IdentifierKey(11, "internal_canonical_id", False),
)

_BY_KEY = {ik.key: ik for ik in IDENTIFIER_HIERARCHY}
AUTHORITATIVE_KEYS: frozenset[str] = frozenset(
    ik.key for ik in IDENTIFIER_HIERARCHY if ik.authoritative
)


@dataclass(frozen=True)
class Identifier:
    """A concrete identifier value on an entity, with temporal validity."""

    key: str
    value: str
    valid_from: str | None = None
    valid_to: str | None = None
    source_date: str | None = None

    def is_authoritative(self) -> bool:
        return is_authoritative(self.key)

    def is_valid_on(self, date: str | None) -> bool:
        """Whether this identifier was valid on ``date`` (ISO ``YYYY-MM-DD``).

        Open-ended bounds are treated as unbounded. A ``None`` query date means
        "any time" and always matches — historical ids are never dropped.
        """
        if date is None:
            return True
        if self.valid_from is not None and date < self.valid_from:
            return False
        if self.valid_to is not None and date > self.valid_to:
            return False
        return True


def identifier_priority(key: str) -> int:
    """Priority for ``key`` (lower == stronger); unknown keys sort last."""
    ik = _BY_KEY.get(key)
    return ik.priority if ik else len(IDENTIFIER_HIERARCHY) + 1


def is_authoritative(key: str) -> bool:
    return key in AUTHORITATIVE_KEYS


def best_identifier(identifiers: list[Identifier]) -> Identifier | None:
    """Return the highest-priority identifier from a list, or ``None`` if empty."""
    if not identifiers:
        return None
    return min(identifiers, key=lambda i: identifier_priority(i.key))


def has_unique_authoritative_id(left: list[Identifier], right: list[Identifier]) -> bool:
    """True if the two entities share exactly one authoritative id key whose values match.

    This is the precondition for an auto-merge: a single, unambiguous authoritative
    identifier held in common. If two entities disagree on the value of any shared
    authoritative key, they cannot auto-merge.
    """
    left_auth = {i.key: i.value for i in left if i.is_authoritative()}
    right_auth = {i.key: i.value for i in right if i.is_authoritative()}
    shared_keys = set(left_auth) & set(right_auth)
    if not shared_keys:
        return False
    # Any conflicting shared authoritative key disqualifies an auto-merge.
    for k in shared_keys:
        if left_auth[k] != right_auth[k]:
            return False
    return True


def internal_canonical_id(name: str | None, *, person: bool = False) -> str:
    """Deterministic internal id for an entity, via canonical_ids (no random UUIDs)."""
    return canonical_ids.person_id(name) if person else canonical_ids.entity_id(name)
