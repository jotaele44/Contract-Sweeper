#!/usr/bin/env python3
"""Validate the repository-local HAF federation contract fail closed."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(".federation/haf_contract.json")
EXPECTED = {
    "schema_version": "haf_repo_contract_v2",
    "haf_contract_version": "2.0.0",
    "framework_compatibility": ">=0.4.0,<1.0.0",
    "program_id": "moneysweep-pr",
    "federation_role": "public_money_intelligence_node",
    "certification_required": True,
    "raw_snapshot_policy": "PRESERVE_OR_IMMUTABLE_REFERENCE",
    "identity_policy": "EVIDENCE_PRIORITY_FAIL_CLOSED",
    "unresolved_policy": "FAIL_CLOSED",
    "canonical_export_required": True,
    "native_contract": "federation.json",
}
ALLOWED_ADAPTER_STATES = {"COMPATIBLE_PENDING_CI", "COMPATIBLE"}


def validate(root: Path, repository: str) -> list[str]:
    path = root / CONTRACT
    if not path.is_file():
        return [f"missing HAF contract: {CONTRACT}"]
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid HAF contract: {exc}"]
    if not isinstance(contract, dict):
        return ["HAF contract root must be an object"]

    errors = [
        f"{key}: expected {expected!r}, got {contract.get(key)!r}"
        for key, expected in EXPECTED.items()
        if contract.get(key) != expected
    ]
    if contract.get("repository_full_name") != repository:
        errors.append("repository_full_name does not match GITHUB_REPOSITORY")
    if contract.get("adapter_state") not in ALLOWED_ADAPTER_STATES:
        errors.append("adapter_state is not an allowed compatible state")

    native_path = root / str(contract.get("native_contract", ""))
    if not native_path.is_file():
        errors.append("native_contract does not resolve to a file")
    else:
        try:
            native = json.loads(native_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid native contract: {exc}")
        else:
            if not isinstance(native, dict) or native.get("program_id") != contract.get(
                "program_id"
            ):
                errors.append("native contract program_id does not match HAF contract")

    for key in ("native_test_command", "canonical_export_command"):
        command = contract.get(key)
        if not isinstance(command, str) or not command.strip():
            errors.append(f"{key} must be a non-empty command")
            continue
        parts = shlex.split(command)
        script_args = [part for part in parts if part.endswith(".py")]
        if script_args and not all((root / part).is_file() for part in script_args):
            errors.append(f"{key} references a missing script")
    return errors


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "jotaele44/moneysweep-pr")
    errors = validate(ROOT, repository)
    if errors:
        for error in errors:
            print(f"HAF_CONTRACT_FAIL: {error}")
        return 1
    print("HAF_CONTRACT_PASS: moneysweep-pr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
