"""Tests for the SpiderWeb contract-finance bundle adapter."""

from __future__ import annotations

import json
from pathlib import Path


from scripts.build_contract_finance_bundle import REQUIRED_OUTPUTS, build_bundle
from scripts.ingest_centinelas_signals import run as ingest_run

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_drop(intake: Path, item_id: str, **overrides) -> None:
    payload = {
        "schema_version": "1.0",
        "item_id": item_id,
        "source_url": f"https://example.com/{item_id}",
        "title": "AAA procurement RFP in Ponce",
        "body_text": "",
        "labels": ["FINANCIAL"],
        "captured_at": "2026-07-01T00:00:00+00:00",
        "published_at": "2026-07-01T00:00:00+00:00",
        "evidence_tier": "T2",
        "municipalities": ["Ponce"],
        "agencies": ["AAA"],
        "estimated_value": 1500000.0,
    }
    payload.update(overrides)
    (intake / f"{item_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_bundle_from_centinelas_stream(tmp_path):
    intake = tmp_path / "intake"
    intake.mkdir()
    _write_drop(intake, "fin001")
    streams = tmp_path / "streams"
    ingest_run(intake, streams, root=REPO_ROOT)

    out = tmp_path / "bundle"
    report = build_bundle(out, export_dir=streams)

    # All four SpiderWeb-required files exist.
    for name in REQUIRED_OUTPUTS:
        assert (out / name).exists(), f"missing {name}"

    # The award feature carries the exact properties SpiderWeb's scorer reads.
    awards = json.loads((out / "contract_awards.geojson").read_text())
    assert awards["type"] == "FeatureCollection"
    props = awards["features"][0]["properties"]
    for key in (
        "record_id",
        "entity_id",
        "amount",
        "date",
        "municipality_code",
        "municipality_name",
        "feature_type",
        "source_id",
    ):
        assert key in props
    assert props["municipality_code"] == "72113"  # Ponce
    assert props["amount"] == 1500000.0
    assert props["source_id"] == "centinelas-pr"

    # Ingest report surfaces the Centinelas pre-official provenance.
    assert report["producer"] == "moneysweep-pr"
    assert report["centinelas_pre_official"] == {"candidate_count": 1, "located_count": 1}

    # Density aggregates one clean row per municipality.
    density = (out / "municipality_funding_density.csv").read_text().strip().splitlines()
    assert density[0] == "municipality_code,municipality_name,total_amount,record_count"
    assert any(line.startswith("72113,Ponce,1500000") for line in density[1:])
