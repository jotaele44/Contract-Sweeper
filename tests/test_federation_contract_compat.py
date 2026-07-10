"""Federation canonical-export contract-compat test (hub-facing).

Pins the manifest envelope produced by ``scripts/federation_export.py`` against
the hub's contract: the exact top-level key set, the federation handshake
block, the per-file entries, and validity against the vendored copy of
thehub-pr's ``federation_export_manifest`` schema
(``schemas/federation_export_manifest.schema.json``). A producer-side change
that alters any of these breaks this test before it can silently break the
hub's consumer.
"""

import json
from pathlib import Path

import pytest

from scripts import federation_export as fx

REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO / "schemas" / "federation_export_manifest.schema.json"

_TS = "2026-06-07T01:08:53.877935+00:00"

EXPECTED_MANIFEST_KEYS = {
    "package_id",
    "producer",
    "export_contract_version",
    "mode",
    "created_at",
    "extracted_at",
    "federation",
    "files",
}


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    out = tmp_path_factory.mktemp("contract_compat")
    rc = fx.main(["--mode", "test", "--now", _TS, "--out", str(out)])
    assert rc == 0
    return json.loads((out / "manifest.json").read_text())


def test_manifest_top_level_keys_exact(manifest):
    assert set(manifest) == EXPECTED_MANIFEST_KEYS


def test_federation_handshake_block(manifest):
    assert manifest["federation"]["hub_parent"] == "thehub-pr"
    assert manifest["federation"]["producer_repo"] == "moneysweep-pr"


def test_file_entries_carry_required_fields(manifest):
    assert manifest["files"]
    for f in manifest["files"]:
        assert set(f) >= {"filename", "stream", "record_count", "sha256", "schema_id"}


def test_manifest_validates_against_vendored_hub_schema(manifest):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(manifest, schema)


def test_vendored_schema_matches_hub_manifest_contract():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["$id"] == "federation_export_manifest.schema.json"
    assert set(schema["required"]) <= EXPECTED_MANIFEST_KEYS
