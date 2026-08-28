from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "data"
    / "manifests"
    / "capital_control"
    / "capital_control_successor_synthesis_v1.json"
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode()
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_successor_preserves_exact_source_payload_blobs() -> None:
    manifest = _manifest()
    for source_name in ("pr520", "pr527"):
        source = manifest["source_inputs"][source_name]
        for relative, expected_sha in source["files"].items():
            if relative == "moneysweep/capital_control/__init__.py":
                continue
            path = ROOT / relative
            assert path.is_file(), f"missing imported source path: {relative}"
            assert _git_blob_sha(path) == expected_sha, relative


def test_only_material_overlap_is_adjudicated_whole_file() -> None:
    manifest = _manifest()
    adjudication = manifest["overlap_adjudication"]
    assert adjudication["pr520_vs_pr527_path_intersection"] == []
    assert adjudication["pr520_vs_current_main_material_intersection"] == [
        "moneysweep/capital_control/__init__.py"
    ]

    merged = ROOT / "moneysweep" / "capital_control" / "__init__.py"
    record = adjudication["moneysweep/capital_control/__init__.py"]
    assert _git_blob_sha(merged) == record["derived_merged_blob"]

    source = merged.read_text(encoding="utf-8")
    assert "from . import resolution_core" in source
    assert "from .deep_dive import (" in source
    assert '"resolution_core"' in source
    assert '"build_ownership_deep_dive"' in source


def test_successor_source_lineage_and_hold_are_exact() -> None:
    manifest = _manifest()
    sources = manifest["source_inputs"]
    assert manifest["control_issue"] == 526
    assert manifest["base_main"]["commit"] == "df78f15f7c36b98bc6ecfae37c7e775ec487ead3"
    assert sources["pr520"]["head_sha"] == "5646ad6014959baf783b66c8dd497f1f518f207e"
    assert sources["pr527"]["head_sha"] == "f484a226f73f7f366a88ad9e051bba0d0150da54"
    assert sources["pr484"]["head_sha"] == "85dc4744173ebd26c68f2b904265c6c91497d5ad"
    assert sources["pr484"]["resolver_disposition"] == "SUPERSEDED_NONCANONICAL"
    assert manifest["state"] == "CANDIDATE_REQUIRES_COMPLETE_RECERTIFICATION"
    assert manifest["draft_required"] is True
    assert manifest["merge_authorized"] is False
    assert manifest["production_promotion_authorized"] is False


def test_legacy_identity_and_generic_backend_do_not_become_second_resolvers() -> None:
    identity_source = (
        ROOT / "moneysweep" / "capital_control" / "identity.py"
    ).read_text(encoding="utf-8")
    assert "from .resolution_core import Candidate, EvidenceBasis, resolve_candidates" in identity_source
    assert "Compatibility wrapper over the canonical resolution_core" in identity_source

    backend_source = (ROOT / "server" / "backend" / "main.py").read_text(encoding="utf-8")
    forbidden = {
        "def _capital_effective(",
        "def _capital_compare(",
        "CAPITAL_CONTROL_PATH =",
        "capital_control_holdings.csv",
    }
    assert not any(marker in backend_source for marker in forbidden)


def test_dependency_and_public_source_gates_remain_fail_closed() -> None:
    manifest = _manifest()
    invariants = manifest["invariants"]
    assert invariants == {
        "no_raw_mutation": True,
        "no_heuristic_identity_promotion": True,
        "no_unsafe_many_to_many": True,
        "parcel_requires_authoritative_property_anchor": True,
        "federation_requires_stable_id_or_authoritative_binding": True,
        "funding_requires_project_specific_binding": True,
        "foia_requires_certified_public_source_exhaustion": True,
        "full_candidate_sets_preserved": True,
        "contradictions_and_superseded_preserved": True,
        "source_input_shas_immutable": True,
    }
