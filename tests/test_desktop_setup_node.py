from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop import setup

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_runtime_contract_bindings() -> None:
    package = json.loads((REPO_ROOT / "dashboard/package.json").read_text(encoding="utf-8"))
    extension = json.loads(
        (
            REPO_ROOT / ".federation/gui-capabilities.extensions/dashboard-node-runtime.json"
        ).read_text(encoding="utf-8")
    )
    assert setup.NODE_ENGINE == package["engines"]["node"]
    assert (REPO_ROOT / "dashboard/.npmrc").read_text(encoding="utf-8") == ("engine-strict=true\n")
    assert extension["capabilities"][0]["candidate_ids"] == [
        "python_symbol:desktop/setup.py:node_version_supported"
    ]


@pytest.mark.parametrize("version", ("v20.19.0", "20.99.0", "v22.13.0", "24.0.0", "v26.0.0"))
def test_node_version_supported_accepts_vite_8_runtimes(version: str) -> None:
    assert setup.node_version_supported(version)


@pytest.mark.parametrize(
    "version",
    ("v18.20.0", "v20.18.9", "v21.99.0", "v22.12.9", "v23.99.0", "unknown", ""),
)
def test_node_version_supported_rejects_unsupported_runtimes(version: str) -> None:
    assert not setup.node_version_supported(version)


def test_setup_frontend_rejects_node_18_before_npm_install(monkeypatch) -> None:
    monkeypatch.setattr(setup.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(
        setup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="v18.20.0\n"),
    )
    with pytest.raises(SystemExit, match=r"Node\.js .* required .* found v18\.20\.0"):
        setup.setup_frontend()
