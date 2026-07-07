"""Tests for scripts/federation_export.py — the Hub-conformant canonical export."""

import json
import re

import pytest

from scripts import federation_export as fx

_TS = "2026-06-07T01:08:53.877935+00:00"


def _streams():
    lineage = {
        "producer_script": "moneysweep/federation/canonical_v1_bridge.py",
        "producer_phase": "CANONICAL_V1_FEDERATION_BRIDGE",
        "source_inputs": ["data/canonical_v1/evidence.csv"],
    }
    return {
        "sources": [
            {
                "source_id": "src_" + "a" * 32,
                "source_type": "registry",
                "source_name": "S",
                "source_ref": "r",
                "confidence": 0.9,
                "lineage": lineage,
                "synthetic": False,
                "created_at": _TS,
                "extracted_at": _TS,
            },
        ],
        "entities": [
            {
                "entity_id": "ent_" + "b" * 32,
                "source_id": "src_" + "a" * 32,
                "name": "Acme",
                "normalized_name": "ACME",
                "entity_type": "recipient",
                "jurisdiction": "PR",
                "confidence": 0.9,
                "lineage": lineage,
                "synthetic": False,
                "created_at": _TS,
                "extracted_at": _TS,
            },
        ],
        "relationships": [
            {
                "relationship_id": "rel_" + "c" * 32,
                "source_id": "src_" + "a" * 32,
                "source_entity_id": "ent_" + "b" * 32,
                "target_entity_id": "ent_" + "b" * 32,
                "relationship_type": "received_award_from",
                "evidence_source_id": "src_" + "a" * 32,
                "confidence": 0.9,
                "lineage": lineage,
                "synthetic": False,
                "created_at": _TS,
                "extracted_at": _TS,
            },
        ],
        "not_yet_federated": [],
    }


def test_write_package_manifest_is_hub_conformant(tmp_path):
    manifest = fx.write_package(_streams(), tmp_path, mode="test", now=_TS)

    # Required Hub federation_export_manifest fields.
    for key in (
        "package_id",
        "producer",
        "export_contract_version",
        "mode",
        "created_at",
        "federation",
        "files",
    ):
        assert key in manifest
    assert re.fullmatch(r"pkg_[a-f0-9]{32}", manifest["package_id"])
    assert manifest["producer"] == "moneysweep-pr"
    assert manifest["mode"] == "test"
    assert manifest["federation"] == {"producer_repo": "moneysweep-pr", "hub_parent": "thehub-pr"}

    streams = _streams()
    for f in manifest["files"]:
        assert f["stream"] in ("sources", "entities", "relationships")
        assert re.fullmatch(r"[a-f0-9]{64}", f["sha256"])
        assert f["record_count"] == len(streams[f["stream"]])
        assert (tmp_path / f["filename"]).exists()
    # manifest.json is written to disk and round-trips.
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest


def test_write_package_is_deterministic(tmp_path):
    a = fx.write_package(_streams(), tmp_path / "a", mode="test", now=_TS)
    b = fx.write_package(_streams(), tmp_path / "b", mode="test", now=_TS)
    assert a["package_id"] == b["package_id"]
    assert (tmp_path / "a" / "sources.jsonl").read_bytes() == (
        tmp_path / "b" / "sources.jsonl"
    ).read_bytes()


def test_mode_changes_package_id(tmp_path):
    test_id = fx.write_package(_streams(), tmp_path / "t", mode="test", now=_TS)["package_id"]
    prod_id = fx.write_package(_streams(), tmp_path / "p", mode="production", now=_TS)["package_id"]
    assert test_id != prod_id


def test_build_coverage_shape():
    cov = fx.build_coverage(_streams(), mode="test", now=_TS)
    assert cov["producer"] == "moneysweep-pr"
    assert cov["gate"] == "NON_PRODUCTION_DIAGNOSTIC"
    assert cov["stream_counts"] == {"sources": 1, "entities": 1, "relationships": 1}
    assert cov["edges_federated_pct"] == 100.0
    assert fx.build_coverage(_streams(), mode="production", now=_TS)["gate"] == "PRODUCTION"


@pytest.mark.integration
def test_main_end_to_end_writes_valid_package(tmp_path):
    # Runs the real bridge against repo data and writes a package to tmp_path.
    rc = fx.main(["--mode", "test", "--now", _TS, "--out", str(tmp_path)])
    assert rc == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["producer"] == "moneysweep-pr"
    assert {f["stream"] for f in manifest["files"]} == {"sources", "entities", "relationships"}
    assert (tmp_path / "coverage.json").exists()
    # Every declared file exists with a matching record count.
    for f in manifest["files"]:
        lines = [ln for ln in (tmp_path / f["filename"]).read_text().splitlines() if ln.strip()]
        assert len(lines) == f["record_count"]
