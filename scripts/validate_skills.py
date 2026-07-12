"""Offline validator for the MoneySweep PRII skill packet (blueprint §9).

Runs the ten packet checks with no network and no live source acquisition:
structure, registry, command-resolution, path-resolution, boundary-policy,
mode-safety, coverage-accounting, export-contract (local), activation, drift.

Each check is a function returning ``list[str]`` of human-readable errors
(empty = pass). ``run_all`` aggregates them; the CLI exits non-zero on any
failure. Stdlib + PyYAML only (matches scripts/regenerate_registry_json.py).

Usage:
  python3 scripts/validate_skills.py            # all checks, human output
  python3 scripts/validate_skills.py --json      # machine-readable
  python3 scripts/validate_skills.py --check command-resolution   # one check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install PyYAML", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = "skills"
REGISTRY = "skill-registry.yaml"
ACTIVATION = "activation-matrix.yaml"
DEPENDENCY = "dependency-graph.yaml"
CONTRACT_SCHEMA = "schemas/prii_skill_contract.schema.json"

SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9-]+$")
ALLOWED_MODES = frozenset({"read_only", "offline_write", "live_network", "promotion"})
SAFE_DEFAULT_MODES = frozenset({"read_only", "offline_write"})
GATED_MODES = frozenset({"live_network", "promotion"})
# Skill-folder entries that are allowed (no skill-level README, per §3).
ALLOWED_SKILL_ENTRIES = frozenset({"SKILL.md", "agents", "references", "scripts"})
ACTIVATION_ROUTES = frozenset({"route_to_hub", "route_to_centinelas", "clarify"})


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def _load_yaml(root: Path, rel: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load((root / rel).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except OSError:
        return {}


def _load_json(root: Path, rel: str) -> dict[str, Any]:
    try:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _registry_skills(root: Path) -> list[dict[str, Any]]:
    return list(_load_yaml(root, REGISTRY).get("skills") or [])


def _hub_command_ids(root: Path) -> set[str]:
    return set(_load_json(root, "federation.json").get("hub_callable_commands") or {})


def _frontmatter(text: str) -> dict[str, Any] | None:
    """Parse a leading ``---`` YAML frontmatter block from a SKILL.md."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        block = yaml.safe_load(text[3:end])
        return block if isinstance(block, dict) else None
    except yaml.YAMLError:
        return None


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_skill_structure(root: Path) -> list[str]:
    errors: list[str] = []
    for skill in _registry_skills(root):
        sid = skill.get("skill_id", "<unknown>")
        folder = root / SKILLS_DIR / sid
        if not folder.is_dir():
            errors.append(f"{sid}: skills/{sid}/ directory is missing")
            continue
        if not SKILL_ID_RE.match(sid):
            errors.append(f"{sid}: folder name is not lowercase-hyphenated")
        skill_md = folder / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"{sid}: SKILL.md is missing")
        else:
            fm = _frontmatter(skill_md.read_text(encoding="utf-8"))
            if fm is None:
                errors.append(f"{sid}: SKILL.md has no valid YAML frontmatter")
            else:
                for field in ("name", "description"):
                    if not fm.get(field):
                        errors.append(f"{sid}: SKILL.md frontmatter missing '{field}'")
                if fm.get("name") and fm["name"] != sid:
                    errors.append(f"{sid}: SKILL.md name '{fm['name']}' != folder id")
        if not (folder / "agents" / "openai.yaml").is_file():
            errors.append(f"{sid}: agents/openai.yaml is missing")
        for entry in folder.iterdir():
            if entry.name not in ALLOWED_SKILL_ENTRIES:
                errors.append(
                    f"{sid}: prohibited skill entry '{entry.name}' (no skill-level README)"
                )
    return errors


