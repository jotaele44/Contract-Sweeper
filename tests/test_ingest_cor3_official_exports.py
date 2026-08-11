from __future__ import annotations

import pandas as pd

from scripts.ingest_cor3 import (
    OUTPUT_COLUMNS,
    _deduplicate_projects,
    _map_col,
    _parse_sheet,
)


def test_map_col_is_accent_and_case_insensitive() -> None:
    frame = pd.DataFrame(columns=["NÚMERO DEL PW", "Nombre del Solicitante"])

    assert _map_col(frame, ["Número del PW"]) == "NÚMERO DEL PW"
    assert _map_col(frame, ["nombre del solicitante"]) == "Nombre del Solicitante"


def test_parse_official_pa_spanish_headers() -> None:
    frame = pd.DataFrame(
        [
            {
                "Número del PW": "PA-02-PR-3384-PW-00001",
                "Versión": "5",
                "Nombre del Desastre": "Huracán Irma (4336)",
                "Nombre del Solicitante": "Departamento de la Policía de PR",
                "Categoría": "Categoría B",
                "Cantidad Obligada": "1,413,971",
                "Cantidad Desembolsada": "3525042",
                "Fecha de Última Actualización": "08/07/2026",
            }
        ]
    )

    parsed = _parse_sheet(frame, "COR3 PA_110726_0836.xlsx")

    assert len(parsed) == 1
    assert parsed.iloc[0]["project_id"] == "PA-02-PR-3384-PW-00001"
    assert parsed.iloc[0]["applicant_name"] == "Departamento de la Policía de PR"
    assert parsed.iloc[0]["program"] == "Huracán Irma (4336)"
    assert parsed.iloc[0]["total_approved"] == "1413971"
    assert parsed.iloc[0]["total_disbursed"] == "3525042"
    assert parsed.iloc[0]["last_updated"] == "08/07/2026"
    assert parsed.iloc[0]["_source_version"] == "5"


def test_summary_only_sheet_is_rejected() -> None:
    frame = pd.DataFrame([{"Programa": "Asistencia Pública", "Asignado": "$10", "Obligado": "$9"}])

    parsed = _parse_sheet(frame, "COR3 Resumen_Financiero.xlsx")

    assert parsed.empty


def test_deduplicate_projects_keeps_highest_version_not_first_or_last() -> None:
    rows = []
    for version, approved in [("0", "100"), ("5", "500"), ("4", "400")]:
        row = {column: "" for column in OUTPUT_COLUMNS}
        row.update(
            {
                "project_id": "PA-TEST-1",
                "applicant_name": "Municipio de Prueba",
                "applicant_normalized": "MUNICIPIO DE PRUEBA",
                "total_approved": approved,
                "total_disbursed": "0",
                "_source_version": version,
            }
        )
        rows.append(row)

    deduped, removed = _deduplicate_projects(pd.DataFrame(rows))

    assert removed == 2
    assert len(deduped) == 1
    assert deduped.iloc[0]["total_approved"] == "500"
    assert list(deduped.columns) == OUTPUT_COLUMNS


def test_deduplicate_projects_keeps_missing_project_ids_as_unkeyed_rows() -> None:
    rows = []
    for applicant, approved in [("Municipio A", "100"), ("Municipio B", "200")]:
        row = {column: "" for column in OUTPUT_COLUMNS}
        row.update(
            {
                "project_id": float("nan"),
                "applicant_name": applicant,
                "applicant_normalized": applicant.upper(),
                "total_approved": approved,
                "total_disbursed": "0",
                "_source_version": "1",
            }
        )
        rows.append(row)

    deduped, removed = _deduplicate_projects(pd.DataFrame(rows))

    assert removed == 0
    assert len(deduped) == 2
    assert set(deduped["applicant_name"]) == {"Municipio A", "Municipio B"}
