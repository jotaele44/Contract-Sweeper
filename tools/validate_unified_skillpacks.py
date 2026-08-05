#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def is_allowed_path(path: str, allowed_paths: list[str]) -> bool:
    return any(
        path == allowed
        or (allowed.endswith("/") and path.startswith(allowed))
        for allowed in allowed_paths
    )


def validate(root: Path) -> dict[str, Any]:
    skillpack_root = root / ".claude" / "skillpacks"
    errors: list[str] = []

    binding = load_json(skillpack_root / "BINDING.json")
    manifest = load_json(skillpack_root / "MANIFEST.json")
    legacy = load_json(skillpack_root / "LEGACY_COMPATIBILITY.json")
    skill_bytes = (skillpack_root / "SKILL.md").read_bytes()
    skill_text = skill_bytes.decode("utf-8")

    if manifest["repository"] != binding["repository"]:
        errors.append("repository identity mismatch")
    if manifest["pinned_base_commit"] != binding["pinned_base_commit"]:
        errors.append("pinned base mismatch")
    if manifest.get("runtime_enabled") is not False:
        errors.append("runtime is not fail-closed")

    activation = binding["activation"]
    if any(value is not False for value in activation.values()):
        errors.append("activation boundary is not fail-closed")

    authority = binding["authority"]
    if any(value is not False for value in authority.values()):
        errors.append("authority boundary is not fail-closed")

    if sha256_bytes(skill_bytes) != manifest["skill_sha256"]:
        errors.append("skill SHA-256 mismatch")
    if len(skill_bytes) != manifest["skill_bytes"]:
        errors.append("skill size mismatch")

    capabilities = manifest["capabilities"]
    capability_ids = {capability["id"] for capability in capabilities}
    if len(capability_ids) != manifest["capability_count"]:
        errors.append("capability count mismatch")

    for capability in capabilities:
        capability_id = capability["id"]
        if f"`{capability_id}`" not in skill_text:
            errors.append(f"missing capability in dispatcher: {capability_id}")
        replacement = capability.get("replacement")
        if replacement and replacement not in capability_ids:
            errors.append(f"missing alias target for: {capability_id}")

    if "__unknown_capability__" in capability_ids:
        errors.append("unknown dispatch sentinel is present")

    legacy_entries = legacy.get("entries", [])
    repository_capability_ids = set(binding["capability_ids"])
    legacy_capability_ids = {
        entry["capability_id"] for entry in legacy_entries
    }
    if legacy_capability_ids != repository_capability_ids:
        errors.append("legacy parity mismatch")

    for entry in legacy_entries:
        if entry.get("status") != "compatibility_shim":
            errors.append("legacy entry is not a compatibility shim")
        if entry.get("capability_preserved") is not True:
            errors.append("legacy capability is not preserved")

    legacy_bytes = (skillpack_root / "LEGACY_COMPATIBILITY.json").read_bytes()
    if sha256_bytes(legacy_bytes) != manifest["legacy_compatibility_sha256"]:
        errors.append("legacy compatibility SHA-256 mismatch")

    bound_paths = binding["implementation_roots"] + binding["test_roots"]
    for bound_path in bound_paths:
        if not (root / bound_path).exists():
            errors.append(f"bound path is missing: {bound_path}")

    checks = [
        "identity",
        "non_activation",
        "skill_hash",
        "capability_accounting",
        "alias_resolution",
        "fail_closed_dispatch",
        "legacy_parity",
        "repository_path_bindings",
    ]

    if (root / ".git").exists():
        base_commit = binding["pinned_base_commit"]
        shallow_result = run_git(root, "rev-parse", "--is-shallow-repository")
        is_shallow = (
            shallow_result.returncode == 0
            and shallow_result.stdout.strip() == "true"
        )
        base_object = run_git(
            root,
            "cat-file",
            "-e",
            f"{base_commit}^{{commit}}",
        )

        if base_object.returncode != 0:
            if is_shallow:
                checks.append("git_history_deferred_shallow_checkout")
            else:
                errors.append("pinned base commit object is unavailable")
        else:
            ancestry = run_git(
                root,
                "merge-base",
                "--is-ancestor",
                base_commit,
                "HEAD",
            )
            if ancestry.returncode != 0:
                errors.append("pinned base is not an ancestor of HEAD")

            diff = run_git(
                root,
                "diff",
                "--name-only",
                f"{base_commit}..HEAD",
            )
            if diff.returncode != 0:
                errors.append("git diff failed")
            else:
                changed_paths = [
                    path for path in diff.stdout.splitlines() if path
                ]
                allowed_paths = manifest["allowed_change_paths"]
                for changed_path in changed_paths:
                    if not is_allowed_path(changed_path, allowed_paths):
                        errors.append(f"out-of-scope change: {changed_path}")

                for legacy_surface in binding["legacy_surfaces"]:
                    legacy_prefix = legacy_surface.rstrip("/") + "/"
                    for changed_path in changed_paths:
                        if changed_path == legacy_surface or changed_path.startswith(
                            legacy_prefix
                        ):
                            errors.append(
                                "legacy surface was modified: "
                                f"{legacy_surface}"
                            )

            checks.extend(
                [
                    "exact_base_ancestry",
                    "change_scope",
                    "legacy_non_modification",
                ]
            )

    return {
        "schema_version": "1.0",
        "repository": binding["repository"],
        "pinned_base_commit": binding["pinned_base_commit"],
        "status": "success" if not errors else "failed",
        "checks": checks,
        "errors": errors,
        "capability_count": manifest["capability_count"],
        "module_count": manifest["module_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    result = validate(Path(args.root).resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
