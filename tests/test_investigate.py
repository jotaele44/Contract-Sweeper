"""Regression gates for the generalized selected-entity investigation surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from moneysweep.investigate import CanonicalEntityIndex, investigate
from moneysweep.investigate.models import InvestigationLimits, ResolutionState

ROOT = Path(__file__).resolve().parents[1]
PREPA = "ENT_AGENCY_6c1d858c1babe390"
GENERA = "ENT_ORG_0f8f1789b2c687ed"
ARCADIS = "ENT_ORG_21371fab1b27e788"
COMMONWEALTH = "ENT_AGENCY_125b538f289a4708"


@pytest.mark.unit
def test_pilot_three_entity_alias_resolution_is_canonical():
    index = CanonicalEntityIndex(root=ROOT)
    targets = [index.resolve("PREPA"), index.resolve("Genera"), index.resolve("Arcadis")]
    assert [target.resolution_state for target in targets] == [
        ResolutionState.RESOLVED,
        ResolutionState.RESOLVED,
        ResolutionState.RESOLVED,
    ]
    assert [target.canonical_entity_id for target in targets] == [PREPA, GENERA, ARCADIS]
    assert all(target.match_method == "authoritative_alias" for target in targets)


@pytest.mark.unit
def test_unknown_name_fails_closed_without_candidate_identity():
    target = CanonicalEntityIndex(root=ROOT).resolve(
        "Definitely Not A Canonical Money Sweep Entity"
    )
    assert target.resolution_state is ResolutionState.UNRESOLVED
    assert target.canonical_entity_id is None
    assert target.match_method == "discovery_name_no_binding"


@pytest.mark.unit
def test_stable_id_resolution_is_authoritative():
    target = CanonicalEntityIndex(root=ROOT).resolve(PREPA, kind="entity_id")
    assert target.resolved
    assert target.canonical_entity_id == PREPA
    assert target.match_method == "stable_id"


@pytest.mark.unit
def test_three_entity_pilot_lineage_positive_and_negative_gates():
    result = investigate(
        ["PREPA", "Genera", "Arcadis"],
        root=ROOT,
        modes=("LINEAGE",),
        limits=InvestigationLimits(max_depth=1, max_nodes=20, max_edges=20),
    )
    pairs = {
        (edge["parent_entity_id"], edge["child_entity_id"], edge["relationship_type"])
        for edge in result.lineage_edges
    }
    assert (COMMONWEALTH, PREPA, "INSTRUMENTALITY_OF") in pairs
    assert (PREPA, GENERA, "P3_OPERATOR_OF") in pairs
    # Arcadis has no curated parent/operator edge in the current canonical map.
    assert not any(
        ARCADIS in (edge["parent_entity_id"], edge["child_entity_id"])
        for edge in result.lineage_edges
    )
    assert not result.review_items


@pytest.mark.unit
def test_full_mode_expands_to_all_generalized_modes_without_remote_network():
    result = investigate(["PREPA"], root=ROOT, modes=("FULL",), remote=False)
    assert result.modes == (
        "PROFILE",
        "LINEAGE",
        "CORRELATION",
        "RELATIONSHIP",
        "CONVERGENCE",
    )
    assert "entity_sources" not in result.remote_source_summaries


@pytest.mark.unit
def test_unresolved_target_is_reviewed_and_never_generates_lineage():
    result = investigate(
        ["Definitely Not A Canonical Money Sweep Entity"],
        root=ROOT,
        modes=("FULL",),
        remote=False,
    )
    assert result.targets[0].resolution_state is ResolutionState.UNRESOLVED
    assert result.lineage_edges == []
    assert result.local_correlations == []
    assert result.review_items[0]["issue_type"] == "unresolved_identity"
