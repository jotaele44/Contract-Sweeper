"""Cross-layer join tests, including the Arcadis convergence fixture."""

import json
from pathlib import Path

import pytest

from moneysweep.fusion.join_engine import cross_layer_join

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "fusion"


def _load(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_arcadis_cross_layer_join():
    fixture = _load("arcadis_cross_layer.json")
    result = cross_layer_join(fixture)
    expected = fixture["expected"]

    # One canonical entity only (all name variants collapse).
    assert len(result.distinct_entity_ids) == 1
    assert result.canonical_entity == expected["canonical_entity"]
    assert list(result.domains_present) == expected["domains_present"]
    assert set(result.documented_edges) == set(expected["documented_edges"])
    assert result.cross_layer_join_pass is True

    # The join confirms convergence, NOT influence.
    assert result.influence_conclusion is None
    assert result.to_dict()["influence_conclusion"] is None


@pytest.mark.unit
def test_arcadis_documented_edges_are_evidence_backed():
    result = cross_layer_join(_load("arcadis_cross_layer.json"))
    assert {"PREPARED_REPORT_FOR", "LOBBIED_FOR"} <= set(result.documented_edges)
    for edge in result.edges:
        assert edge.source_record_id  # every edge carries evidence
    # No conclusory predicate leaked in.
    assert "INFLUENCED" not in result.documented_edges


@pytest.mark.unit
def test_to_dict_matches_documented_shape():
    result = cross_layer_join(_load("arcadis_cross_layer.json"))
    payload = result.to_dict()
    assert set(payload) == {
        "canonical_entity",
        "domains_present",
        "documented_edges",
        "influence_conclusion",
        "cross_layer_join_pass",
    }
    assert payload["cross_layer_join_pass"] is True


@pytest.mark.unit
def test_prasa_project_geography_bridge():
    fixture = _load("prasa_project_geography.json")
    result = cross_layer_join(fixture)
    expected = fixture["expected"]
    assert len(result.distinct_entity_ids) == 1
    assert set(result.documented_edges) == set(expected["documented_edges"])
    assert "SERVES_MUNICIPALITY" in result.documented_edges
    assert result.cross_layer_join_pass is True
    assert result.influence_conclusion is None
