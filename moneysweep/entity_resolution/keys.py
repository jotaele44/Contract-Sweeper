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
    "shared_authoritative_identifiers",
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
    """A concrete identifier assertion with temporal/provenance context.

    Multiple values for the same ``key`` are valid and must be preserved. This is
    required for historical identifiers such as DUNS/CAGE changes and prevents a
    ``{key: value}`` collapse from silently overwriting contradictory evidence.
    """

    key: str
    value: str
    valid_from: str | None = None
    valid_to: str | None = None
    source_date: str | None = None
    issuer: str | None = None
    source_record_id: str | None = None

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


def _intervals_overlap(left: Identifier, right: Identifier) -> bool:
    """Return whether two identifier-validity intervals overlap.

    ``None`` bounds are open-ended. Bounds are ISO date strings, so lexical order
    is chronological for the accepted ``YYYY-MM-DD`` representation.
    """
    latest_start = max(filter(None, (left.valid_from, right.valid_from)), default=None)
    earliest_end = min(filter(None, (left.valid_to, right.valid_to)), default=None)
    if latest_start is None or earliest_end is None:
        return True
    return latest_start <= earliest_end


def shared_authoritative_identifiers(
    left: list[Identifier], right: list[Identifier]
) -> tuple[tuple[Identifier, Identifier], ...]:
    """Return all temporally-overlapping equal authoritative assertions.

    The full candidate sets are retained. A pair matches only when scheme/key and
    value agree and their validity intervals overlap. No normalization, proximity,
    score, or source absence can create a match here.
    """
    matches: list[tuple[Identifier, Identifier]] = []
    for left_id in left:
        if not left_id.is_authoritative():
            continue
        for right_id in right:
            if not right_id.is_authoritative() or left_id.key != right_id.key:
                continue
            if left_id.value == right_id.value and _intervals_overlap(left_id, right_id):
                matches.append((left_id, right_id))
    return tuple(matches)


def has_unique_authoritative_id(left: list[Identifier], right: list[Identifier]) -> bool:
    """Whether authoritative evidence can safely anchor an auto-merge.

    This legacy-named predicate now evaluates complete multi-value temporal
    assertion sets instead of collapsing each side to ``{key: value}``.

    Rules:
    * at least one equal authoritative assertion must overlap in time;
    * any *overlapping* disagreement on the same authoritative scheme fails
      closed, even if another assertion matches;
    * non-overlapping historical succession is preserved and is not treated as a
      contemporaneous contradiction.
    """
    left_auth = [identifier for identifier in left if identifier.is_authoritative()]
    right_auth = [identifier for identifier in right if identifier.is_authoritative()]

    for left_id in left_auth:
        for right_id in right_auth:
            if left_id.key != right_id.key or not _intervals_overlap(left_id, right_id):
                continue
            if left_id.value != right_id.value:
                return False

    return bool(shared_authoritative_identifiers(left_auth, right_auth))


def internal_canonical_id(name: str | None, *, person: bool = False) -> str:
    """Deterministic internal id for an entity, via canonical_ids (no random UUIDs)."""
    return canonical_ids.person_id(name) if person else canonical_ids.entity_id(name)
