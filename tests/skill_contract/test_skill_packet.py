"""The committed PRII skill packet passes every validator check.

This is the master gate: it runs scripts/validate_skills.run_all over the real
repo and asserts zero errors across all ten checks (blueprint §9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.validate_skills import CHECKS, run_all

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


def test_registry_validates_against_declared_schema():
    # The registry declares a schema; it must actually conform to it, including
    # the top-level packet_config block. Guards against a registry key the
    # declared schema forbids (the pure-Python validator does not enforce the
    # schema's additionalProperties, so a consumer that does would reject us).
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "prii_skill_contract.schema.json").read_text())
    registry = yaml.safe_load((ROOT / "skill-registry.yaml").read_text())
    jsonschema.validate(registry, schema)
