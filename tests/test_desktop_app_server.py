"""Tests for the same-origin desktop app server (SPA fallback + API precedence).

Covers the behaviours that regressed: SPA navigation on API-shadowed paths, API
priority for fetch()-style requests, passthrough prefixes, the trailing-slash
redirect, static-asset serving, the path-traversal guard, and the friendly
missing-build page. Skipped when fastapi/httpx aren't installed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import desktop.app_server as app_server  # noqa: E402


@pytest.fixture
def built_client(tmp_path, monkeypatch):
    """A client whose DIST_DIR contains a built frontend."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>app</title>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(app_server, "DIST_DIR", dist)
    return TestClient(app_server.app)


def test_spa_navigation_serves_index(built_client):
    r = built_client.get("/deep/client/route", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "<title>app</title>" in r.text


def test_spa_navigation_on_api_shadowed_path(built_client):
    # A browser navigation to a path that also exists as an API endpoint
    # (/health) must return the SPA, not the JSON — the /sources-style regression.
    r = built_client.get("/health", headers={"accept": "text/html"})
    assert "text/html" in r.headers["content-type"]


def test_api_keeps_priority_for_fetch(built_client):
    r = built_client.get("/health", headers={"accept": "*/*"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


def test_docs_not_hijacked(built_client):
    r = built_client.get("/openapi.json", headers={"accept": "text/html"})
    assert r.headers["content-type"].startswith("application/json")


def test_trailing_slash_redirects_api(built_client):
    r = built_client.get("/health/", headers={"accept": "*/*"}, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/health"


def test_static_asset_served(built_client):
    r = built_client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_path_traversal_falls_back_to_index(built_client):
    r = built_client.get("/../../etc/passwd", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "<title>app</title>" in r.text  # never serves outside DIST_DIR


def test_missing_build_shows_setup_page(tmp_path, monkeypatch):
    monkeypatch.setattr(app_server, "DIST_DIR", tmp_path / "nope")
    client = TestClient(app_server.app)
    r = client.get("/", headers={"accept": "text/html"})
    assert r.status_code == 503
    assert "desktop/setup.py" in r.text
