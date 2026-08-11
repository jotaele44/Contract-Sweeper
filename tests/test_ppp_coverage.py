"""Tests for the PPP coverage truth file.

The report is derived from committed tables, so these run offline and assert the
invariants that make it trustworthy rather than pinning today's counts.
"""

from __future__ import annotations

import json

import pytest

from moneysweep.validation import canonical_v1_schema as cv1
from scripts import build_ppp_coverage as bpc

REPO_ROOT = cv1.REPO_ROOT


@pytest.fixture(scope="module")
def report():
    return bpc.build_report(REPO_ROOT)


@pytest.mark.integration
def test_committed_report_matches_live_rebuild(report):
    on_disk = json.loads((REPO_ROOT / bpc.OUT).read_text(encoding="utf-8"))
    live = dict(report)
    on_disk.pop("generated_at", None)
    live.pop("generated_at", None)
    assert on_disk == live, "reports/ppp_coverage.json drifted — rerun build_ppp_coverage.py"


@pytest.mark.unit
def test_every_known_concession_is_reported(report):
    assert len(report["concessions"]) == len(bpc.KNOWN_CONCESSIONS)
    assert report["known_concessions"] == len(bpc.KNOWN_CONCESSIONS)


@pytest.mark.integration
def test_operator_aliases_resolve_renamed_projects(report):
    """The project is titled 'Metropistas ...' while the operator is
    'Autopistas Metropolitanas de Puerto Rico'; without aliases it reads as an
    uncovered concession."""
    metro = next(
        e for e in report["concessions"] if e["operator"].startswith("Autopistas Metropolitanas")
    )
    assert metro["canonical"] is True
    assert metro["canonical_project_ids"]


@pytest.mark.integration
def test_only_site_extent_concessions_federate_a_location(report):
    """An island-wide concession must not report a location.

    Its municipality_id names the lead agency's administrative seat, and
    canonical_v1_bridge withholds it from the federated row; reporting it here
    would overstate what a downstream consumer receives.
    """
    for entry in report["concessions"]:
        if entry["spatial_extent"] != "site":
            assert entry["federates_location"] is False, entry["operator"]
        if entry["federates_location"]:
            assert entry["locatable"] is True, entry["operator"]


@pytest.mark.integration
def test_blocked_sources_are_declared(report):
    ids = {b["source_id"] for b in report["blocked_sources"]}
    assert ids == {"prasa_completed_projects_ppp", "prasa_consulting_engineer_ppp"}
    for blocked in report["blocked_sources"]:
        assert blocked["blocking_reason"]


@pytest.mark.integration
def test_documented_contract_values_are_non_negative(report):
    for entry in report["concessions"]:
        assert entry["contract_value_documented"] >= 0
        assert entry["contract_rows"] >= 0
