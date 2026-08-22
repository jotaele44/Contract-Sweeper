"""Resolve user targets against the canonical Money Sweep entity namespace."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from moneysweep.runtime.name_normalization import normalize_name

from .models import IdentityEvidence, InvestigationTarget, ResolutionState

ENTITY_MASTER = Path("data/reference/entity_master.csv")
ENTITY_ALIASES = Path("data/reference/entity_aliases.csv")


class CanonicalEntityIndex:
    """In-memory canonical entity/alias index.

    Stable ``ENT_*`` identifiers are authoritative. Canonical-name and alias
    lookups resolve only through committed master rows. If a normalized lookup
    points to multiple canonical IDs, every candidate is preserved and the
    result is REVIEW rather than an arbitrary winner.
    """

    def __init__(self, *, root: Path):
        self.root = Path(root)
        self.entities_by_id: dict[str, dict[str, str]] = {}
        self.canonical_index: dict[str, list[str]] = defaultdict(list)
        self.alias_index: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.aliases_by_entity: dict[str, list[str]] = defaultdict(list)
        self._load()

    def _load(self) -> None:
        master_path = self.root / ENTITY_MASTER
        alias_path = self.root / ENTITY_ALIASES
        if not master_path.exists():
            raise FileNotFoundError(master_path)
        with master_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                entity_id = (row.get("entity_id") or "").strip()
                name = (row.get("canonical_name") or "").strip()
                if not entity_id or not name:
                    continue
                self.entities_by_id[entity_id] = row
                self.canonical_index[normalize_name(name)].append(entity_id)
        if alias_path.exists():
            with alias_path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    entity_id = (row.get("entity_id") or "").strip()
                    alias = (row.get("alias") or "").strip()
                    if not entity_id or not alias:
                        continue
                    key = (row.get("normalized_alias") or normalize_name(alias)).strip()
                    self.alias_index[key].append(row)
                    self.aliases_by_entity[entity_id].append(alias)

    def resolve(self, value: str, *, kind: str = "name") -> InvestigationTarget:
        raw = str(value or "").strip()
        if not raw:
            return InvestigationTarget(
                requested_value=raw,
                requested_kind=kind,
                resolution_state=ResolutionState.UNRESOLVED,
                notes=("empty target",),
            )
        if kind == "entity_id" or raw.startswith("ENT_"):
            row = self.entities_by_id.get(raw)
            if row is None:
                return InvestigationTarget(
                    requested_value=raw,
                    requested_kind=kind,
                    resolution_state=ResolutionState.UNRESOLVED,
                    match_method="stable_id",
                    notes=("canonical entity_id not found",),
                )
            return self._resolved(row, raw, "stable_id", raw)
        if kind != "name":
            return InvestigationTarget(
                requested_value=raw,
                requested_kind=kind,
                resolution_state=ResolutionState.UNRESOLVED,
                notes=("non-name external identifiers require a canonical entity binding first",),
            )

        key = normalize_name(raw)
        canonical_ids = sorted(set(self.canonical_index.get(key, [])))
        if len(canonical_ids) == 1:
            row = self.entities_by_id[canonical_ids[0]]
            return self._resolved(row, raw, "canonical_registry_name", row["canonical_name"])
        if len(canonical_ids) > 1:
            return self._review(raw, kind, canonical_ids, "canonical_name_collision")

        alias_rows = self.alias_index.get(key, [])
        alias_ids = sorted({row.get("entity_id", "") for row in alias_rows if row.get("entity_id")})
        if len(alias_ids) == 1:
            row = self.entities_by_id[alias_ids[0]]
            matched = next((r.get("alias", "") for r in alias_rows if r.get("entity_id") == alias_ids[0]), raw)
            return self._resolved(row, raw, "authoritative_alias", matched)
        if len(alias_ids) > 1:
            return self._review(raw, kind, alias_ids, "alias_collision")

        return InvestigationTarget(
            requested_value=raw,
            requested_kind=kind,
            resolution_state=ResolutionState.UNRESOLVED,
            match_method="discovery_name_no_binding",
            notes=("no canonical name or authoritative alias binding found",),
        )

    def _resolved(
        self, row: dict[str, str], requested: str, method: str, matched: str
    ) -> InvestigationTarget:
        entity_id = row["entity_id"]
        evidence = IdentityEvidence(
            evidence_type=method,
            source_path=str(ENTITY_MASTER if method != "authoritative_alias" else ENTITY_ALIASES),
            raw_value=matched,
            canonical_entity_id=entity_id,
            strength="stable_id" if method == "stable_id" else "authoritative_binding",
        )
        return InvestigationTarget(
            requested_value=requested,
            requested_kind="entity_id" if method == "stable_id" else "name",
            resolution_state=ResolutionState.RESOLVED,
            canonical_entity_id=entity_id,
            canonical_name=row.get("canonical_name"),
            entity_type=row.get("entity_type"),
            jurisdiction=row.get("jurisdiction"),
            match_method=method,
            matched_value=matched,
            aliases=tuple(sorted(set(self.aliases_by_entity.get(entity_id, [])))),
            evidence=(evidence,),
        )

    def _review(
        self, raw: str, kind: str, candidates: list[str], issue: str
    ) -> InvestigationTarget:
        return InvestigationTarget(
            requested_value=raw,
            requested_kind=kind,
            resolution_state=ResolutionState.REVIEW,
            match_method=issue,
            candidates=tuple(candidates),
            notes=("tied authoritative candidate set; no deterministic winner is identity evidence",),
        )
