from pathlib import Path

import pandas as pd
import pytest

from scripts import ingest_donaciones


@pytest.mark.unit
def test_maps_actual_historical_search_headers(tmp_path):
    raw = tmp_path / "data" / "raw" / "Donaciones"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "Nombre completo": "CIVIC TRUST",
                "Comité": "COMITE LOCAL",
                "Partido de afiliación": "PARTIDO X",
                "Fecha de donación": "2018-12-31",
                "Ciudad": "SAN JUAN",
                "Método de cobro": "Transferencia electrónica",
                "Cantidad": "$2,500.00",
            }
        ]
    ).to_excel(raw / "historicos.xlsx", index=False)

    result = ingest_donaciones.run(root=tmp_path, force=True)
    assert result["status"] == "OK"
    out = pd.read_csv(Path(result["path"]), dtype=str)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["donor_name"] == "CIVIC TRUST"
    assert row["candidate_or_committee"] == "COMITE LOCAL"
    assert row["party"] == "PARTIDO X"
    assert row["payment_method"] == "Transferencia electrónica"
    assert row["amount"] == "2500"
    assert row["contribution_date"] == "2018-12-31"
    assert row["cycle"] == "2018"


@pytest.mark.unit
def test_deduplicates_same_donation_across_exports(tmp_path):
    raw = tmp_path / "data" / "raw" / "Donaciones"
    raw.mkdir(parents=True)
    row = {
        "Nombre completo": "A",
        "Comité": "B",
        "Fecha de donación": "2024-01-02",
        "Cantidad": "10",
        "Partido de afiliación": "P",
    }
    pd.DataFrame([row]).to_csv(raw / "a.csv", index=False)
    pd.DataFrame([row]).to_csv(raw / "b.csv", index=False)
    result = ingest_donaciones.run(root=tmp_path, force=True)
    assert result["rows"] == 1
    assert result["deduplicated_rows"] == 1
