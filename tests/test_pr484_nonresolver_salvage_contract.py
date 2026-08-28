from __future__ import annotations

import json
from pathlib import Path

from scripts.gen_dashboard_snapshot import ENDPOINTS
from server.backend import main as backend

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifests" / "capital_control" / "pr484_nonresolver_salvage_v1.json"


def test_offline_client_prefers_complete_query_key_before_route_fallback() -> None:
    source = (ROOT / "dashboard" / "src" / "lib" / "api.js").read_text(encoding="utf-8")
    exact_lookup = "Object.prototype.hasOwnProperty.call(snapshot, path)"
    route_fallback = "const key = path.split('?')[0]"
    assert exact_lookup in source
    assert route_fallback in source
    assert source.index(exact_lookup) < source.index(route_fallback)


def test_snapshot_generator_materializes_exact_query_key_from_canonical_route() -> None:
    key = "/contracts?status=ACTIVE"
    assert key in ENDPOINTS
    assert ENDPOINTS[key]() == backend.contracts(status="ACTIVE")


def test_salvage_manifest_keeps_multi_issuer_ui_dependency_gated() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in manifest["items"]}
    assert items["multi-issuer-comparison-presentation"]["state"] == "DEFERRED_DEPENDENCY_GATED"
    assert items["pr484-generic-backend-resolver"]["state"] == "SUPERSEDED_NONCANONICAL"
    assert manifest["canonical_owner"] == "moneysweep.capital_control.resolution_core"


def test_generic_backend_does_not_receive_pr484_private_resolution_helpers() -> None:
    source = (ROOT / "server" / "backend" / "main.py").read_text(encoding="utf-8")
    forbidden = {
        "def _capital_effective(",
        "def _capital_compare(",
        "CAPITAL_CONTROL_PATH =",
        "capital_control_holdings.csv",
    }
    assert not any(marker in source for marker in forbidden)


def test_manifest_prohibits_direct_merge_and_production_promotion() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    prohibitions = set(manifest["prohibitions"])
    assert {
        "NO_DIRECT_PR484_MERGE",
        "NO_DIRECT_PR484_CHERRY_PICK",
        "NO_DUPLICATED_CANONICAL_RESOLVER",
        "NO_MERGE",
        "NO_PRODUCTION_PROMOTION",
    } <= prohibitions
    assert manifest["recertification_required"] is True
