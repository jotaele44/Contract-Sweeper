"""Deterministic, evidence-backed cross-domain fusion.

Exposes documented cross-layer paths between canonical entities. Never emits
influence, capture, or coordination conclusions (see
``docs/fusion_engine_methodology.md``).
"""

from __future__ import annotations

from moneysweep.fusion.contradictions import Contradiction, ContradictionStore
from moneysweep.fusion.edge_builder import EdgeValidationError, build_edge
from moneysweep.fusion.join_engine import cross_layer_join
from moneysweep.fusion.models import (
    APPROVED_PREDICATES,
    AssertionType,
    CanonicalEntity,
    EvidenceRecord,
    FusionObservation,
    PublicationStatus,
    RelationshipEdge,
)
from moneysweep.fusion.publication_gate import PublicationGateError, check_publishable

__all__ = [
    "APPROVED_PREDICATES",
    "AssertionType",
    "CanonicalEntity",
    "EvidenceRecord",
    "FusionObservation",
    "PublicationStatus",
    "RelationshipEdge",
    "build_edge",
    "EdgeValidationError",
    "cross_layer_join",
    "Contradiction",
    "ContradictionStore",
    "check_publishable",
    "PublicationGateError",
]
