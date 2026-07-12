"""The committed PRII skill packet passes every validator check.

This is the master gate: it runs scripts/validate_skills.run_all over the real
repo and asserts zero errors across all ten checks (blueprint §9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.validate_skills import (
    CHECKS,
    check_activation,
    check_path_resolution,
    run_all,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_all_ten_checks_are_registered():
    # Blueprint §9 defines ten jobs; the validator must implement all of them.
    assert set(CHECKS) == {
        "skill-structure",
        "skill-registry",
        "command-resolution",
        "path-resolution",
        "boundary-policy",
        "mode-safety",
        "coverage-accounting",
        "export-contract",
        "activation",
        "drift",
    }


def test_committed_packet_passes_every_check():
    results = run_all(ROOT)
    failures = {name: errs for name, errs in results.items() if errs}
    assert not failures, f"skill packet validation failed: {failures}"


def test_activation_check_requires_a_matrix(tmp_path):
    # The activation matrix is the routing-coverage artifact; a missing or empty
    # matrix must fail the check, not silently pass (a no-op "ok").
    (tmp_path / "skill-registry.yaml").write_text(
        (ROOT / "skill-registry.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert check_activation(tmp_path), "missing activation-matrix.yaml must fail"
    (tmp_path / "activation-matrix.yaml").write_text("{}", encoding="utf-8")
    assert check_activation(tmp_path), "empty activation-matrix.yaml must fail"


def test_path_resolution_rejects_out_of_repo_paths(tmp_path):
    # reads/local_scripts are repo-relative by contract; absolute or ../ paths
    # must be rejected so a packet cannot authorize resources outside the repo.
    reg = {
        "schema_version": "prii_skill_registry_v1",
        "skills": [{"skill_id": "x", "reads": ["/etc/hostname", "../outside.txt"]}],
    }
    (tmp_path / "skill-registry.yaml").write_text(yaml.safe_dump(reg), encoding="utf-8")
    errors = check_path_resolution(tmp_path)
    assert any("not repo-relative" in e for e in errors), errors
    assert any("escapes the repo root" in e for e in errors), errors


def test_registry_validates_against_declared_schema():
    # The registry declares a schema; it must actually conform to it, including
    # the top-level packet_config block. Guards against a registry key the
    # declared schema forbids (the pure-Python validator does not enforce the
    # schema's additionalProperties, so a consumer that does would reject us).
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "prii_skill_contract.schema.json").read_text())
    registry = yaml.safe_load((ROOT / "skill-registry.yaml").read_text())
    jsonschema.validate(registry, schema)
