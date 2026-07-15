"""Resolution safety invariants: no name-only auto-merge; auth-id gated merges."""

import json
from pathlib import Path

import pytest

from moneysweep.entity_resolution.keys import Identifier
from moneysweep.entity_resolution.resolver import MergeDecision, resolve
from moneysweep.entity_resolution.scoring import NAME_ONLY_CAP, MatchFeatures, score_match

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "fusion"


@pytest.mark.unit
def test_name_only_similarity_is_capped_below_auto_merge():
    # Perfect name + alias match, but no other evidence.
    features = MatchFeatures(normalized_legal_name=1.0, registered_alias=True)
    assert not features.has_non_name_evidence()
    assert score_match(features) <= NAME_ONLY_CAP < 0.95


@pytest.mark.unit
def test_name_only_never_auto_merges_even_with_shared_name():
    features = MatchFeatures(normalized_legal_name=1.0, registered_alias=True)
    # Even if identifiers are absent, a name-only match cannot auto-merge.
    result = resolve(features, [], [])
    assert result.decision is not MergeDecision.AUTO_MERGE
    assert result.decision is MergeDecision.SUGGESTED_MERGE


@pytest.mark.unit
def test_high_score_without_authoritative_id_downgrades_to_suggested():
    # Strong non-name evidence pushes score into the auto-merge band...
    features = MatchFeatures(
        exact_identifier=True,
        normalized_legal_name=1.0,
        address_similarity=1.0,
        telephone_match=True,
    )
    assert score_match(features) >= 0.95
    # ...but without a unique authoritative id, it must not auto-merge.
    result = resolve(features, [], [])
    assert result.decision is MergeDecision.SUGGESTED_MERGE
    assert result.has_unique_authoritative_id is False


@pytest.mark.unit
def test_auto_merge_requires_unique_authoritative_id():
    features = MatchFeatures(
        exact_identifier=True,
        normalized_legal_name=1.0,
        address_similarity=1.0,
    )
    left = [Identifier("uei", "UEIMATCH1")]
    right = [Identifier("uei", "UEIMATCH1")]
    result = resolve(features, left, right)
    assert result.decision is MergeDecision.AUTO_MERGE
    assert result.merged is True


@pytest.mark.unit
def test_conflicting_authoritative_id_blocks_auto_merge():
    features = MatchFeatures(exact_identifier=True, normalized_legal_name=1.0, address_similarity=1.0)
    left = [Identifier("uei", "UEIAAA")]
    right = [Identifier("uei", "UEIBBB")]  # same key, different value
    result = resolve(features, left, right)
    assert result.decision is not MergeDecision.AUTO_MERGE


@pytest.mark.unit
def test_possible_relationship_is_not_a_merge():
    features = MatchFeatures(
        address_similarity=1.0,
        officer_or_authorized_person_overlap=1.0,
        parent_subsidiary_relationship=True,
        municipality_and_project_context=True,
        temporal_overlap=True,
    )
    result = resolve(features, [], [])
    assert 0.65 <= result.score < 0.85
    assert result.decision is MergeDecision.POSSIBLE_RELATIONSHIP
    assert result.merged is False


@pytest.mark.unit
def test_fixture_name_collision_not_auto_merged():
    """The two similarly-named contractors have distinct UEIs and no other evidence."""
    fixture = json.loads((FIXTURE_DIR / "prasa_project_geography.json").read_text())
    collision = fixture["name_collision"]
    left = [Identifier(i["key"], i["value"]) for i in collision["entity_a"]["identifiers"]]
    right = [Identifier(i["key"], i["value"]) for i in collision["entity_b"]["identifiers"]]
    # Names are very similar -> strong name signal, but distinct authoritative ids.
    features = MatchFeatures(normalized_legal_name=0.97, registered_alias=True)
    result = resolve(features, left, right)
    assert result.decision is not MergeDecision.AUTO_MERGE
