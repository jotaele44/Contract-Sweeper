"""Tests for the RDC detail-page enrichment pass (scripts.enrich_rdc_details).

Covers detail parsing, the resume/skip selection rules and the run chain with
the HTTP layer mocked out — no live network calls.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.enrich_rdc_details import (
    PARTY_COLUMNS,
    _merge_parties,
    _run,
    apply_detail,
    parse_detail,
    select_pending,
)
from scripts.scrape_rdc_demandas import DEMANDA_COLUMNS, OUT_PATH_REL

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED = "2026-08-16"
DETAIL_HTML = (FIXTURES / "rdc_detail.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit: detail parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_detail_reads_the_label_value_blocks():
    fields = parse_detail(DETAIL_HTML)["fields"]
    assert fields["case_number"] == "09"
    assert fields["epigrafe"] == "ALBERTO L. MALDONADO DIAZ vs. ADMINISTRACION DE CORRECCION"
    assert fields["resolucion_final"] == "Ganado"
    assert fields["fecha_resolucion_final"] == "10-Jul-2007"


@pytest.mark.unit
def test_detail_amounts_carry_full_precision():
    # The list view renders 400000.00; the detail page renders 400000.0000.
    fields = parse_detail(DETAIL_HTML)["fields"]
    assert fields["claimed_amount"] == "400000.0000"
    assert fields["adjudicated_amount"] == "0.0000"


@pytest.mark.unit
def test_the_registry_null_sentinel_becomes_a_blank():
    # Disposición renders "-No hay Información-" when unset. Downstream
    # consumers should not have to know that phrase.
    assert parse_detail(DETAIL_HTML)["fields"]["disposicion"] == ""


@pytest.mark.unit
def test_parse_detail_reads_every_party_role():
    parties = parse_detail(DETAIL_HTML)["parties"]
    by_role: dict[str, list[str]] = {}
    for party in parties:
        by_role.setdefault(party["party_role"], []).append(party["party_name"])

    assert by_role["demandante"] == ["ALBERTO L. MALDONADO DIAZ"]
    assert by_role["demandado"] == [
        "DEPARTAMENTO DE CORRECCION",
        "MIGUEL PEREIRA CASTILLO Y OTROS",
    ]
    assert by_role["representante_demandado"] == ["AROCHO PENDAS, SARELY [CONT]"]


@pytest.mark.unit
def test_multiple_defendants_are_ordinal_numbered_not_collapsed():
    defendants = [p for p in parse_detail(DETAIL_HTML)["parties"] if p["party_role"] == "demandado"]
    assert [p["party_ordinal"] for p in defendants] == [1, 2]


@pytest.mark.unit
def test_an_empty_party_cell_yields_no_row():
    # Representante de Demandante is present but blank on this case; emitting a
    # nameless party row would assert a representative that does not exist.
    roles = {p["party_role"] for p in parse_detail(DETAIL_HTML)["parties"]}
    assert "representante_demandante" not in roles


@pytest.mark.unit
def test_parse_detail_on_a_broken_page_returns_empty_rather_than_raising():
    # A single bad case must not kill a multi-hour run.
    assert parse_detail("<html><body>Error</body></html>") == {"fields": {}, "parties": []}
    assert parse_detail("") == {"fields": {}, "parties": []}


# ---------------------------------------------------------------------------
# Unit: merging a detail page into its case row
# ---------------------------------------------------------------------------


def _blank_row(**overrides) -> dict:
    row = {col: "" for col in DEMANDA_COLUMNS}
    row.update(overrides)
    return row


@pytest.mark.unit
def test_apply_detail_promotes_the_defendant_to_the_structured_value():
    row = _blank_row(
        defendant_name="ADMINISTRACION DE CORRECCION",
        defendant_attribution_method="caption_parse",
        review_status="needs_review",
    )
    updated = apply_detail(row, parse_detail(DETAIL_HTML), ambiguous=False, fetched_on=FETCHED)

    assert updated["defendant_name"] == "DEPARTAMENTO DE CORRECCION"
    assert updated["defendant_count"] == "2"
    assert updated["defendant_attribution_method"] == "detail_page"
    assert updated["review_status"] == "verified"
    assert updated["detail_fetched_at"] == FETCHED


@pytest.mark.unit
def test_a_blank_detail_value_never_erases_a_populated_list_value():
    row = _blank_row(disposicion="SOMETHING FROM THE LIST VIEW")
    updated = apply_detail(row, parse_detail(DETAIL_HTML), ambiguous=False, fetched_on=FETCHED)
    # Disposición is the null sentinel on this page, so the list value stands.
    assert updated["disposicion"] == "SOMETHING FROM THE LIST VIEW"


@pytest.mark.unit
def test_a_row_fetched_by_an_ambiguous_key_is_not_marked_verified():
    # The detail route keys on Núm del Caso alone, so for a shared value the
    # app may have served a different case entirely.
    updated = apply_detail(
        _blank_row(), parse_detail(DETAIL_HTML), ambiguous=True, fetched_on=FETCHED
    )
    assert updated["review_status"] == "ambiguous_key"


@pytest.mark.unit
def test_a_case_with_no_defendant_is_still_marked_read():
    """Some cases genuinely name no Demandado.

    Observed live: "IN RE: DELIRIS CASTAÑER FUENTES" (a bankruptcy) and
    "MUNICIPIO DE CAYEY vs." (the government is the plaintiff). Marking a case
    done by the presence of a defendant would re-fetch these on every run
    forever, so detail_fetched_at is what closes the row.
    """
    parsed = {
        "fields": {"resolucion_final": "Ganado"},
        "parties": [
            {"party_role": "demandante", "party_ordinal": 1, "party_name": "MUNICIPIO DE CAYEY"}
        ],
    }
    updated = apply_detail(_blank_row(), parsed, ambiguous=False, fetched_on=FETCHED)

    assert updated["detail_fetched_at"] == FETCHED
    assert updated["defendant_count"] == "0"
    # No defendant exists to attribute, so no attribution is claimed...
    assert updated["defendant_attribution_method"] == ""
    # ...the row is not called verified, which would overstate it...
    assert updated["review_status"] == "no_defendant_listed"
    # ...but it is not pending any more either.
    assert select_pending(pd.DataFrame([updated])).empty


@pytest.mark.unit
def test_an_uncorroborated_caption_candidate_is_not_marked_verified():
    """A caption guess the detail page did not confirm must not read as confirmed.

    Observed live on a 3-page sweep: one case kept its caption-parsed defendant
    while its detail page listed no Demandado at all. Marking that "verified"
    would contradict defendant_count=0.
    """
    row = _blank_row(
        defendant_name="SOME AGENCY FROM THE CAPTION",
        defendant_attribution_method="caption_parse",
    )
    updated = apply_detail(row, {"fields": {}, "parties": []}, ambiguous=False, fetched_on=FETCHED)
    assert updated["review_status"] == "no_defendant_listed"
    assert updated["defendant_attribution_method"] == "caption_parse"
    assert updated["defendant_count"] == "0"


# ---------------------------------------------------------------------------
# Unit: resume / skip selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_select_pending_skips_rows_whose_detail_page_was_already_read():
    frame = pd.DataFrame(
        {
            "rdc_case_uid": ["a", "b"],
            "detail_fetched_at": ["2026-08-16", ""],
            "case_number_ambiguous": ["false", "false"],
        }
    )
    assert list(select_pending(frame)["rdc_case_uid"]) == ["b"]


@pytest.mark.unit
def test_select_pending_skips_ambiguous_case_numbers_by_default():
    frame = pd.DataFrame(
        {
            "rdc_case_uid": ["a", "b"],
            "detail_fetched_at": ["", ""],
            "case_number_ambiguous": ["true", "false"],
        }
    )
    assert list(select_pending(frame)["rdc_case_uid"]) == ["b"]
    assert list(select_pending(frame, include_ambiguous=True)["rdc_case_uid"]) == ["a", "b"]


# ---------------------------------------------------------------------------
# Unit: party merge
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_re_enriching_a_case_replaces_its_parties_instead_of_duplicating_them():
    existing = pd.DataFrame(
        [
            {
                "rdc_case_uid": "a",
                "case_number": "09",
                "party_role": "demandado",
                "party_ordinal": "1",
                "party_name": "OLD AGENCY",
                "source_system": "rdc_demandas_civiles",
                "source_url": "u",
            },
            {
                "rdc_case_uid": "b",
                "case_number": "10",
                "party_role": "demandado",
                "party_ordinal": "1",
                "party_name": "UNTOUCHED",
                "source_system": "rdc_demandas_civiles",
                "source_url": "u",
            },
        ]
    )
    new_rows = [
        {
            "rdc_case_uid": "a",
            "case_number": "09",
            "party_role": "demandado",
            "party_ordinal": "1",
            "party_name": "NEW AGENCY",
            "source_system": "rdc_demandas_civiles",
            "source_url": "u",
        }
    ]
    merged = _merge_parties(existing, new_rows, {"a"})

    assert list(merged.columns) == PARTY_COLUMNS
    names = dict(zip(merged["rdc_case_uid"], merged["party_name"]))
    assert names["a"] == "NEW AGENCY"
    assert names["b"] == "UNTOUCHED"
    assert len(merged) == 2


# ---------------------------------------------------------------------------
# Integration: run chain (HTTP mocked)
# ---------------------------------------------------------------------------


class _FakeSession:
    def close(self):
        pass


def _seed_cases(root: Path) -> Path:
    case_path = root / OUT_PATH_REL
    case_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            **{col: "" for col in DEMANDA_COLUMNS},
            "rdc_case_uid": "uid-09",
            "case_number": "09",
            "epigrafe": "ALBERTO L. MALDONADO DIAZ vs. ADMINISTRACION DE CORRECCION",
            "claimed_amount": "400000.00",
            "defendant_name": "ADMINISTRACION DE CORRECCION",
            "defendant_attribution_method": "caption_parse",
            "review_status": "needs_review",
            "case_number_ambiguous": "false",
            "detail_url": "https://justicia1.justicia.pr.gov/rdc/Home/Details/09",
        }
    ]
    pd.DataFrame(rows, columns=DEMANDA_COLUMNS).to_csv(case_path, index=False)
    return case_path


@pytest.mark.integration
def test_run_enriches_the_case_file_and_writes_the_parties_file(tmp_path, monkeypatch):
    case_path = _seed_cases(tmp_path)
    monkeypatch.setattr(
        "scripts.enrich_rdc_details._fetch_detail",
        lambda session, url, logger: DETAIL_HTML,
    )
    monkeypatch.setattr("scripts.enrich_rdc_details.build_session", lambda *a, **k: _FakeSession())

    result = _run(root=tmp_path)
    assert result["status"] == "OK"
    assert result["enriched"] == 1
    assert result["pending"] == 0

    cases = pd.read_csv(case_path, dtype=str)
    assert cases.loc[0, "defendant_name"] == "DEPARTAMENTO DE CORRECCION"
    assert cases.loc[0, "defendant_count"] == "2"
    assert cases.loc[0, "review_status"] == "verified"
    # post_ingest is re-run, so the canonical companion tracks the full-precision
    # detail amount rather than the list value.
    assert cases.loc[0, "claimed_amount_canonical"] == "400000.0"

    parties = pd.read_csv(tmp_path / "data/staging/processed/pr_rdc_demandas_parties.csv")
    assert len(parties) == 4
    assert set(parties["rdc_case_uid"]) == {"uid-09"}


@pytest.mark.integration
def test_a_second_run_is_a_no_op_because_the_row_is_already_enriched(tmp_path, monkeypatch):
    _seed_cases(tmp_path)
    calls = []

    def fake_fetch(session, url, logger):
        calls.append(url)
        return DETAIL_HTML

    monkeypatch.setattr("scripts.enrich_rdc_details._fetch_detail", fake_fetch)
    monkeypatch.setattr("scripts.enrich_rdc_details.build_session", lambda *a, **k: _FakeSession())

    _run(root=tmp_path)
    _run(root=tmp_path)
    assert len(calls) == 1  # resumed, not re-fetched


@pytest.mark.integration
def test_limit_bounds_the_run(tmp_path, monkeypatch):
    _seed_cases(tmp_path)
    monkeypatch.setattr(
        "scripts.enrich_rdc_details._fetch_detail", lambda session, url, logger: DETAIL_HTML
    )
    monkeypatch.setattr("scripts.enrich_rdc_details.build_session", lambda *a, **k: _FakeSession())

    result = _run(root=tmp_path, limit=0)
    assert result["enriched"] == 0
    assert result["pending"] == 1


@pytest.mark.integration
def test_a_failed_fetch_leaves_the_row_pending(tmp_path, monkeypatch):
    _seed_cases(tmp_path)
    monkeypatch.setattr(
        "scripts.enrich_rdc_details._fetch_detail", lambda session, url, logger: None
    )
    monkeypatch.setattr("scripts.enrich_rdc_details.build_session", lambda *a, **k: _FakeSession())

    result = _run(root=tmp_path)
    assert result["enriched"] == 0
    assert result["failed"] == 1
    assert result["pending"] == 1


@pytest.mark.integration
def test_run_without_a_case_file_fails_with_a_pointer_to_the_sweep(tmp_path):
    result = _run(root=tmp_path)
    assert result["status"] == "ERROR"
    assert "scrape_rdc_demandas" in result["errors"][0]


# ---------------------------------------------------------------------------
# Regression: canonical amounts must track the detail page, not the list view
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_canonical_amounts_are_recomputed_from_the_detail_page(tmp_path, monkeypatch):
    """apply_post_ingest skips money columns that already have a canonical twin.

    The list sweep writes those twins, so without an explicit drop the enriched
    row would carry a detail-sourced raw amount beside a list-sourced numeric,
    and every downstream total would use the stale one.
    """
    case_path = tmp_path / OUT_PATH_REL
    case_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        **{col: "" for col in DEMANDA_COLUMNS},
        "rdc_case_uid": "uid-09",
        "case_number": "09",
        "claimed_amount": "1.00",  # stale list value
        "detail_url": "https://justicia1.justicia.pr.gov/rdc/Home/Details/09",
        "case_number_ambiguous": "false",
    }
    frame = pd.DataFrame([row], columns=DEMANDA_COLUMNS)
    frame["claimed_amount_canonical"] = "1.0"
    frame["adjudicated_amount_canonical"] = "0.0"
    frame.to_csv(case_path, index=False)

    monkeypatch.setattr(
        "scripts.enrich_rdc_details._fetch_detail", lambda session, url, logger: DETAIL_HTML
    )
    monkeypatch.setattr("scripts.enrich_rdc_details.build_session", lambda *a, **k: _FakeSession())
    _run(root=tmp_path)

    out = pd.read_csv(case_path, dtype=str)
    # Detail page says 400000.0000; the raw column and its canonical twin agree.
    assert out.loc[0, "claimed_amount"] == "400000.0000"
    assert float(out.loc[0, "claimed_amount_canonical"]) == 400000.0
