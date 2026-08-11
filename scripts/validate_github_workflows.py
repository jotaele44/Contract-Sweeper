#!/usr/bin/env python3
"""Static checks for GitHub workflow syntax and source-fetch safety invariants."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

UNSUPPORTED_FUNCTIONS = re.compile(r"\b(?:toLower|toUpper)\s*\(", re.IGNORECASE)
EXPRESSION_BLOCKS = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
SECRET_CONTEXT = "secrets" + "."
LIVE_FETCH_WORKFLOWS = {
    "materialize-sources.yml",
    "highergov-fetch.yml",
    "sam-opportunities-fetch.yml",
}


def _walk(node: Any, path: tuple[str, ...] = ()):
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = path + (str(key),)
            yield child_path, value
            yield from _walk(value, child_path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child_path = path + (str(index),)
            yield child_path, value
            yield from _walk(value, child_path)


def _expression_has_unsupported_helper(text: str) -> bool:
    return any(
        UNSUPPORTED_FUNCTIONS.search(expression) for expression in EXPRESSION_BLOCKS.findall(text)
    )


def validate_workflow_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]

    if not isinstance(parsed, dict):
        return [f"{path}: workflow root must be a mapping"]

    if _expression_has_unsupported_helper(text):
        errors.append(f"{path}: unsupported expression helper detected")

    for node_path, value in _walk(parsed):
        if node_path and node_path[-1] == "if" and isinstance(value, str):
            if UNSUPPORTED_FUNCTIONS.search(value):
                errors.append(f"{path}:{'.'.join(node_path)}: unsupported expression helper")

    if path.name in LIVE_FETCH_WORKFLOWS:
        for node_path, value in _walk(parsed):
            if node_path and node_path[-1] == "if" and isinstance(value, str):
                if SECRET_CONTEXT in value:
                    errors.append(
                        f"{path}:{'.'.join(node_path)}: credential context is forbidden in if"
                    )

        dispatch = parsed.get(True, parsed.get("on", {}))
        if not isinstance(dispatch, dict) or "workflow_dispatch" not in dispatch:
            errors.append(f"{path}: source-fetch workflow must be manual-dispatch only")
        else:
            workflow_dispatch = dispatch["workflow_dispatch"] or {}
            inputs = workflow_dispatch.get("inputs", {})
            mode = inputs.get("mode", {}) if isinstance(inputs, dict) else {}
            if mode.get("default") != "preflight":
                errors.append(f"{path}: mode must default to preflight")
            if "dry_run" in inputs:
                errors.append(f"{path}: legacy dry_run input is forbidden")

        if "validate_live_fetch_dispatch.py" not in text:
            errors.append(f"{path}: shared dispatch validator is not invoked")
        if "dispatch-receipt" not in text:
            errors.append(f"{path}: redacted dispatch receipt is required")

    return errors


def validate_workflows(workflows_dir: Path) -> list[str]:
    paths = sorted([*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")])
    if not paths:
        return [f"{workflows_dir}: no workflow files found"]
    errors: list[str] = []
    for path in paths:
        errors.extend(validate_workflow_file(path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows-dir", type=Path, default=Path(".github/workflows"))
    args = parser.parse_args()
    errors = validate_workflows(args.workflows_dir)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"validated workflow files in {args.workflows_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
