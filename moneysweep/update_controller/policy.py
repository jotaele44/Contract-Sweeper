"""Effective-policy resolution + validation for the source update controller.

Merges the policy overlay (registries/source_update_policy.yaml) against the
canonical source registry and the readiness path-type classification to produce
exactly one *effective* policy per canonical source. Validates each effective
policy against schemas/source_update_policy.schema.json using a self-contained
validator (no third-party jsonschema dependency).

Effective-policy precedence (spec §17):
  explicit overlay override
  → manual_export_registry entry (operator-gated fallback)
  → canonical source_registry authentication / manual_drop_dir
  → readiness path_type inference (spec §5).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from moneysweep.runtime.source_registry import load_source_registry
from moneysweep.update_controller.models import (
    CADENCE_SLA_HOURS,
    SCHEDULE_CADENCES,
    SourceUpdatePolicy,
    TriggerType,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = "registries/source_update_policy.yaml"
SCHEMA_PATH = "schemas/source_update_policy.schema.json"
MANUAL_EXPORT_REGISTRY = "registries/manual_export_registry.json"

# path_types that map to a permanently-disabled terminal policy (spec §5).
DISABLED_PATH_TYPES = frozenset({"scraper_needed", "deferred_stub", "semantic_duplicate"})
TERMINAL_PATH_TYPES = frozenset({"deferred_stub", "semantic_duplicate"})

# Authoritative dependency DAG (spec §7). This OVERRIDES the messier
# registry `depends_on` (which carries dangling non-source edges like
# contracts_master); the required DAG cleans those up.
REQUIRED_DAG: dict[str, list[str]] = {
    "prasa_contracts_master": ["prasa"],
    "emma_infra_revenue": ["emma_bonds"],
    "legislapr_sessions": ["legislapr_discovery"],
    "legislative_canonical_sources": ["legislapr_discovery", "legislapr_sessions"],
    "osl_sutra_crosswalk": ["legislative_canonical_sources"],
    "legislative_fiscal_link_candidates": [
        "legislative_canonical_sources",
        "osl_sutra_crosswalk",
    ],
    "ngo_integration_layer": ["nonprofits_irs990", "usaspending_prime"],
    "centinelas_pre_official_signals": [],
}

# Soft analytical links documented as downstream consumers, NOT blocking DAG
# parents (spec §7).
DOWNSTREAM_CONSUMERS: dict[str, str] = {
    "fec": "FEC cross-reference",
    "lda": "lobbying enrichment",
    "donaciones_pr": "political cross-reference",
    "contralor_electoral": "political cross-reference",
}

DEFAULT_FILE_DROP_PATTERNS = ["*.csv", "*.xlsx"]


class PolicyError(Exception):
    """Raised when the policy overlay is structurally invalid or inconsistent."""


# --------------------------------------------------------------------------- #
# Schema loading + self-contained validation
# --------------------------------------------------------------------------- #
def load_schema(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    return json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))


def _enum_values(schema: dict[str, Any], name: str) -> list[str]:
    return list(schema.get("$defs", {}).get(name, {}).get("enum", []))


def validate_effective_policy(policy: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate one effective policy against the schema's effective_source_policy
    definition. Returns a list of error strings (empty = valid).

    A focused interpreter for the subset of JSON-Schema constructs the schema
    uses (required, enum, type, and if/then conditionals) — keeps the schema file
    authoritative without a third-party validator.
    """
    errors: list[str] = []
    defn = schema.get("$defs", {}).get("effective_source_policy", {})
    sid = policy.get("source_id", "<unknown>")

    for req in defn.get("required", []):
        if policy.get(req) is None:
            errors.append(f"{sid}: missing required field '{req}'")

    enum_fields = {
        "trigger_type": "trigger_type",
        "execution_backend": "execution_backend",
        "empty_result_policy": "empty_result_policy",
        "output_change_policy": "output_change_policy",
        "dedupe_method": "dedupe_method",
        "trigger_dependents_on": "trigger_dependents_on",
        "checkpoint_strategy": "checkpoint_strategy",
    }
    for fld, defname in enum_fields.items():
        val = policy.get(fld)
        if val is None:
            continue
        allowed = _enum_values(schema, defname)
        if allowed and val not in allowed:
            errors.append(f"{sid}: field '{fld}'={val!r} not in {allowed}")

    # Conditional (if/then) requirements — interpret the allOf blocks.
    for block in defn.get("allOf", []):
        cond = block.get("if", {}).get("properties", {})
        matches = all(
            policy.get(k) == spec.get("const") for k, spec in cond.items() if "const" in spec
        )
        if not matches:
            continue
        then = block.get("then", {})
        for req in then.get("required", []):
            val = policy.get(req)
            if val is None or (isinstance(val, (list, str)) and len(val) == 0):
                errors.append(f"{sid}: trigger '{policy.get('trigger_type')}' requires '{req}'")
        for k, spec in then.get("properties", {}).items():
            val = policy.get(k)
            if "const" in spec and val != spec["const"]:
                errors.append(f"{sid}: field '{k}' must be {spec['const']!r} for this trigger")
            if "minItems" in spec and isinstance(val, list) and len(val) < spec["minItems"]:
                errors.append(f"{sid}: field '{k}' needs >= {spec['minItems']} item(s)")
            if "minLength" in spec and isinstance(val, str) and len(val) < spec["minLength"]:
                errors.append(f"{sid}: field '{k}' must be non-empty")
    return errors