def _validate_contract_entry(skill: dict[str, Any]) -> list[str]:
    """Self-contained validation of one entry against prii_skill_contract_v1."""
    sid = skill.get("skill_id", "<unknown>")
    errors: list[str] = []
    required = (
        "schema_version",
        "skill_id",
        "owner_repo",
        "federation_role",
        "trigger_intents",
        "allowed_modes",
        "default_mode",
        "command_ids",
        "boundary_owner",
        "forbidden_operations",
        "stop_conditions",
        "evidence_requirements",
    )
    for field in required:
        if field not in skill:
            errors.append(f"{sid}: missing required contract field '{field}'")
    if skill.get("schema_version") != "prii_skill_contract_v1":
        errors.append(f"{sid}: schema_version must be prii_skill_contract_v1")
    if not SKILL_ID_RE.match(sid):
        errors.append(f"{sid}: skill_id is not lowercase-hyphenated")
    for list_field in (
        "trigger_intents",
        "stop_conditions",
        "evidence_requirements",
        "forbidden_operations",
    ):
        val = skill.get(list_field)
        if not isinstance(val, list) or not val:
            errors.append(f"{sid}: '{list_field}' must be a non-empty list")
    modes = skill.get("allowed_modes") or []
    bad_modes = set(modes) - ALLOWED_MODES
    if bad_modes:
        errors.append(f"{sid}: unknown allowed_modes {sorted(bad_modes)}")
    if skill.get("default_mode") not in ALLOWED_MODES:
        errors.append(f"{sid}: default_mode {skill.get('default_mode')!r} not a known mode")
    elif skill.get("default_mode") not in modes:
        errors.append(f"{sid}: default_mode not in allowed_modes")
    return errors


def check_skill_registry(root: Path) -> list[str]:
    errors: list[str] = []
    skills = _registry_skills(root)
    if not skills:
        return [f"{REGISTRY}: no skills declared or file unreadable"]
    ids = [str(s.get("skill_id")) for s in skills]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate skill_id(s): {sorted(dupes)}")
    for skill in skills:
        errors.extend(_validate_contract_entry(skill))
    # No orphan folders: every skills/<dir> must be registered.
    skills_root = root / SKILLS_DIR
    if skills_root.is_dir():
        registered = set(ids)
        for entry in skills_root.iterdir():
            if entry.is_dir() and entry.name not in registered:
                errors.append(f"orphan skill folder not in registry: skills/{entry.name}")
    return errors


def check_command_resolution(root: Path) -> list[str]:
    errors: list[str] = []
    hub = _hub_command_ids(root)
    if not hub:
        return ["federation.json#hub_callable_commands is empty or unreadable"]
    for skill in _registry_skills(root):
        sid = skill.get("skill_id", "<unknown>")
        for cid in skill.get("command_ids") or []:
            if cid not in hub:
                errors.append(f"{sid}: command_id '{cid}' does not resolve in federation.json")
    return errors


def check_path_resolution(root: Path) -> list[str]:
    errors: list[str] = []
    for skill in _registry_skills(root):
        sid = skill.get("skill_id", "<unknown>")
        for key in ("local_scripts", "reads", "writes"):
            for rel in skill.get(key) or []:
                # writes may legitimately not exist yet; only path-check inputs.
                if key == "writes":
                    continue
                if not (root / rel).exists():
                    errors.append(f"{sid}: {key} path does not exist: {rel}")
    return errors


def check_boundary_policy(root: Path) -> list[str]:
    errors: list[str] = []
    owner = _load_yaml(root, REGISTRY).get("owner_repo", "jotaele44/moneysweep-pr")
    for skill in _registry_skills(root):
        sid = skill.get("skill_id", "<unknown>")
        if skill.get("owner_repo") != owner:
            errors.append(f"{sid}: owner_repo != registry owner {owner}")
        if skill.get("boundary_owner") != "moneysweep-pr":
            errors.append(f"{sid}: boundary_owner must be 'moneysweep-pr'")
        if not (skill.get("forbidden_operations") or []):
            errors.append(f"{sid}: forbidden_operations must be declared (boundary guard)")
    return errors


def check_mode_safety(root: Path) -> list[str]:
    errors: list[str] = []
    for skill in _registry_skills(root):
        sid = skill.get("skill_id", "<unknown>")
        default = skill.get("default_mode")
        if default not in SAFE_DEFAULT_MODES:
            errors.append(
                f"{sid}: default_mode '{default}' is not a safe default (read_only/offline_write)"
            )
        gated = set(skill.get("allowed_modes") or []) & GATED_MODES
        if gated and not (skill.get("requires_user_authorization") or []):
            errors.append(
                f"{sid}: {sorted(gated)} allowed but requires_user_authorization is empty"
            )
        for secret in skill.get("requires_secrets") or []:
            if "=" in secret or "/" in secret:
                errors.append(f"{sid}: requires_secrets must list names only, got {secret!r}")
    return errors


