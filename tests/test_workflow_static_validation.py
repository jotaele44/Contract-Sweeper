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


def test_rejects_secrets_context_in_if(tmp_path: Path) -> None:
    workflow = tmp_path / "broken.yml"
    workflow.write_text(
        """
name: broken
on: workflow_dispatch
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - if: secrets.API_KEY != ''
        run: echo broken
""",
        encoding="utf-8",
    )
    errors = validate_workflow_file(workflow)
    assert any("secrets context is forbidden" in error for error in errors)
