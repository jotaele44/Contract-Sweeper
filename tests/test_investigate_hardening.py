"""Hardening regressions for entity investigation identity and source routing."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from moneysweep.investigate import CanonicalEntityIndex, bridge_name, investigate
from moneysweep.investigate.models import InvestigationLimits, ResolutionState
from moneysweep.query import EntityIdentifier, EntityQuery
from moneysweep.query.adapters import ENTITY_ADAPTER_REGISTRY
from moneysweep.query.adapters.nonprofits import NonprofitsIRS990EntityAdapter

ROOT = Path(__file__).resolve().parents[1]
PREPA = "ENT_AGENCY_6c1d858c1babe390"
GENERA = "ENT_ORG_0f8f1789b2c687ed"
ARCADIS = "ENT_ORG_21371fab1b27e788"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture_root(tmp_path: Path) -> Path:
    _write_csv(
        tmp_path / "data/reference/entity_master.csv",
        [
            "entity_id",
            "entity_type",
            "canonical_name",
            "jurisdiction",
            "source_id",
            "evidence_tier",
            "confidence",
            "notes",
        ],
        [
            {
                "entity_id": "ENT_ORG_A",
                "entity_type": "organization",
                "canonical_name": "Acme LLC",
                "jurisdiction": "PR",
                "source_id": "fixture",
                "evidence_tier": "T1",
                "confidence": "1",
                "notes": "",
            },
            {
                "entity_id": "ENT_ORG_B",
                "entity_type": "organization",
                "canonical_name": "Acme Inc",
                "jurisdiction": "PR",
                "source_id": "fixture",
                "evidence_tier": "T1",
                "confidence": "1",
                "notes": "",
            },
        ],
    )
    _write_csv(
        tmp_path / "data/reference/entity_aliases.csv",
        [
            "alias_id",
            "entity_id",
            "alias",
            "normalized_alias",
            "source_id",
            "evidence_tier",
            "confidence",
            "notes",
        ],
        [
            {
                "alias_id": "ALIAS_A",
                "entity_id": "ENT_ORG_A",
                "alias": "Shared",
                "normalized_alias": "SHARED",
                "source_id": "fixture",
                "evidence_tier": "T1",
                "confidence": "1",
                "notes": "",
            },
            {
                "alias_id": "ALIAS_B",
                "entity_id": "ENT_ORG_B",
                "alias": "Shared",
                "normalized_alias": "SHARED",
                "source_id": "fixture",
                "evidence_tier": "T1",
                "confidence": "1",
                "notes": "",
            },
        ],
    )
    _write_csv(
        tmp_path / "data/reference/entity_parent_map.csv",
        [
            "relation_id",
            "parent_entity_id",
            "child_entity_id",
            "relationship_type",
            "source_id",
            "evidence_tier",
            "confidence",
            "notes",
        ],
        [],
    )
    return tmp_path


@pytest.mark.unit
def test_current_canonical_index_has_zero_unadjudicated_identity_collisions():
    audit = CanonicalEntityIndex(root=ROOT).audit()
    assert audit["identity_collision_count"] == 0
    assert audit["integrity_issue_count"] == 0
    assert audit["ready"] is True


@pytest.mark.unit
def test_normalized_canonical_collision_fails_closed(tmp_path):
    index = CanonicalEntityIndex(root=_fixture_root(tmp_path))
    target = index.resolve("Acme")
    assert target.resolution_state is ResolutionState.REVIEW
    assert target.match_method == "canonical_name_collision"
    assert set(target.candidates) == {"ENT_ORG_A", "ENT_ORG_B"}
    assert index.audit()["identity_collision_count"] == 2


@pytest.mark.unit
def test_alias_collision_fails_closed_with_all_candidates(tmp_path):
    index = CanonicalEntityIndex(root=_fixture_root(tmp_path))
    target = index.resolve("Shared")
    assert target.resolution_state is ResolutionState.REVIEW
    assert target.match_method == "alias_collision"
    assert set(target.candidates) == {"ENT_ORG_A", "ENT_ORG_B"}


@pytest.mark.unit
def test_blank_target_is_unresolved_and_never_traversed():
    result = investigate([""], root=ROOT, modes=("FULL",), remote=False)
    assert result.targets[0].resolution_state is ResolutionState.UNRESOLVED
    assert result.lineage_edges == []
    assert result.local_correlations == []


@pytest.mark.unit
def test_lineage_limits_are_enforced():
    result = investigate(
        ["PREPA", "Genera"],
        root=ROOT,
        modes=("LINEAGE",),
        limits=InvestigationLimits(max_depth=1, max_nodes=2, max_edges=1),
    )
    assert len(result.lineage_edges) <= 1


@pytest.mark.unit
def test_namespace_bridge_resolves_authoritative_aliases_and_preserves_unknowns():
    index = CanonicalEntityIndex(root=ROOT)
    prepa = bridge_name(
        index,
        source_namespace="prepa_titleiii",
        source_record_id="prepa_titleiii:prepa",
        source_name="PREPA",
    )
    unknown = bridge_name(
        index,
        source_namespace="legacy",
        source_record_id="legacy:1",
        source_name="Unknown Example Company",
    )
    assert prepa.bridge_status == "RESOLVED"
    assert prepa.canonical_entity_id == PREPA
    assert unknown.bridge_status == "CANDIDATE_NOT_IDENTITY"
    assert unknown.canonical_entity_id is None


@pytest.mark.unit
def test_multi_entity_end_to_end_target_identity_is_stable():
    result = investigate(
        ["PREPA", "Genera", "Arcadis"],
        root=ROOT,
        modes=("FULL",),
        remote=False,
        max_local_matches=25,
    )
    assert [target.canonical_entity_id for target in result.targets] == [PREPA, GENERA, ARCADIS]
    assert not result.review_items
    assert len(result.local_correlations) <= 25


def _mock_response(payload: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.unit
def test_nonprofit_entity_adapter_is_registered_and_ein_native():
    assert ENTITY_ADAPTER_REGISTRY["nonprofits_irs990"] is NonprofitsIRS990EntityAdapter
    assert NonprofitsIRS990EntityAdapter.supported_kinds == frozenset({"ein"})


@pytest.mark.unit
def test_nonprofit_entity_adapter_direct_ein_lookup_skips_names():
    session = MagicMock()
    session.get.return_value = _mock_response(
        {
            "organization": {
                "ein": 123456789,
                "name": "Fixture Foundation",
                "city": "San Juan",
                "state": "PR",
                "ntee_code": "T20",
            }
        }
    )
    adapter = NonprofitsIRS990EntityAdapter(root=ROOT, session=session)
    query = EntityQuery(
        identifiers=(
            EntityIdentifier(kind="ein", value="12-3456789"),
            EntityIdentifier(kind="name", value="Fixture Foundation"),
        )
    )
    frame = adapter.fetch(query)
    assert len(frame) == 1
    assert str(frame.iloc[0]["ein"]) == "123456789"
    assert session.get.call_count == 1
    assert session.get.call_args.args[0].endswith("/organizations/123456789.json")
