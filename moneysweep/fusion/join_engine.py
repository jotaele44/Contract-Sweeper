"""Cross-layer join engine.

Resolves a subject's name variants (across FIN_AUDIT and INF_CTRL) to a single
canonical entity, builds the documented, evidence-backed edges, and reports which
domains the entity appears in.

The result **always** carries ``influence_conclusion == None``. The engine exposes
documented convergence; it never concludes influence, capture, or coordination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from moneysweep.fusion.edge_builder import build_edge
from moneysweep.fusion.models import RelationshipEdge
from moneysweep.runtime import canonical_ids

__all__ = ["CrossLayerJoin", "cross_layer_join"]


@dataclass(frozen=True)
class CrossLayerJoin:
    """Result of a cross-layer join for one subject entity."""

    canonical_entity: str
    canonical_entity_id: str
    domains_present: tuple[str, ...]
    documented_edges: tuple[str, ...]
    edges: tuple[RelationshipEdge, ...] = field(default_factory=tuple)
    distinct_entity_ids: tuple[str, ...] = field(default_factory=tuple)
    cross_layer_join_pass: bool = False

    # Influence is an analytical hypothesis, never a fusion output.
    influence_conclusion: None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the documented cross-layer-join shape."""
        return {
            "canonical_entity": self.canonical_entity,
            "domains_present": list(self.domains_present),
            "documented_edges": list(self.documented_edges),
            "influence_conclusion": None,
            "cross_layer_join_pass": self.cross_layer_join_pass,
        }


def _resolve_variants(variants: list[dict[str, Any]]) -> set[str]:
    """Distinct deterministic entity ids for a list of name variants."""
    ids: set[str] = set()
    for v in variants:
        name = v.get("name", "")
        person = bool(v.get("person", False))
        ids.add(
            canonical_ids.person_id(name) if person else canonical_ids.entity_id(name)
        )
    return ids


def cross_layer_join(fixture: dict[str, Any]) -> CrossLayerJoin:
    """Join a subject across domains from a fixture describing its records.

    Expected ``fixture`` shape::

        {
          "subject": {"canonical_name": str, "variants": [{"name", "domain"}...]},
          "relationships": [
            {"domain", "predicate", "object_name", "source_record_id",
             "evidence_tier"?, "assertion_type"?}...
          ]
        }

    ``cross_layer_join_pass`` is True when the subject's variants resolve to exactly
    one canonical entity and at least one documented edge exists.
    """
    subject = fixture["subject"]
    canonical_name: str = subject["canonical_name"]
    variants: list[dict[str, Any]] = subject.get("variants", [])

    distinct_ids = _resolve_variants(variants) or {canonical_ids.entity_id(canonical_name)}
    # Canonical id is derived from the display name so it is stable regardless of
    # which variant list is supplied.
    subject_id = canonical_ids.entity_id(canonical_name)

    edges: list[RelationshipEdge] = []
    predicates: list[str] = []
    domains: set[str] = set()

    for rel in fixture.get("relationships", []):
        domain = rel["domain"]
        object_name = rel.get("object_name", "")
        object_id = canonical_ids.entity_id(object_name) if object_name else rel.get("object_id", "")
        edge = build_edge(
            subject_entity_id=subject_id,
            predicate=rel["predicate"],
            object_entity_id=object_id,
            source_record_id=rel["source_record_id"],
            evidence_tier=rel.get("evidence_tier", "T2"),
            assertion_type=rel.get("assertion_type", "explicit"),
            confidence=rel.get("confidence", 0.0),
        )
        edges.append(edge)
        predicates.append(edge.predicate)
        domains.add(domain)

    # domains_present also reflects the domains the subject's own variants live in.
    for v in variants:
        if v.get("domain"):
            domains.add(v["domain"])

    single_canonical = len(distinct_ids) == 1
    join_pass = single_canonical and len(edges) > 0

    # Deduplicate predicates while preserving first-seen order.
    seen: set[str] = set()
    documented = tuple(p for p in predicates if not (p in seen or seen.add(p)))

    return CrossLayerJoin(
        canonical_entity=canonical_name,
        canonical_entity_id=subject_id,
        domains_present=tuple(sorted(domains)),
        documented_edges=documented,
        edges=tuple(edges),
        distinct_entity_ids=tuple(sorted(distinct_ids)),
        cross_layer_join_pass=join_pass,
    )
