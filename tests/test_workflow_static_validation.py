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


def test_rejects_unsupported_expression_helper(tmp_path: Path) -> None:
    workflow = tmp_path / "broken.yml"
    workflow.write_text(
        """
name: broken
on: workflow_dispatch
jobs:
  test:
    runs-on: ubuntu-latest
    if: startsWith(toLower(github.event.inputs.confirm), 'yes')
    steps:
      - run: echo broken
""",
        encoding="utf-8",
    )
    errors = validate_workflow_file(workflow)
    assert any("unsupported expression helper" in error for error in errors)


def test_allows_language_lower_method_outside_actions_expression(tmp_path: Path) -> None:
    workflow = tmp_path / "valid.yml"
    workflow.write_text(
        """
name: valid
on: workflow_dispatch
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python - <<'PY'
          value = "TRUE".lower()
          print(value)
          PY
""",
        encoding="utf-8",
    )
    errors = validate_workflow_file(workflow)
    assert not any("unsupported expression helper" in error for error in errors)


def test_rejects_credential_context_in_live_fetch_if(tmp_path: Path) -> None:
    workflow = tmp_path / "highergov-fetch.yml"
    workflow.write_text(
        """
name: broken
on:
  workflow_dispatch:
    inputs:
      mode:
        default: preflight
jobs:
  validate_dispatch:
    runs-on: ubuntu-latest
    steps:
      - if: secrets.API_KEY != ''
        run: python scripts/validate_live_fetch_dispatch.py
""",
        encoding="utf-8",
    )
    errors = validate_workflow_file(workflow)
    assert any("credential context is forbidden" in error for error in errors)
