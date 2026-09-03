"""Tests for the canonical_v1 projects ingester (WS-G)."""

import pytest

from moneysweep.validation import canonical_v1_schema as cv1
from scripts import ingest_projects as ip

REPO_ROOT = cv1.REPO_ROOT


@pytest.fixture(scope="module")
def built():
    return ip.build_rows(REPO_ROOT)


@pytest.mark.integration
def test_seed_projects_resolve_lead_entities(built):
    rows = built["project_rows"]
    assert ip.check(rows) == []
    assert {r["project_type"] for r in rows} == {"ppp", "recovery", "infrastructure"}
    # Both surfaces contribute: the agency-led reference seed and the
    # concessionaire-led P3 export.
    assert len(rows) > 5
    # Every skip is an explained duplicate, never an unresolved reference.
    assert all("duplicate of" in s["reason"] for s in built["skipped"]), built["skipped"]


@pytest.mark.integration
def test_p3_surface_contributes_projects_the_seed_lacks(built):
    """The P3 export is no longer a dead-end file — its rows reach canonical."""
    names = {r["project_name"] for r in built["project_rows"]}
    assert "Luis Muñoz Marín Airport" in names
    assert "PRASA O&M Agreement" in names
    assert "Teodoro Moscoso Bridge Toll Concession" in names


@pytest.mark.integration
def test_same_concession_not_duplicated_across_surfaces(built):
    """LUMA/Genera/Metropistas appear in both surfaces under different names.

    project_id() keys off the lead entity, which differs between the agency-led
    seed and the concessionaire-led export, so only the explicit
    canonical_project_number crosswalk catches these.
    """
    rows = built["project_rows"]
    assert sum(1 for r in rows if "LUMA" in r["project_name"]) == 1
    assert sum(1 for r in rows if "Genera" in r["project_name"]) == 1
    assert sum(1 for r in rows if "PR-22" in r["project_name"]) == 1


@pytest.mark.integration
def test_site_extent_projects_carry_a_municipality(built):
    """A 'site' project claims one physical location, so it must name it.

    This is what gives the spatial producer something to geolocate; island-wide
    and corridor projects deliberately have no single point.
    """
    sited = [r for r in built["project_rows"] if r["spatial_extent"] == "site"]
    assert sited, "expected at least one site-extent project"
    for row in sited:
        assert row["municipality_id"], row
    # LMM is in Carolina, not San Juan, despite the common name.
    lmm = next(r for r in built["project_rows"] if "Muñoz Marín" in r["project_name"])
    assert lmm["municipality_id"] == "muni_pr_carolina"
    # The bridge itself sits in San Juan.
    bridge = next(r for r in built["project_rows"] if "Moscoso" in r["project_name"])
    assert bridge["municipality_id"] == "muni_pr_san_juan"


@pytest.mark.unit
def test_spatial_extent_values_are_controlled(built):
    for row in built["project_rows"]:
        assert row["spatial_extent"] in ip.VALID_EXTENTS, row


@pytest.mark.integration
def test_rows_and_evidence_validate(built):
    proj_schema = cv1.load_schema("projects", REPO_ROOT)
    ev_schema = cv1.load_schema("evidence", REPO_ROOT)
    tables = cv1.load_all_tables(REPO_ROOT)
    entity_ids = {r["entity_id"] for r in tables["entities"]}
    muni_ids = {r["municipality_id"] for r in tables["municipalities"]}
    evidence_ids = {e.evidence_id for e in built["evidence_rows"]}
    for row in built["project_rows"]:
        assert cv1.validate_row(row, proj_schema) == [], row
        assert row["lead_entity_id"] in entity_ids  # no broken reference
        assert row["evidence_id"] in evidence_ids  # no provenance -> no row
        if row["municipality_id"]:
            assert row["municipality_id"] in muni_ids
    for ev in built["evidence_rows"]:
        assert cv1.validate_row(ev.as_row(), ev_schema) == [], ev


@pytest.mark.unit
def test_project_ids_unique_and_deterministic(built):
    rows = built["project_rows"]
    ids = [r["project_id"] for r in rows]
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("project_") for i in ids)
    again = ip.build_rows(REPO_ROOT)["project_rows"]
    assert [r["project_id"] for r in again] == ids