# --------------------------------------------------------------------------- #
# Overlay + manual-export loading
# --------------------------------------------------------------------------- #
def load_overlay(root: Path | None = None, policy_path: str | Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    path = Path(policy_path) if policy_path else (root / DEFAULT_POLICY_PATH)
    if not path.is_absolute():
        path = root / path
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PolicyError(f"policy overlay is not a mapping: {path}")
    return data


def _manual_export_ids(root: Path) -> set[str]:
    path = root / MANUAL_EXPORT_REGISTRY
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    entries = data.get("sources") or data.get("manual_sources") or data.get("entries") or []
    ids: set[str] = set()
    for e in entries:
        if isinstance(e, dict) and e.get("source_id"):
            ids.add(e["source_id"])
    return ids


# --------------------------------------------------------------------------- #
# Trigger inference (spec §5) + effective-policy build
# --------------------------------------------------------------------------- #
def infer_trigger_type(
    path_type: str, cadence: str, dag_parents: list[str], manual_export: bool
) -> str | None:
    """Infer a trigger type from readiness path_type + cadence + DAG membership.

    Returns None for broken_producer (a policy/gate failure, not a trigger).
    """
    if path_type in DISABLED_PATH_TYPES:
        return TriggerType.DISABLED.value
    if path_type == "broken_producer":
        return None
    if path_type == "manual_export" or manual_export:
        return TriggerType.FILE_DROP.value
    if cadence == "on_drop":
        return TriggerType.ON_DROP.value
    if dag_parents:
        # A source with declared upstreams is derived → dependency-triggered.
        return TriggerType.DEPENDENCY.value
    if cadence == "ad_hoc":
        return TriggerType.MANUAL.value
    if cadence in SCHEDULE_CADENCES:
        return TriggerType.SCHEDULE.value
    return TriggerType.MANUAL.value


def _sla_for(cadence: str) -> float:
    sla = CADENCE_SLA_HOURS.get(cadence)
    return 0.0 if sla is None else float(sla)


def build_effective_policies(
    root: Path | None = None,
    policy_path: str | Path | None = None,
) -> dict[str, SourceUpdatePolicy]:
    """Resolve exactly one effective policy per canonical source (spec §17)."""
    # Local import to avoid a heavy import graph at module load and to break a
    # potential import cycle with the readiness classifier.
    from scripts.build_source_recovery_matrix import _classify

    root = root or REPO_ROOT
    overlay = load_overlay(root, policy_path)
    defaults = dict(overlay.get("defaults") or {})
    overrides = {e["source_id"]: e for e in overlay.get("sources") or [] if e.get("source_id")}
    manual_ids = _manual_export_ids(root)

    sources = load_source_registry(root).get("sources", [])
    policies: dict[str, SourceUpdatePolicy] = {}

    for src in sources:
        sid = src.get("source_id")
        if not sid:
            continue
        cadence = str(src.get("update_cadence") or "").strip().lower()
        path_type = _classify(src)
        override = overrides.get(sid, {})
        dag_parents = list(override.get("depends_on") or REQUIRED_DAG.get(sid, []))
        manual_export = sid in manual_ids

        inferred_trigger = infer_trigger_type(path_type, cadence, dag_parents, manual_export)
        trigger = override.get("trigger_type") or inferred_trigger
        if trigger is None:
            # broken_producer with no override — surface as a disabled/invalid
            # policy so the consistency gate can flag it deterministically.
            trigger = TriggerType.DISABLED.value

        is_disabled = trigger == TriggerType.DISABLED.value
        is_dependency = trigger == TriggerType.DEPENDENCY.value
        is_file_like = trigger in (TriggerType.FILE_DROP.value, TriggerType.ON_DROP.value)

        # runner
        runner = override.get("runner") or src.get("producer_script") or ""

        # secrets by name (never values)
        req_secrets = list(override.get("required_secrets") or [])
        auth = str(src.get("authentication") or "")
        if not req_secrets and auth.startswith("api_key:"):
            req_secrets = [auth.split(":", 1)[1]]

        # watch paths / patterns / dedupe for file-like triggers
        watch_paths = list(override.get("watch_paths") or [])
        if is_file_like and not watch_paths:
            drop = src.get("manual_drop_dir")
            if drop:
                watch_paths = [drop]
        patterns = list(override.get("filename_patterns") or [])
        if is_file_like and not patterns:
            patterns = list(DEFAULT_FILE_DROP_PATTERNS)
        dedupe = override.get("dedupe_method") or ("sha256" if is_file_like else None)

        # freshness SLA
        if "freshness_sla_hours" in override:
            sla = float(override["freshness_sla_hours"])
        elif is_disabled:
            sla = 0.0
        else:
            sla = _sla_for(cadence)

        # output change policy: dependency defaults to upstream_change
        default_ocp = (
            "upstream_change"
            if is_dependency
            else defaults.get("output_change_policy", "row_count_or_hash")
        )
        output_change_policy = override.get("output_change_policy", default_ocp)

        # cadence field: only schedule carries it (manual must not; §4)
        policy_cadence = None
        if trigger == TriggerType.SCHEDULE.value:
            policy_cadence = override.get("cadence") or (cadence if cadence else None)
        elif override.get("cadence") and trigger != TriggerType.MANUAL.value:
            policy_cadence = override.get("cadence")

        enabled = override.get("enabled")
        if enabled is None:
            enabled = not is_disabled

        source_of_policy = (
            "overlay"
            if sid in overrides
            else ("manual_export_registry" if manual_export else "inferred")
        )

        pol = SourceUpdatePolicy(
            source_id=sid,
            trigger_type=trigger,
            enabled=bool(enabled),
            runner=runner,
            freshness_sla_hours=sla,
            timeout_minutes=int(
                override.get("timeout_minutes", defaults.get("timeout_minutes", 60))
            ),
            max_retries=int(override.get("max_retries", defaults.get("max_retries", 2))),
            empty_result_policy=override.get(
                "empty_result_policy", defaults.get("empty_result_policy", "preserve_previous")
            ),
            output_change_policy=output_change_policy,
            execution_backend=override.get(
                "execution_backend", defaults.get("execution_backend", "github_actions")
            ),
            atomic_output_required=bool(
                override.get("atomic_output_required", defaults.get("atomic_output_required", True))
            ),
            freshness_grace_hours=float(
                override.get("freshness_grace_hours", defaults.get("freshness_grace_hours", 24))
            ),
            row_regression_tolerance_pct=float(
                override.get(
                    "row_regression_tolerance_pct",
                    defaults.get("row_regression_tolerance_pct", 40),
                )
            ),
            cadence=policy_cadence,
            cron=override.get("cron"),
            runner_args=list(override.get("runner_args") or []),
            required_secrets=req_secrets,
            depends_on=dag_parents,
            watch_paths=watch_paths,
            filename_patterns=patterns,
            dedupe_method=dedupe,
            checkpoint_strategy=override.get("checkpoint_strategy"),
            max_pages_per_run=override.get("max_pages_per_run"),
            trigger_dependents_on=override.get("trigger_dependents_on"),
            minimum_output_rows=override.get("minimum_output_rows"),
            notes=override.get("notes", "") or "",
            path_type=path_type,
            required=bool(src.get("required", False)),
            terminal=path_type in TERMINAL_PATH_TYPES,
            source_of_policy=source_of_policy,
        )
        policies[sid] = pol

    return policies


def canonical_source_ids(root: Path | None = None) -> list[str]:
    root = root or REPO_ROOT
    return sorted(
        s["source_id"] for s in load_source_registry(root).get("sources", []) if s.get("source_id")
    )


def registry_snapshot(root: Path | None = None) -> dict[str, Any]:
    ids = canonical_source_ids(root)
    digest = hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()
    return {"source_count": len(ids), "source_ids_sha256": digest}


def policy_hash(policies: dict[str, SourceUpdatePolicy]) -> str:
    payload = json.dumps(
        [policies[k].to_dict() for k in sorted(policies)], sort_keys=True, ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_policy(
    root: Path | None = None,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Full policy validation (spec §11 validate-policy). Returns a report dict
    with ``ok`` and ``errors``. Does NOT import or run producers.
    """
    root = root or REPO_ROOT
    errors: list[str] = []
    warnings: list[str] = []

    overlay = load_overlay(root, policy_path)
    if overlay.get("schema_version") != "source_update_policy_v1":
        errors.append(f"overlay schema_version mismatch: {overlay.get('schema_version')!r}")

    canonical = set(canonical_source_ids(root))
    override_ids = [e.get("source_id") for e in overlay.get("sources") or []]
    for oid in override_ids:
        if oid not in canonical:
            errors.append(f"orphan policy override for unknown source_id: {oid!r}")
    if len(override_ids) != len(set(override_ids)):
        errors.append("duplicate source_id in policy overlay")

    schema = load_schema(root)
    policies = build_effective_policies(root, policy_path)

    # exactly one effective policy per canonical source
    missing = sorted(canonical - set(policies))
    extra = sorted(set(policies) - canonical)
    if missing:
        errors.append(f"sources without an effective policy: {missing}")
    if extra:
        errors.append(f"effective policies for non-canonical sources: {extra}")

    for sid in sorted(policies):
        errors.extend(validate_effective_policy(policies[sid].to_dict(), schema))

    # DAG gates (spec §7)
    dag_errors, dag_warnings = validate_dag(policies)
    errors.extend(dag_errors)
    warnings.extend(dag_warnings)

    snapshot = registry_snapshot(root)
    return {
        "schema_version": "source_update_policy_report_v1",
        "ok": not errors,
        "source_count": snapshot["source_count"],
        "source_ids_sha256": snapshot["source_ids_sha256"],
        "policy_coverage": f"{len(policies)}/{snapshot['source_count']}",
        "effective_policy_count": len(policies),
        "override_count": len(override_ids),
        "policy_hash": policy_hash(policies),
        "trigger_distribution": _trigger_distribution(policies),
        "errors": errors,
        "warnings": warnings,
    }


def validate_dag(policies: dict[str, SourceUpdatePolicy]) -> tuple[list[str], list[str]]:
    """Validate the dependency DAG (spec §7). Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    known = set(policies)
    disabled = {sid for sid, p in policies.items() if p.trigger_type == TriggerType.DISABLED.value}
    terminal = {sid for sid, p in policies.items() if p.terminal}

    for sid, pol in policies.items():
        for parent in pol.depends_on:
            if parent == sid:
                errors.append(f"{sid}: self-dependency")
                continue
            if parent not in known:
                errors.append(f"{sid}: dependency on unknown source '{parent}'")
                continue
            if parent in disabled and sid not in disabled:
                errors.append(f"{sid}: depends on disabled source '{parent}'")
            if parent in terminal:
                errors.append(f"{sid}: depends on semantic-duplicate/terminal source '{parent}'")

    # cycle detection
    cycle = _find_cycle(policies)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))
    return errors, warnings


def _find_cycle(policies: dict[str, SourceUpdatePolicy]) -> list[str]:
    """Return one cycle path if the DAG has a cycle, else []."""
    graph = {sid: [p for p in pol.depends_on if p in policies] for sid, pol in policies.items()}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        color[node] = GREY
        stack.append(node)
        for parent in sorted(graph.get(node, [])):
            if color[parent] == GREY:
                idx = stack.index(parent)
                return stack[idx:] + [parent]
            if color[parent] == WHITE:
                found = visit(parent)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return []

    for n in sorted(graph):
        if color[n] == WHITE:
            found = visit(n)
            if found:
                return found
    return []


def topological_order(
    policies: dict[str, SourceUpdatePolicy], subset: set[str] | None = None
) -> list[str]:
    """Deterministic topological order (ties broken by source_id, spec §7)."""
    nodes = set(policies) if subset is None else set(subset)
    graph = {
        sid: [p for p in policies[sid].depends_on if p in nodes] for sid in nodes if sid in policies
    }
    order: list[str] = []
    visited: dict[str, int] = {}

    def visit(node: str) -> None:
        state = visited.get(node, 0)
        if state == 2:
            return
        visited[node] = 1
        for parent in sorted(graph.get(node, [])):
            if visited.get(parent, 0) != 1:
                visit(parent)
        visited[node] = 2
        order.append(node)

    for n in sorted(graph):
        visit(n)
    return order


def _trigger_distribution(policies: dict[str, SourceUpdatePolicy]) -> dict[str, int]:
    dist: dict[str, int] = {t.value: 0 for t in TriggerType}
    for pol in policies.values():
        dist[pol.trigger_type] = dist.get(pol.trigger_type, 0) + 1
    return dist
