"""State store for the source update controller.

Owns the per-source state file (atomic JSON write) and the append-only run /
failure ledgers. State is initialized for every canonical source; the committed
``reports/source_update_state.json`` is an empty template — runtime writes go to
the tracked file only when an operator runs locally, and CI never commits state
(it uploads artifacts instead).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.update_controller.models import (
    SourceUpdatePolicy,
    new_source_state,
)
from moneysweep.update_controller.policy import build_effective_policies, registry_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_REL = "reports/source_update_state.json"
# Runtime ledgers are the gitignored ``.local.jsonl`` variants (spec §20); the
# committed ``*.jsonl`` files are empty templates.
RUNS_REL = "reports/source_update_runs.local.jsonl"
FAILURES_REL = "reports/source_update_failures.local.jsonl"

STATE_SCHEMA_VERSION = "source_update_state_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _registry_schema_version(root: Path) -> str:
    from moneysweep.runtime.source_registry import load_source_registry

    return str(load_source_registry(root).get("schema_version") or "")


def empty_state_template(root: Path | None = None) -> dict[str, Any]:
    """The committed template: registry snapshot placeholders + no per-source rows."""
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "registry_snapshot": {
            "source_registry_schema_version": "r5_source_registry_v1",
            "source_count": 144,
            "source_ids_sha256": "",
            "generated_at": "",
        },
        "sources": {},
    }


def init_state(
    root: Path | None = None,
    policies: dict[str, SourceUpdatePolicy] | None = None,
) -> dict[str, Any]:
    """Build a fresh state initialized for every canonical source."""
    root = root or REPO_ROOT
    policies = policies if policies is not None else build_effective_policies(root)
    snap = registry_snapshot(root)
    sources: dict[str, Any] = {}
    for sid in sorted(policies):
        pol = policies[sid]
        sources[sid] = new_source_state(sid, pol.trigger_type, pol.enabled)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "registry_snapshot": {
            "source_registry_schema_version": _registry_schema_version(root),
            "source_count": snap["source_count"],
            "source_ids_sha256": snap["source_ids_sha256"],
            "generated_at": _now_iso(),
        },
        "sources": sources,
    }


def load_state(
    root: Path | None = None,
    state_path: str | Path | None = None,
    policies: dict[str, SourceUpdatePolicy] | None = None,
) -> dict[str, Any]:
    """Load state, initializing (in memory) any canonical source not yet present.

    Sources present in the state file but no longer canonical are preserved as
    ``retired`` state (explicit-migration rule, spec §8) rather than dropped.
    """
    root = root or REPO_ROOT
    path = _resolve(root, state_path, STATE_REL)
    policies = policies if policies is not None else build_effective_policies(root)

    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            state = empty_state_template(root)
    else:
        state = empty_state_template(root)

    if not isinstance(state, dict):
        state = empty_state_template(root)
    state.setdefault("schema_version", STATE_SCHEMA_VERSION)
    existing = state.get("sources")
    if not isinstance(existing, dict):
        existing = {}
    merged: dict[str, Any] = dict(existing)

    canonical = set(policies)
    for sid in sorted(canonical):
        if sid not in merged:
            merged[sid] = new_source_state(sid, policies[sid].trigger_type, policies[sid].enabled)
        else:
            # keep historical row; refresh declared trigger/enabled from policy
            merged[sid]["trigger_type"] = policies[sid].trigger_type
            merged[sid]["enabled"] = policies[sid].enabled

    # retire rows for sources that are no longer canonical (preserve, don't drop)
    for sid in list(merged):
        if sid not in canonical:
            merged[sid]["retired"] = True

    state["sources"] = merged
    rs = state.get("registry_snapshot") or {}
    try:
        snap = registry_snapshot(root)
        rs.update(
            {
                "source_registry_schema_version": _registry_schema_version(root),
                "source_count": snap["source_count"],
                "source_ids_sha256": snap["source_ids_sha256"],
            }
        )
    except Exception:
        # A caller may pass a synthetic root without a full registry (tests);
        # keep any existing snapshot rather than failing the load.
        rs.setdefault("source_count", len(canonical))
    rs.setdefault("generated_at", "")
    state["registry_snapshot"] = rs
    return state


def registry_changed(state: dict[str, Any], root: Path | None = None) -> bool:
    """True if the live registry's source-id hash differs from the state snapshot."""
    root = root or REPO_ROOT
    snap = registry_snapshot(root)
    prev = (state.get("registry_snapshot") or {}).get("source_ids_sha256")
    return bool(prev) and prev != snap["source_ids_sha256"]


def write_state(
    state: dict[str, Any],
    root: Path | None = None,
    state_path: str | Path | None = None,
) -> Path:
    """Atomically write the state JSON (tmp file + os.replace)."""
    root = root or REPO_ROOT
    path = _resolve(root, state_path, STATE_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    rs = state.get("registry_snapshot") or {}
    rs["generated_at"] = _now_iso()
    state["registry_snapshot"] = rs
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def append_jsonl(root: Path, rel: str, record: dict[str, Any]) -> Path:
    """Append one JSON record as a line to a ledger file."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def append_run(record: dict[str, Any], root: Path | None = None) -> Path:
    return append_jsonl(root or REPO_ROOT, RUNS_REL, record)


def append_failure(packet: dict[str, Any], root: Path | None = None) -> Path:
    return append_jsonl(root or REPO_ROOT, FAILURES_REL, packet)


def _resolve(root: Path, override: str | Path | None, default_rel: str) -> Path:
    if override:
        p = Path(override)
        return p if p.is_absolute() else (root / p)
    return root / default_rel