def check_coverage_accounting(root: Path) -> list[str]:
    """The readiness truth must self-reconcile (blueprint §7 rule 4)."""
    errors: list[str] = []
    r = _load_json(root, "reports/materialization_readiness.json")
    if not r:
        return ["reports/materialization_readiness.json unreadable"]
    total = r.get("total_sources")
    auto = r.get("automatable_total")
    queued_total = r.get("queued_excluded_total")
    queued = r.get("queued_excluded") or {}
    if isinstance(total, int) and isinstance(auto, int) and isinstance(queued_total, int):
        if auto + queued_total != total:
            errors.append(
                f"readiness: automatable({auto}) + queued({queued_total}) != total({total})"
            )
        if sum(queued.values()) != queued_total:
            errors.append(
                f"readiness: queued_excluded values sum {sum(queued.values())} != {queued_total}"
            )
    else:
        errors.append("readiness: total/automatable/queued counts are not all integers")
    if not (r.get("source_count_provenance") or {}).get("source_ids_sha256"):
        errors.append("readiness: missing source_ids_sha256 (registry hash provenance)")
    return errors


def check_export_contract(root: Path) -> list[str]:
    """Local export-contract sanity: the export command resolves and the
    canonical bridge exists. (Full Hub-schema compat runs in prii-check-producer-contract.)"""
    errors: list[str] = []
    hub = _hub_command_ids(root)
    if "export_canonical" not in hub:
        errors.append("federation.json missing export_canonical command")
    if not (root / "moneysweep" / "federation" / "canonical_v1_bridge.py").exists():
        errors.append("canonical_v1_bridge.py missing (export skill dependency)")
    return errors


def check_activation(root: Path) -> list[str]:
    errors: list[str] = []
    matrix = _load_yaml(root, ACTIVATION)
    known = {s.get("skill_id") for s in _registry_skills(root)}
    for bucket in ("positive", "negative", "ambiguous"):
        for case in matrix.get(bucket) or []:
            expect = case.get("expect")
            if expect not in known and expect not in ACTIVATION_ROUTES:
                errors.append(
                    f"activation[{bucket}]: expect '{expect}' is not a skill or known route"
                )
            if not case.get("prompt"):
                errors.append(f"activation[{bucket}]: a case is missing its prompt")
    return errors


def check_drift(root: Path) -> list[str]:
    """Dependency-graph nodes + invariant targets must all be real skills, and
    every command a skill claims must still exist (stale-reference guard)."""
    errors: list[str] = []
    known = {s.get("skill_id") for s in _registry_skills(root)}
    graph = _load_yaml(root, DEPENDENCY)
    for parent, children in (graph.get("edges") or {}).items():
        for node in [parent, *children]:
            if node not in known:
                errors.append(f"dependency-graph node '{node}' is not a registered skill")
    for inv in graph.get("invariants") or []:
        for node in inv.get("applies_to") or []:
            if node not in known:
                errors.append(f"invariant '{inv.get('id')}' targets unknown skill '{node}'")
    if graph.get("root") and graph["root"] not in known:
        errors.append(f"dependency-graph root '{graph['root']}' is not a registered skill")
    return errors


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    "skill-structure": check_skill_structure,
    "skill-registry": check_skill_registry,
    "command-resolution": check_command_resolution,
    "path-resolution": check_path_resolution,
    "boundary-policy": check_boundary_policy,
    "mode-safety": check_mode_safety,
    "coverage-accounting": check_coverage_accounting,
    "export-contract": check_export_contract,
    "activation": check_activation,
    "drift": check_drift,
}


def run_all(root: Path, only: str | None = None) -> dict[str, list[str]]:
    checks = {only: CHECKS[only]} if only else CHECKS
    return {name: fn(root) for name, fn in checks.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--check", choices=sorted(CHECKS), help="run one check only")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    results = run_all(Path(args.root), only=args.check)
    total = sum(len(v) for v in results.values())
    if args.json:
        print(json.dumps({"ok": total == 0, "errors": results}, indent=2))
    else:
        for name, errs in results.items():
            mark = "ok" if not errs else "FAIL"
            print(f"[{mark}] {name}")
            for e in errs:
                print(f"    - {e}")
        print(f"\n{total} error(s) across {len(results)} check(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
