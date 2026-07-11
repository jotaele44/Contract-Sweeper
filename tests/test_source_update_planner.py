"""DAG + planner tests for the source update controller."""

from __future__ import annotations

import pytest

from moneysweep.update_controller.models import SourceUpdatePolicy
from moneysweep.update_controller.planner import build_plan, evaluate_due
from moneysweep.update_controller.policy import (
    build_effective_policies,
    topological_order,
    validate_dag,
)

pytestmark = pytest.mark.unit

POLICIES = build_effective_policies()


def _pol(
    sid: str, trigger: str, depends_on=None, terminal=False, enabled=True
) -> SourceUpdatePolicy:
    return SourceUpdatePolicy(
        source_id=sid,
        trigger_type=trigger,
        enabled=enabled,
        runner=f"scripts/{sid}.py",
        freshness_sla_hours=192,
        timeout_minutes=60,
        max_retries=1,
        empty_result_policy="preserve_previous",
        depends_on=list(depends_on or []),
        terminal=terminal,
    )


def test_live_dag_is_acyclic_and_valid():
    errors, _warnings = validate_dag(POLICIES)
    assert errors == [], errors


def test_topological_order_is_deterministic():
    a = topological_order(POLICIES)
    b = topological_order(POLICIES)
    assert a == b


def test_topological_order_places_parents_first():
    order = topological_order(POLICIES)
    idx = {sid: i for i, sid in enumerate(order)}
    # legislapr_discovery must precede its dependents
    for child in ("legislapr_sessions", "legislative_canonical_sources"):
        assert idx["legislapr_discovery"] < idx[child]


def test_cycle_is_detected():
    pols = {
        "a": _pol("a", "dependency", ["b"]),
        "b": _pol("b", "dependency", ["a"]),
    }
    errors, _ = validate_dag(pols)
    assert any("cycle" in e for e in errors)


def test_self_dependency_rejected():
    pols = {"a": _pol("a", "dependency", ["a"])}
    errors, _ = validate_dag(pols)
    assert any("self-dependency" in e for e in errors)


def test_unknown_dependency_rejected():
    pols = {"a": _pol("a", "dependency", ["ghost"])}
    errors, _ = validate_dag(pols)
    assert any("unknown source" in e for e in errors)


def test_dependency_on_disabled_parent_rejected():
    pols = {
        "parent": _pol("parent", "disabled", enabled=False),
        "child": _pol("child", "dependency", ["parent"]),
    }
    errors, _ = validate_dag(pols)
    assert any("disabled source" in e for e in errors)


def test_dependency_on_terminal_parent_rejected():
    pols = {
        "dup": _pol("dup", "disabled", enabled=False, terminal=True),
        "child": _pol("child", "dependency", ["dup"]),
    }
    errors, _ = validate_dag(pols)
    assert any("terminal" in e for e in errors)


def test_schedule_never_run_is_due():
    pol = _pol("s", "schedule")
    pol.cadence = "weekly"
    state = {"sources": {"s": {"next_due_at": None}}}
    from datetime import datetime, timezone

    due, reason = evaluate_due(
        pol, state, __import__("pathlib").Path("."), datetime.now(timezone.utc)
    )
    assert due and "never scheduled" in reason


def test_manual_not_due_in_scan():
    pol = _pol("m", "manual")
    from datetime import datetime, timezone

    due, _ = evaluate_due(
        pol, {"sources": {}}, __import__("pathlib").Path("."), datetime.now(timezone.utc)
    )
    assert due is False


def test_plan_is_read_only_and_orders_selection():
    items = build_plan(policies=POLICIES, due_only=False)
    assert len(items) == 143
    # deterministic order indices
    assert [it.order_index for it in items] == sorted(it.order_index for it in items)


def test_plan_cadence_excludes_self_hosted():
    # sam_entities is monthly but self_hosted → excluded from the monthly batch
    items = build_plan(policies=POLICIES, cadence="monthly")
    ids = {it.source_id for it in items}
    assert "sam_entities" not in ids
