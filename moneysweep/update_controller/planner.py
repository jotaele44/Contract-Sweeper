"""Update planner (spec §6 / §10 / §11).

Determines which sources are *due*, resolves trigger eligibility, evaluates
secret presence **by name only**, and returns a deterministic topologically
ordered plan. Planning is strictly read-only: it never imports or runs a
producer, makes no network calls, and writes no output.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.update_controller.drop_scanner import has_new_drop
from moneysweep.update_controller.models import (
    SCHEDULE_CADENCES,
    SourceUpdatePolicy,
    UpdatePlanItem,
)
from moneysweep.update_controller.policy import build_effective_policies, topological_order

REPO_ROOT = Path(__file__).resolve().parents[2]


def _dotenv(root: Path) -> dict[str, Any]:
    try:
        from scripts.pipeline_preflight import _load_dotenv_dict

        return _load_dotenv_dict(root)
    except Exception:
        return {}


def secret_present(name: str, dotenv: dict[str, Any]) -> bool:
    """True if a secret is set via environment or .env — never returns the value."""
    if os.environ.get(name, "").strip():
        return True
    return bool(str(dotenv.get(name, "")).strip())


def missing_secrets(policy: SourceUpdatePolicy, dotenv: dict[str, Any]) -> list[str]:
    return [s for s in policy.required_secrets if not secret_present(s, dotenv)]


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def evaluate_due(
    policy: SourceUpdatePolicy,
    state: dict[str, Any],
    root: Path,
    now: datetime,
    consumed_path: str | Path | None = None,
) -> tuple[bool, str]:
    """Return (due, reason) for one source per the §6 planning rules."""
    trigger = policy.trigger_type
    row = state.get("sources", {}).get(policy.source_id, {})

    if trigger == "disabled" or not policy.enabled:
        return False, "disabled"

    if trigger == "manual":
        return False, "manual — requires explicit --source/--trigger manual"

    if trigger == "schedule":
        next_due = _parse_iso(row.get("next_due_at"))
        if next_due is None:
            return True, "never scheduled"
        return (now >= next_due), (
            "due (past next_due_at)" if now >= next_due else "not due until next_due_at"
        )

    if trigger in ("file_drop", "on_drop"):
        if has_new_drop(policy, root, consumed_path):
            return True, "new unconsumed drop detected"
        return False, "no new drop"

    if trigger == "dependency":
        parents = policy.depends_on
        srcs = state.get("sources", {})
        if not parents:
            return True, "dependency with no parents (leaf) — eligible"
        consumed = row.get("dependency_versions_consumed", {}) or {}
        all_ok = True
        changed = False
        for parent in parents:
            prow = srcs.get(parent, {})
            if not prow.get("last_success_at"):
                all_ok = False
                break
            phash = prow.get("output_manifest_hash")
            if phash and consumed.get(parent) != phash:
                changed = True
        if not all_ok:
            return False, "dependency not ready (a parent has not succeeded)"
        if not changed:
            return False, "no upstream change since last consumed"
        return True, "upstream changed"

    return False, "unknown trigger"


def _select_ids(
    policies: dict[str, SourceUpdatePolicy],
    *,
    source: str | None,
    cadence: str | None,
    trigger: str | None,
) -> list[str]:
    if source:
        return [source] if source in policies else []
    if cadence:
        c = cadence.strip().lower()
        # Cadence batches target github-hosted-eligible sources only; self-hosted
        # long-running sources (ocpr_contracts, sam_entities) run via the dispatch
        # workflow, never the hosted cron (spec §15 self-hosted exclusion).
        return sorted(
            sid
            for sid, p in policies.items()
            if p.trigger_type == "schedule"
            and (p.cadence or "").lower() == c
            and p.execution_backend == "github_actions"
        )
    if trigger:
        t = trigger.strip().lower()
        return sorted(sid for sid, p in policies.items() if p.trigger_type == t)
    return sorted(policies)


def build_plan(
    root: Path | None = None,
    *,
    policies: dict[str, SourceUpdatePolicy] | None = None,
    state: dict[str, Any] | None = None,
    source: str | None = None,
    cadence: str | None = None,
    trigger: str | None = None,
    due_only: bool = False,
    now: datetime | None = None,
    consumed_path: str | Path | None = None,
    max_sources: int | None = None,
) -> list[UpdatePlanItem]:
    root = root or REPO_ROOT
    now = now or datetime.now(timezone.utc)
    if policies is None:
        policies = build_effective_policies(root)
    if state is None:
        from moneysweep.update_controller.state import load_state

        state = load_state(root, policies=policies)
    dotenv = _dotenv(root)

    selected = _select_ids(policies, source=source, cadence=cadence, trigger=trigger)
    selected_set = set(selected)
    order = topological_order(policies, subset=selected_set)
    # ensure any selected node absent from the ordered graph still appears
    for sid in selected:
        if sid not in order:
            order.append(sid)

    items: list[UpdatePlanItem] = []
    for idx, sid in enumerate(order):
        if sid not in selected_set:
            continue
        pol = policies[sid]
        if source and sid == source and pol.trigger_type == "manual":
            due, reason = True, "explicitly selected (manual)"
        else:
            due, reason = evaluate_due(pol, state, root, now, consumed_path)
        item = UpdatePlanItem(
            source_id=sid,
            trigger_type=pol.trigger_type,
            due=due,
            reason=reason,
            enabled=pol.enabled,
            order_index=idx,
            depends_on=list(pol.depends_on),
            required_secrets=list(pol.required_secrets),
            missing_secrets=missing_secrets(pol, dotenv),
        )
        items.append(item)

    if due_only:
        items = [it for it in items if it.due]
    if max_sources is not None:
        items = items[:max_sources]
    return items


def cadence_members(policies: dict[str, SourceUpdatePolicy], cadence: str) -> list[str]:
    c = cadence.strip().lower()
    return sorted(
        sid
        for sid, p in policies.items()
        if p.trigger_type == "schedule"
        and (p.cadence or "").lower() == c
        and p.execution_backend == "github_actions"
    )


def scheduled_cadence_counts(policies: dict[str, SourceUpdatePolicy]) -> dict[str, int]:
    return {c: len(cadence_members(policies, c)) for c in SCHEDULE_CADENCES}
