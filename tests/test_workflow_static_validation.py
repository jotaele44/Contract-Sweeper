from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_github_workflows.py"
SPEC = importlib.util.spec_from_file_location("validate_github_workflows", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

validate_workflow_file = MODULE.validate_workflow_file
validate_workflows = MODULE.validate_workflows

NODE_ENGINE = "^20.19.0 || ^22.13.0 || >=24.0.0"
WORKFLOW_NODE_VERSIONS = {
    "gui-capability-parity.yml": "20.19.0",
    "ci.yml": "22.13.0",
    "desktop-build.yml": "22.13.0",
    "moneysweep-federation-design-pilot.yml": "22.13.0",
}


def test_repository_workflows_pass_static_validation() -> None:
    assert validate_workflows(Path(".github/workflows")) == []


def test_source_workflows_require_preflight_default() -> None:
    for name in (
        "materialize-sources.yml",
        "highergov-fetch.yml",
        "sam-opportunities-fetch.yml",
    ):
        assert validate_workflow_file(Path(".github/workflows") / name) == []


def test_dashboard_declares_the_vite_8_node_engine() -> None:
    package = json.loads(Path("dashboard/package.json").read_text(encoding="utf-8"))
    lock = json.loads(Path("dashboard/package-lock.json").read_text(encoding="utf-8"))
    assert package["engines"]["node"] == NODE_ENGINE
    assert lock["packages"][""]["engines"]["node"] == NODE_ENGINE
    assert lock["packages"]["node_modules/jsdom"]["engines"]["node"] == NODE_ENGINE
    assert lock["packages"]["node_modules/vite"]["engines"]["node"] == ("^20.19.0 || >=22.12.0")


def test_setup_node_workflows_pin_supported_versions() -> None:
    found = {}
    for path in sorted(Path(".github/workflows").glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/setup-node@"):
                    found[path.name] = step.get("with", {}).get("node-version")
    assert found == WORKFLOW_NODE_VERSIONS
