"""Smoke test: this repo's FastAPI backend imports, starts, and answers.

Rendered from thehub-pr/federation-templates/baseline/test_server_smoke.py.
Do not hand-edit — template-drift.yml fails the build if you do. Change the
template and re-render.

Deliberately shallow. It asserts the server *boots and responds*, not that its
data is right: past `/health` the six producers share no route at all, so
anything deeper cannot be single-sourced. The gap this closes is real — three
repos had no test importing `server/backend/main.py`, so an import-time break
would ship with a green suite.

Three details are load-bearing rather than stylistic:

* **`with TestClient(app)`** runs the FastAPI lifespan; bare `TestClient(app)`
  does not. A probe that forgot the context manager is exactly what once
  reported a correctly-seeded collection as empty.
* **`status` is checked for presence, never value.** spiderweb-pr's `/health`
  returns `"degraded"` with a 200 when its database is absent — by design, so a
  load balancer can read the body rather than guess. Asserting `== "ok"` would
  fail there for a healthy reason.
* **`importorskip` is not decoration.** Some repos run a second pytest job
  without fastapi installed (moneysweep's `ci.yml`, ovnis' `validate.yml`); this
  test must skip there rather than turn a green job red. The job that does
  install fastapi is the one that gives this test its teeth.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Do this here rather than rely on pytest config: `pythonpath`, `tests/__init__.py`
# and the presence of `server/__init__.py` all differ across the federation, so
# `import server.backend.main` resolves in some repos and not others.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

import server.backend.main as backend  # noqa: E402


def test_backend_module_exposes_a_fastapi_app():
    """Importing the module at all is most of the value of this file."""
    from fastapi import FastAPI

    assert isinstance(backend.app, FastAPI)


def test_health_endpoint_answers():
    with TestClient(backend.app) as client:  # context manager -> lifespan runs
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    # Presence, not value: "degraded" is a legitimate answer from a server that
    # started correctly but has no data mounted.
    status = body.get("status")
    assert isinstance(status, str) and status


def test_health_is_registered_alongside_other_routes():
    paths = {getattr(route, "path", None) for route in backend.app.routes}
    assert "/health" in paths
    assert len({path for path in paths if path}) > 1


def test_openapi_schema_builds():
    """Catches a malformed response model, which /health alone would not."""
    schema = backend.app.openapi()

    assert schema.get("openapi")
    assert "/health" in schema.get("paths", {})
