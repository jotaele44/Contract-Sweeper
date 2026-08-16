"""Tests for the RDC civil-claims registry sweep (scripts.scrape_rdc_demandas).

Covers the pure table/caption/identity transforms and the pagination + run
chain with the HTTP layer mocked out — no live network calls.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.scrape_rdc_demandas import (
    DEMANDA_COLUMNS,
    _carry_forward_first_seen,
    _normalize_row,
    _run,
    case_uid,
    declared_last_page,
    fetch_all_records,
    flag_ambiguous_case_numbers,
    parse_caption,
    parse_rows,
)

FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "rdc_list_page.html").read_text(encoding="utf-8")
PAST_END_HTML = (FIXTURES / "rdc_list_page_past_end.html").read_text(encoding="utf-8")

TODAY = "2026-08-16"


class _NullLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


# ---------------------------------------------------------------------------
# Unit: table parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_rows_reads_every_data_row_and_strips_the_padding():
    rows = parse_rows(LIST_HTML)
    assert len(rows) == 4
    # The registry pads every cell ("09             ").
    assert [r["case_number"] for r in rows] == ["00-127-0034PAN", "05-00829", "09", "1000"]
    assert rows[2]["causa_de_accion"] == "Violación Derechos Civiles / Confinados"
    assert rows[2]["claimed_amount"] == "400000.00"
    assert rows[2]["resolucion_final"] == "Ganado"
    assert rows[2]["fecha_resolucion_final"] == "10-Jul-2007"


@pytest.mark.unit
def test_parse_rows_captures_the_detail_href_rather_than_rebuilding_it():
    # The href is the exact route key the detail page is addressed by;
    # reconstructing it from the case-number column would guess at encoding.
    rows = parse_rows(LIST_HTML)
    assert rows[0]["detail_href"] == "/rdc/Home/Details/00-127-0034PAN"
    assert rows[2]["detail_href"] == "/rdc/Home/Details/09"


@pytest.mark.unit
def test_a_page_past_the_end_parses_to_no_rows():
    # RDC answers 200 with an empty tbody instead of clamping to the last page,
    # which is what makes "no rows" a safe stop condition.
    assert parse_rows(PAST_END_HTML) == []


@pytest.mark.unit
def test_a_page_without_the_table_returns_empty_rather_than_raising():
    assert parse_rows("<html><body><h1>Error</h1></body></html>") == []
    assert parse_rows("") == []


@pytest.mark.unit
def test_declared_last_page_reads_the_ultima_link():
    assert declared_last_page(LIST_HTML) == 7451


@pytest.mark.unit
def test_declared_last_page_tolerates_a_page_without_an_ultima_link():
    # Out-of-range pages render Primera/Anterior only. Absence is not an error:
    # termination is driven by the empty page, not by this marker.
    assert declared_last_page(PAST_END_HTML) is None
    assert declared_last_page("<html><body>no pager</body></html>") is None


# ---------------------------------------------------------------------------
# Unit: caption parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_caption_parse_splits_an_ordinary_epigrafe():
    assert parse_caption("ALBERTO L. MALDONADO DIAZ vs. ADMINISTRACION DE CORRECCION") == (
        "ALBERTO L. MALDONADO DIAZ",
        "ADMINISTRACION DE CORRECCION",
    )


@pytest.mark.unit
def test_caption_parse_handles_an_agency_as_plaintiff():
    """The registry also carries cases the government brought.

    Reading the agency as the plaintiff is a correct reading of the caption,
    not a parse failure — deciding which side is a government entity is entity
    resolution's job, not this parser's.
    """
    plaintiff, defendant = parse_caption(
        "ADM. DESARROLLO SOCIO ECONOMICO FAMILIA VS EVELYN HERNANDEZ ORTIZ  REG.44"
    )
    assert plaintiff == "ADM. DESARROLLO SOCIO ECONOMICO FAMILIA"
    assert defendant == "EVELYN HERNANDEZ ORTIZ REG.44"


@pytest.mark.unit
@pytest.mark.parametrize(
    "caption",
    [
        "IN RE: DELIRIS CASTAÑER FUENTES",  # bankruptcy, no separator at all
        "A vs B vs C",  # compound a naive split would mangle
        "vs. ADMINISTRACION DE CORRECCION",  # no plaintiff side
        "",
    ],
)
def test_caption_parse_leaves_a_blank_rather_than_guessing(caption):
    assert parse_caption(caption) == ("", "")


@pytest.mark.unit
def test_caption_separator_does_not_fire_inside_a_name():
    # "vs" must stand alone as a token, or names containing those letters split.
    assert parse_caption("ALVSTON CORP") == ("", "")


@pytest.mark.unit
def test_an_unparseable_caption_claims_no_attribution_method():
    # Claiming caption_parse for a row where nothing was parsed would assert an
    # attribution that does not exist.
    row = _normalize_row(parse_rows(LIST_HTML)[1], TODAY)  # the "IN RE:" row
    assert row["defendant_name"] == ""
    assert row["defendant_attribution_method"] == ""


# ---------------------------------------------------------------------------
# Unit: identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_case_uid_is_stable_across_whitespace_variation():
    assert case_uid("09", "X vs Y", "Daños") == case_uid("  09  ", "X vs Y", "Daños")


@pytest.mark.unit
def test_case_uid_separates_cases_that_share_a_case_number():
    # Núm del Caso alone is not unique across the registry — "09" and "1000"
    # recur — so identity has to include the caption.
    assert case_uid("09", "A vs B", "Daños") != case_uid("09", "C vs D", "Daños")


@pytest.mark.unit
def test_ambiguous_case_numbers_are_flagged_on_every_sharing_row():
    frame = pd.DataFrame(
        {
            "case_number": ["09", "09", "1000"],
            "case_number_ambiguous": ["false", "false", "false"],
        }
    )
    flagged = flag_ambiguous_case_numbers(frame)
    assert list(flagged["case_number_ambiguous"]) == ["true", "true", "false"]


@pytest.mark.unit
def test_normalize_row_emits_exactly_the_declared_columns():
    row = _normalize_row(parse_rows(LIST_HTML)[2], TODAY)
    assert list(row.keys()) == DEMANDA_COLUMNS
    assert row["detail_url"] == "https://justicia1.justicia.pr.gov/rdc/Home/Details/09"
    assert row["review_status"] == "needs_review"
    assert row["defendant_attribution_method"] == "caption_parse"
    # The raw money string is preserved; post_ingest adds the parsed companion.
    assert row["claimed_amount"] == "400000.00"


@pytest.mark.unit
def test_defendant_count_is_left_to_the_detail_pass():
    # The list view names no parties, so it cannot know how many there are.
    row = _normalize_row(parse_rows(LIST_HTML)[2], TODAY)
    assert row["defendant_count"] == ""


# ---------------------------------------------------------------------------
# Unit: first_seen_at
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_first_seen_at_is_preserved_for_cases_we_have_seen_before(tmp_path):
    """first_seen_at is only an upper bound on entry if it never moves.

    The registry renders no filing date, so re-stamping every row each run
    would turn this into "the date we last scraped".
    """
    out_path = tmp_path / "cases.csv"
    rows = [_normalize_row(r, TODAY) for r in parse_rows(LIST_HTML)]

    first = _carry_forward_first_seen(pd.DataFrame(rows), out_path, "2026-01-15")
    first.to_csv(out_path, index=False)
    assert set(first["first_seen_at"]) == {"2026-01-15"}

    newcomer = {**rows[0], "rdc_case_uid": "ffffffffffffffff"}
    second = _carry_forward_first_seen(pd.DataFrame([*rows, newcomer]), out_path, "2026-08-16")
    seen = dict(zip(second["rdc_case_uid"], second["first_seen_at"]))

    assert seen[rows[0]["rdc_case_uid"]] == "2026-01-15"  # kept, not re-stamped
    assert seen["ffffffffffffffff"] == "2026-08-16"  # only the new row is dated


# ---------------------------------------------------------------------------
# Integration: pagination + run chain (HTTP mocked)
# ---------------------------------------------------------------------------


def _page_html(case_numbers: list[str]) -> str:
    rows = "".join(
        f"<tr><td>PARTE {i} vs. AGENCIA {i}</td><td>{cn}</td><td>Daños y Perjuicios</td>"
        f"<td>1000.00</td><td>0.00</td><td></td><td></td><td></td>"
        f'<td><a href="/rdc/Home/Details/{cn}">Ver</a></td></tr>'
        for i, cn in enumerate(case_numbers)
    )
    return f"<html><body><table><tbody>{rows}</tbody></table></body></html>"


@pytest.mark.integration
def test_fetch_all_records_walks_until_a_page_comes_back_empty(monkeypatch):
    pages = {
        1: _page_html(["A-1", "A-2"]),
        2: _page_html(["A-3"]),
        3: PAST_END_HTML,
    }
    calls = []

    def fake_fetch_page(session, page, logger):
        calls.append(page)
        return pages[page]

    monkeypatch.setattr("scripts.scrape_rdc_demandas._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, logger=_NullLogger())

    assert calls == [1, 2, 3]
    assert len(records) == 3
    assert truncated is False


@pytest.mark.integration
def test_start_page_lets_the_append_ordered_tail_be_reswept(monkeypatch):
    # The registry appends new cases at the end, so a high start page re-sweeps
    # only recent ones instead of the whole 7,451-page corpus.
    pages = {7400: _page_html(["Z-1"]), 7401: PAST_END_HTML}
    calls = []

    def fake_fetch_page(session, page, logger):
        calls.append(page)
        return pages[page]

    monkeypatch.setattr("scripts.scrape_rdc_demandas._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, logger=_NullLogger(), start_page=7400)

    assert calls == [7400, 7401]
    assert len(records) == 1
    assert truncated is False


@pytest.mark.integration
def test_max_pages_bounds_a_smoke_test(monkeypatch):
    calls = []

    def fake_fetch_page(session, page, logger):
        calls.append(page)
        return _page_html([f"B-{page}"])

    monkeypatch.setattr("scripts.scrape_rdc_demandas._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, logger=_NullLogger(), max_pages=3)

    assert calls == [1, 2, 3]
    assert len(records) == 3
    assert truncated is False


@pytest.mark.integration
def test_a_failed_page_marks_the_result_truncated(monkeypatch):
    def fake_fetch_page(session, page, logger):
        return _page_html(["C-1"]) if page == 1 else None

    monkeypatch.setattr("scripts.scrape_rdc_demandas._fetch_page", fake_fetch_page)
    records, truncated = fetch_all_records(session=None, logger=_NullLogger())

    assert len(records) == 1
    assert truncated is True


@pytest.mark.integration
def test_run_writes_the_declared_columns_and_the_canonical_money_companions(tmp_path, monkeypatch):
    pages = {1: LIST_HTML, 2: PAST_END_HTML}
    monkeypatch.setattr(
        "scripts.scrape_rdc_demandas._fetch_page",
        lambda session, page, logger: pages[page],
    )
    monkeypatch.setattr("scripts.scrape_rdc_demandas.build_session", lambda *a, **k: _FakeSession())

    result = _run(root=tmp_path, force=True)
    assert result["status"] == "OK"
    assert result["rows"] == 4

    frame = pd.read_csv(Path(result["path"]), dtype=str)
    assert set(DEMANDA_COLUMNS) <= set(frame.columns)
    # post_ingest picks these up because the columns are named to match its
    # AMOUNT_COLUMNS tuple.
    assert "claimed_amount_canonical" in frame.columns
    assert "adjudicated_amount_canonical" in frame.columns
    assert frame.loc[frame["case_number"] == "09", "claimed_amount_canonical"].iloc[0] == "400000.0"


@pytest.mark.integration
def test_run_reports_an_error_when_the_registry_yields_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.scrape_rdc_demandas._fetch_page",
        lambda session, page, logger: PAST_END_HTML,
    )
    monkeypatch.setattr("scripts.scrape_rdc_demandas.build_session", lambda *a, **k: _FakeSession())

    result = _run(root=tmp_path, force=True)
    assert result["status"] == "ERROR"
    assert result["rows"] == 0


class _FakeSession:
    def close(self):
        pass
