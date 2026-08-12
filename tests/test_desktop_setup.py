"""Tests for desktop/setup.py — marker-file idempotency.

The desktop wrapper's one-time setup skips reinstalling when a
``.setup-complete`` marker already exists. These tests guard the part that
previously had a gap: the marker used to be a plain "ok" sentinel, so editing
a requirement file or the frontend lockfile after a completed setup left the
marker (and therefore the stale install) in place. ``fingerprint()`` /
``is_complete()`` must detect that drift instead of silently skipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import desktop.setup as setup_mod

pytestmark = pytest.mark.unit


def _wire_paths(monkeypatch, tmp_path):
    """Point every path desktop.setup consults at an isolated tmp tree."""
    repo_root = tmp_path
    requirement = repo_root / "requirements-desktop.txt"
    requirement.write_text("pywebview>=5.0\n", encoding="utf-8")
    frontend_dir = repo_root / "dashboard"
    frontend_dir.mkdir()
    dist_dir = frontend_dir / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    venv_dir = repo_root / ".venv"
    marker = repo_root / ".setup-complete"

    monkeypatch.setattr(setup_mod, "REPO_ROOT", repo_root)
    monkeypatch.setattr(setup_mod, "REQUIREMENT_FILES", [requirement])
    monkeypatch.setattr(setup_mod, "FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(setup_mod, "DIST_DIR", dist_dir)
    monkeypatch.setattr(setup_mod, "VENV_DIR", venv_dir)
    monkeypatch.setattr(setup_mod, "MARKER", marker)
    monkeypatch.setattr(setup_mod.config, "EXTRA_PIP_SPECS", [], raising=False)
    monkeypatch.setattr(setup_mod.config, "EXTRA_BUILD_ENV", {}, raising=False)

    # A stand-in venv python binary; only existence is checked.
    bin_dir = venv_dir / ("Scripts" if setup_mod.os.name == "nt" else "bin")
    bin_dir.mkdir(parents=True)
    setup_mod.venv_python().touch()

    return requirement, marker


def test_is_complete_false_when_marker_absent(tmp_path, monkeypatch):
    _wire_paths(monkeypatch, tmp_path)
    assert setup_mod.is_complete() is False


def test_is_complete_true_after_marker_matches_fingerprint(tmp_path, monkeypatch):
    _wire_paths(monkeypatch, tmp_path)
    setup_mod.MARKER.write_text(setup_mod.fingerprint() + "\n", encoding="utf-8")
    assert setup_mod.is_complete() is True


def test_editing_a_requirement_file_invalidates_the_marker(tmp_path, monkeypatch):
    requirement, marker = _wire_paths(monkeypatch, tmp_path)
    marker.write_text(setup_mod.fingerprint() + "\n", encoding="utf-8")
    assert setup_mod.is_complete() is True

    requirement.write_text("pywebview>=6.0\n", encoding="utf-8")

    assert setup_mod.is_complete() is False


def test_stale_sentinel_marker_is_not_treated_as_complete(tmp_path, monkeypatch):
    # Regression guard for the pre-fingerprint format: a marker containing the
    # old "ok" sentinel must not be mistaken for a valid, up-to-date marker.
    _, marker = _wire_paths(monkeypatch, tmp_path)
    marker.write_text("ok\n", encoding="utf-8")
    assert setup_mod.is_complete() is False
