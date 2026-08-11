from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_github_workflows.py"
SPEC = importlib.util.spec_from_file_location("validate_github_workflows", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

validate_workflow_file = MODULE.validate_workflow_file
validate_workflows = MODULE.validate_workflows


def test_repository_workflows_pass_static_validation() -> None:
    assert validate_workflows(Path(".github/workflows")) == []


def test_source_workflows_require_preflight_default() -> None:
    for name in (
        "materialize-sources.yml",
        "highergov-fetch.yml",
        "sam-opportunities-fetch.yml",
    ):
        assert validate_workflow_file(Path(".github/workflows") / name) == []
