"""Offline normalization tests for the Compras PR (comprashpr.com / ASG) producer.

The live portal is scraped over the network, so these tests exercise only the
pure record-normalization layer with synthetic ASG-shaped records (Spanish
field names, subasta terminology). They guard the bid-signal deepening: an open
subasta must surface its opening date, notice type, category, place, and a
citable source URL rather than silently dropping them.
"""

from __future__ import annotations

import importlib

import pytest

compras = importlib.import_module("scripts.download_compras")


@pytest.mark.unit
def test_rfp_normalizer_keys_match_columns():
    """Normalizer output keys must exactly match RFP_COLUMNS so the DataFrame
    written by run() neither drops fields nor emits empty phantom columns."""
    row = compras._normalize_rfp({})
    assert set(row) == set(compras.RFP_COLUMNS)


@pytest.mark.unit
def test_rfp_subasta_bid_signal_fields_captured():
    """A Spanish-keyed subasta record populates the pre-award bid-signal fields."""
    record = {
        "numero_subasta": "SUB-2025-014",
        "titulo": "Adquisición de equipo médico",
        "agencia": "Administración de Servicios Generales",
        "fecha_publicacion": "2025-06-01",
        "fecha_apertura": "2025-07-15",  # bid opening — previously dropped
        "presupuesto": "1,250,000.00",
        "estado": "Abierta",
        "tipo": "Subasta Formal",
        "categoria": "Equipo Médico",
        "municipio": "San Juan",
        "enlace": "https://www.comprashpr.com/subasta/SUB-2025-014",
    }
    row = compras._normalize_rfp(record)
    assert row["rfp_id"] == "SUB-2025-014"
    assert row["due_date"] == "2025-07-15"  # apertura mapped to bid deadline
    assert row["notice_type"] == "Subasta Formal"
    assert row["category"] == "Equipo Médico"
    assert row["municipality"] == "San Juan"
    assert row["source_url"].endswith("SUB-2025-014")
    assert row["estimated_value"] == pytest.approx(1_250_000.00)
    assert row["status"] == "Abierta"


@pytest.mark.unit
def test_rfp_english_deadline_still_maps():
    """English closing_date/due_date keys keep working (no regression)."""
    row = compras._normalize_rfp({"rfp_id": "R-1", "closing_date": "2025-08-01"})
    assert row["due_date"] == "2025-08-01"


@pytest.mark.unit
def test_award_normalizer_keys_match_columns():
    row = compras._normalize_award({})
    assert set(row) == set(compras.AWARD_COLUMNS)
