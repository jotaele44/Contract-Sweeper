"""Tests for the OCE dropzone ingest and real export layouts."""

from pathlib import Path

import pandas as pd
import pytest

from scripts import ingest_oce


@pytest.mark.unit
def test_no_raw_dir_writes_empty_headers(tmp_path):
    result = ingest_oce.run(root=tmp_path, force=True)
    assert result["status"] == "NO_FILES"
    donations = pd.read_csv(Path(result["path"]))
    reports = pd.read_csv(Path(result["reports_path"]))
    assert list(donations.columns) == ingest_oce.OUTPUT_COLUMNS
    assert list(reports.columns) == ingest_oce.REPORT_COLUMNS
    assert len(donations) == len(reports) == 0


@pytest.mark.unit
def test_spanish_column_mapping(tmp_path):
    raw = tmp_path / "data" / "raw" / "OCE"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "Nombre_Donante": "Civic Trust",
                "Cantidad": "2500",
                "Fecha": "2024-09-01",
                "Comite": "Comite OCE",
                "Partido": "PNP",
                "Ciudad": "Bayamon",
            },
            {
                "Nombre_Donante": "",
                "Cantidad": "100",
                "Fecha": "2024-09-02",
                "Comite": "Other",
                "Partido": "PPD",
                "Ciudad": "San Juan",
            },
        ]
    ).to_csv(raw / "oce_2024.csv", index=False)
    result = ingest_oce.run(root=tmp_path, force=True)
    assert result["rows"] == 1
    row = pd.read_csv(Path(result["path"]), dtype=str).iloc[0]
    assert row["donor_name"] == "Civic Trust"
    assert row["amount"] == "2500"
    assert row["party"] == "PNP"
    assert row["candidate_or_committee"] == "Comite OCE"


@pytest.mark.unit
def test_maps_socrata_api_field_names(tmp_path):
    raw = tmp_path / "data" / "raw" / "OCE"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "candidato": "PARTIDO INDEPENDENTISTA PUERTORRIQUEÑO",
                "candidatura": "Partido",
                "siglas": "PIP",
                "cantidad_donacion": "200",
                "metodo_donacion": "Cheque",
                "nombre_completo": "DAMARIS MANGUAL VELEZ",
                "donante_pueblo": "ARECIBO",
                "fecha_donacion": "2018-03-31T00:00:00.000",
                "descripcion_evento": "2018 - Año no eleccionario",
                "zip_code": "00612",
            }
        ]
    ).to_csv(raw / "oce.csv", index=False)
    result = ingest_oce.run(root=tmp_path, force=True)
    row = pd.read_csv(Path(result["path"]), dtype=str).iloc[0]
    assert row["donor_name"] == "DAMARIS MANGUAL VELEZ"
    assert row["candidate_or_committee"] == "PARTIDO INDEPENDENTISTA PUERTORRIQUEÑO"
    assert row["candidacy_type"] == "Partido"
    assert row["payment_method"] == "Cheque"
    assert row["party"] == "PIP"
    assert row["cycle"] == "2018"


@pytest.mark.unit
def test_maps_oce_donor_search_headers(tmp_path):
    raw = tmp_path / "data" / "raw" / "OCE"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "Nombre completo": "BANK FIRST",
                "Comité": "CARLOS MOLINA RODRIGUEZ",
                "Partido de afiliación": "PARTIDO NUEVO PROGRESISTA",
                "Fecha de donación": "2018-12-31",
                "Ciudad": "SAN JUAN",
                "Método de cobro": "Transferencia electrónica",
                "Cantidad": "2.98",
            }
        ]
    ).to_excel(raw / "donantes.xlsx", index=False)
    result = ingest_oce.run(root=tmp_path, force=True)
    row = pd.read_csv(Path(result["path"]), dtype=str).iloc[0]
    assert row["donor_name"] == "BANK FIRST"
    assert row["party"] == "PARTIDO NUEVO PROGRESISTA"
    assert row["payment_method"] == "Transferencia electrónica"


@pytest.mark.unit
def test_preserves_partial_oce_rows_without_amount(tmp_path):
    raw = tmp_path / "data" / "raw" / "OCE"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "cycle": "2018",
                "donor_name": "BANK FIRST",
                "donor_city": "SAN JUAN",
                "amount": "",
                "contribution_date": "2018-12-31",
                "source_file": "oce_historicos_2018_normalized.csv",
            },
            {
                "cycle": "2018",
                "donor_name": "",
                "amount": "",
                "contribution_date": "2018-12-31",
            },
        ]
    ).to_csv(raw / "pr_oce_donations.csv", index=False)
    result = ingest_oce.run(root=tmp_path, force=True)
    assert result["rows"] == 1
    row = pd.read_csv(Path(result["path"]), dtype=str).fillna("").iloc[0]
    assert row["donor_name"] == "BANK FIRST"
    assert row["amount"] == ""
    assert row["contribution_date"] == "2018-12-31"


@pytest.mark.unit
def test_report_exports_are_separated(tmp_path):
    raw = tmp_path / "data" / "raw" / "OCE"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "Comité": "COMITE X",
                "Número de informe": "IG-2024-1",
                "Tipo de informe": "Ingresos y gastos",
                "Evento electoral": "2024 Año Electoral",
                "Periodo del informe": "Julio a septiembre 2024",
                "Fecha de radicación": "2026-04-23 14:22:30",
            }
        ]
    ).to_excel(raw / "informes.xlsx", index=False)
    result = ingest_oce.run(root=tmp_path, force=True)
    assert result["rows"] == 0
    assert result["report_rows"] == 1
    reports = pd.read_csv(Path(result["reports_path"]), dtype=str)
    assert reports.iloc[0]["report_number"] == "IG-2024-1"
    assert reports.iloc[0]["filed_at"] == "2026-04-23"


@pytest.mark.unit
def test_cached_output_short_circuits(tmp_path):
    out_path = tmp_path / "data" / "staging" / "processed" / "pr_oce_donations.csv"
    out_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [{c: ("X" if c == "donor_name" else "") for c in ingest_oce.OUTPUT_COLUMNS}]
    ).to_csv(out_path, index=False)
    result = ingest_oce.run(root=tmp_path, force=False)
    assert result["status"] == "CACHED"
    assert result["rows"] == 1
