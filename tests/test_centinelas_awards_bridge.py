"""Tests for the Centinelas pre-official -> funding_awards federation bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moneysweep.federation.centinelas_awards_bridge import (
    build_centinelas_streams,
    merge_centinelas_awards,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "moneysweep_funding_award.schema.json").read_text(encoding="utf-8")
)

_CANDIDATE = {
    "award_id": "CS-CENT-e2e001",
    "centinelas_item_id": "e2e001",
    "amount": 1250000.0,
    "currency": "USD",
    "award_date": "2026-07-10",
    "recipient_entity_id": "Administracion de Servicios Generales",
    "funding_agency_entity_id": "Administracion de Servicios Generales",
    "source_id": "centinelas-pr",
    "synthetic": False,
    "location": {
        "municipality_name": "San Juan",
        "municipality_code": "72127",
        "county_fips": "72127",
        "attribution_source": "centinelas_signal",
        "attribution_confidence": "exact_name",
    },
    "lineage": {
        "producer_script": "moneysweep/runtime/centinelas_intake.py",
        "source_inputs": ["https://noticias.pr/subasta-asg"],
    },
}


def _write_candidates(root: Path, rows: list[dict]) -> None:
    d = root / "exports" / "centinelas_intake"
    d.mkdir(parents=True, exist_ok=True)
    (d / "funding_awards.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def test_absent_candidates_is_noop(tmp_path):
    streams = {"sources": [], "entities": [], "relationships": []}
    added = merge_centinelas_awards(streams, root=tmp_path, now="2026-07-11T00:00:00+00:00")
    assert added == 0
    assert "funding_awards" not in streams  # optional stream stays absent


def test_candidate_maps_to_valid_funding_award(tmp_path):
    _write_candidates(tmp_path, [_CANDIDATE])
    built = build_centinelas_streams(root=tmp_path, now="2026-07-11T00:00:00+00:00")
    assert len(built["funding_awards"]) == 1
    award = built["funding_awards"][0]

    # Required keys present, id patterns + types correct.
    required = set(_SCHEMA["required"])
    assert required <= set(award), f"missing {required - set(award)}"
    import re

    assert re.match(r"^awd_[a-f0-9]{32}$", award["award_id"])
    assert re.match(r"^src_[a-f0-9]{32}$", award["source_id"])
    assert re.match(r"^ent_[a-f0-9]{32}$", award["recipient_entity_id"])
    assert re.match(r"^ent_[a-f0-9]{32}$", award["funding_agency_entity_id"])
    assert award["amount"] == 1250000.0
    assert award["currency"] == "USD"
    assert award["fiscal_year"] == 2026
    assert award["award_type"] == "pre_official_signal"
    assert award["synthetic"] is False
    # location.attribution_confidence: label -> number for the schema.
    assert award["location"]["attribution_confidence"] == pytest.approx(0.95)
    # lineage carries the required producer_phase.
    assert award["lineage"]["producer_phase"] == "CENTINELAS_PRE_OFFICIAL_BRIDGE"


def test_supporting_entities_and_source_emitted(tmp_path):
    _write_candidates(tmp_path, [_CANDIDATE])
    built = build_centinelas_streams(root=tmp_path, now="2026-07-11T00:00:00+00:00")
    # One shared source; recipient + agency collapse to one entity (same name here).
    assert len(built["sources"]) == 1
    types = {e["entity_type"] for e in built["entities"]}
    assert types <= {"recipient", "funding_agency"}
    # Every entity/source id the award references exists in the emitted streams.
    ent_ids = {e["entity_id"] for e in built["entities"]}
    award = built["funding_awards"][0]
    assert award["recipient_entity_id"] in ent_ids
    assert award["funding_agency_entity_id"] in ent_ids
    assert award["source_id"] in {s["source_id"] for s in built["sources"]}


def test_merge_appends_and_dedups(tmp_path):
    _write_candidates(tmp_path, [_CANDIDATE])
    streams = {"sources": [], "entities": [], "relationships": []}
    added = merge_centinelas_awards(streams, root=tmp_path, now="2026-07-11T00:00:00+00:00")
    assert added == 1
    assert len(streams["funding_awards"]) == 1
    assert streams["sources"] and streams["entities"]


def test_blank_names_emit_placeholder_entities_no_dangling_refs(tmp_path):
    """A signal with no recipient/agency name still yields resolvable ent_ refs."""
    blank = {**_CANDIDATE, "recipient_entity_id": "", "funding_agency_entity_id": ""}
    _write_candidates(tmp_path, [blank])
    built = build_centinelas_streams(root=tmp_path, now="2026-07-11T00:00:00+00:00")
    award = built["funding_awards"][0]
    ent_ids = {e["entity_id"] for e in built["entities"]}
    assert award["recipient_entity_id"] in ent_ids
    assert award["funding_agency_entity_id"] in ent_ids
    names = {e["name"] for e in built["entities"]}
    assert "Unknown recipient" in names and "Unknown funding_agency" in names


def test_prior_committed_awards_are_preserved(tmp_path):
    """A later signal must not drop earlier candidates from the committed package."""
    from moneysweep.runtime.canonical_ids import fed_source_id

    src_id = fed_source_id("centinelas-pr")
    committed = tmp_path / "data" / "exports" / "canonical_v1_federation"
    committed.mkdir(parents=True, exist_ok=True)
    prior_award = {
        "award_id": "awd_" + "a" * 32,
        "source_id": src_id,
        "recipient_entity_id": "ent_" + "b" * 32,
        "funding_agency_entity_id": "ent_" + "c" * 32,
        "amount": 500.0,
        "currency": "USD",
        "fiscal_year": 2025,
        "award_type": "pre_official_signal",
        "award_date": "2025-01-01",
        "confidence": 0.5,
        "lineage": {"producer_script": "x", "producer_phase": "y", "source_inputs": ["z"]},
        "synthetic": False,
        "created_at": "2025-01-01T00:00:00+00:00",
        "extracted_at": "2025-01-01T00:00:00+00:00",
    }
    (committed / "funding_awards.jsonl").write_text(
        json.dumps(prior_award) + "\n", encoding="utf-8"
    )
    (committed / "entities.jsonl").write_text("", encoding="utf-8")
    (committed / "sources.jsonl").write_text("", encoding="utf-8")

    # A new, different candidate arrives.
    _write_candidates(tmp_path, [_CANDIDATE])
    streams = {"sources": [], "entities": [], "relationships": []}
    added = merge_centinelas_awards(streams, root=tmp_path, now="2026-07-11T00:00:00+00:00")

    award_ids = {a["award_id"] for a in streams["funding_awards"]}
    assert prior_award["award_id"] in award_ids, "prior committed award must persist"
    assert added == 2  # prior + new
