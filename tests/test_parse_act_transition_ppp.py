"""Tests for the ACT/ACUDEN transition-report P3 concession extractor.

The workbook is committed, so these run offline against real data.
"""

from __future__ import annotations

import pytest

from moneysweep.validation import canonical_v1_schema as cv1
from scripts import parse_act_transition_ppp as pp

REPO_ROOT = cv1.REPO_ROOT


@pytest.fixture(scope="module")
def rows():
    return pp.build_rows(REPO_ROOT)


@pytest.mark.integration
def test_extracts_concession_contracts(rows):
    assert rows, "expected concession rows from the committed transition workbook"
    assert all(r["concessionaire"] for r in rows)
    assert set(r["concessionaire"] for r in rows) <= {
        c["concessionaire"] for c in pp.CONCESSIONAIRES.values()
    }


@pytest.mark.integration
def test_metropistas_name_variants_collapse(rows):
    """'... LLC' and '... LLC.' are one concessionaire, not two."""
    variants = {
        r["vendor_name"]
        for r in rows
        if r["concessionaire"] == "Autopistas Metropolitanas de Puerto Rico"
    }
    assert len(variants) > 1, "expected the report's punctuation variants"
    metro = [
        r for r in rows if r["concessionaire"] == "Autopistas Metropolitanas de Puerto Rico"
    ]
    assert len({r["concessionaire"] for r in metro}) == 1


@pytest.mark.unit
def test_unrelated_contractors_are_not_matched():
    """A keyword sweep pulls these in; the controlled name list must not.

    'Generación Futura' matches a naive search for 'genera', and an ordinary
    road-repair firm is not a concessionaire.
    """
    for name in [
        "Generación Futura Inc",
        "Obratec Contratista General, Inc.",
        "Municipio de Coamo",
        "",
    ]:
        assert pp._match_concessionaire(name) is None, name


@pytest.mark.unit
def test_known_concessionaires_match_with_suffix_noise():
    for name in [
        "AUTOPISTAS METROPOLITANAS DE PUERTO RICO, LLC",
        "AUTOPISTAS METROPOLITANAS DE PUERTO RICO, LLC.",
        "Aerostar Airport Holdings LLC",
    ]:
        assert pp._match_concessionaire(name) is not None, name


@pytest.mark.integration
def test_rows_carry_provenance(rows):
    """Every row must trace back to a page of a named source PDF."""
    for r in rows:
        assert r["source_file"].endswith(".pdf"), r
        assert r["source_page"], r
        assert r["contract_id"], r


@pytest.mark.integration
def test_output_columns_stable(rows):
    for r in rows:
        assert list(r.keys()) == pp.OUT_COLUMNS
