"""Command-line interface for the source update controller (spec §11).

Commands: validate-policy, plan, run, scan-drops, ingest-drops, freshness,
state, resume. ``plan`` and ``validate-policy`` are strictly read-only and make
no network calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.runtime.source_registry import load_source_registry
from moneysweep.update_controller.policy import (
    REPO_ROOT,
    build_effective_policies,
    validate_policy,
)

FRESHNESS_CSV = "reports/source_freshness.csv"
FRESHNESS_COLUMNS = [
    "source_id",
    "trigger_type",
    "enabled",
    "required",
    "path_type",
    "update_cadence",
    "freshness_sla_hours",
    "last_success_at",
    "last_materialized_at",
    "age_hours",
    "freshness_status",
    "next_due_at",
    "consecutive_failures",
    "last_status",
]


def _registry_map(root: Path) -> dict[str, dict[str, Any]]:
    return {
        s["source_id"]: s
        for s in load_source_registry(root).get("sources", [])
        if s.get("source_id")
    }


def _emit(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        print(obj)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_validate_policy(args: argparse.Namespace) -> int:
    report = validate_policy(args.root, args.policy)
    if args.json:
        _emit(report, True)
    else:
        print(f"policy_coverage: {report['policy_coverage']}")
        print(f"source_count:    {report['source_count']}")
        print(f"trigger_distribution: {report['trigger_distribution']}")
        if report["errors"]:
            print("ERRORS:")
            for e in report["errors"]:
                print(f"  - {e}")
        else:
            print("OK: policy valid (0 errors)")
        for w in report["warnings"]:
            print(f"  warning: {w}")
    return 0 if report["ok"] else 2


def cmd_plan(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.planner import build_plan

    policies = build_effective_policies(args.root, args.policy)
    items = build_plan(
        args.root,
        policies=policies,
        source=args.source,
        cadence=args.cadence,
        trigger=args.trigger,
        due_only=args.due,
        max_sources=args.max_sources,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected": len(items),
        "due": sum(1 for it in items if it.due),
        "plan": [it.to_dict() for it in items],
    }
    if args.json:
        _emit(payload, True)
    else:
        for it in items:
            flag = "DUE " if it.due else "    "
            print(
                f"  [{flag}] {it.order_index:>3} {it.source_id:40s} {it.trigger_type:11s} {it.reason}"
            )
        print(f"  {payload['due']}/{payload['selected']} due")
    return 0


def cmd_freshness(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.state import load_state
    from moneysweep.update_controller.validation import compute_freshness, freshness_exit_code

    policies = build_effective_policies(args.root, args.policy)
    state = load_state(args.root, args.state, policies=policies)
    reg = _registry_map(args.root)
    now = datetime.now(timezone.utc)
    results = []
    for sid in sorted(policies):
        pol = policies[sid]
        entry = reg.get(sid, {})
        cadence = str(entry.get("update_cadence") or "")
        expected = list(entry.get("expected_outputs") or [])
        has_output = any((args.root / p).exists() for p in expected)
        results.append(
            compute_freshness(pol, state.get("sources", {}).get(sid, {}), cadence, has_output, now)
        )

    # write the tracked CSV
    csv_path = args.root / FRESHNESS_CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FRESHNESS_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_row())

    code = freshness_exit_code(results)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.freshness_status] = counts.get(r.freshness_status, 0) + 1
    payload = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_count": len(results),
        "status_counts": counts,
        "exit_code": code,
        "csv": FRESHNESS_CSV,
    }
    if args.json:
        _emit(payload, True)
    else:
        print(f"freshness: {counts}")
        print(f"wrote {FRESHNESS_CSV}  exit={code}")
    return code


def cmd_scan_drops(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.drop_scanner import scan_all

    policies = build_effective_policies(args.root, args.policy)
    found = scan_all(policies, args.root, args.consumed)
    payload = {sid: [c.to_dict() for c in cands] for sid, cands in found.items()}
    if args.json:
        _emit(payload, True)
    else:
        if not payload:
            print("no drop candidates")
        for sid, cands in payload.items():
            for c in cands:
                mark = "NEW" if c["is_new"] else "   "
                print(f"  [{mark}] {sid:35s} {c['path']}  {c['sha256'][:12]}")
    return 0


def cmd_ingest_drops(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.drop_scanner import has_new_drop
    from moneysweep.update_controller.executor import run_source
    from moneysweep.update_controller.planner import _dotenv
    from moneysweep.update_controller.state import load_state, write_state

    policies = build_effective_policies(args.root, args.policy)
    state = load_state(args.root, args.state, policies=policies)
    reg = _registry_map(args.root)
    dotenv = _dotenv(args.root)
    ran: list[dict[str, Any]] = []
    for sid in sorted(policies):
        pol = policies[sid]
        if pol.trigger_type not in ("file_drop", "on_drop") or not pol.enabled:
            continue
        if not has_new_drop(pol, args.root, args.consumed):
            continue
        res = run_source(
            pol,
            reg.get(sid, {}),
            state,
            root=args.root,
            dotenv=dotenv,
            consumed_path=args.consumed,
            dry_run=args.dry_run,
            strict=True,
        )
        ran.append(res)
    if not args.dry_run:
        write_state(state, args.root, args.state)
    _emit({"ingested": len(ran), "results": ran}, args.json)
    return (
        0
        if all(
            r["status"] not in ("PRODUCER_EXECUTION_FAILED", "PRODUCER_IMPORT_FAILED") for r in ran
        )
        else 1
    )


def cmd_run(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.executor import run_source
    from moneysweep.update_controller.planner import _dotenv, build_plan
    from moneysweep.update_controller.state import load_state, write_state
    from moneysweep.update_controller.models import SUCCESS_STATUSES, ExecutionStatus

    policies = build_effective_policies(args.root, args.policy)
    state = load_state(args.root, args.state, policies=policies)
    reg = _registry_map(args.root)
    dotenv = _dotenv(args.root)

    due_only = not (args.source or args.trigger == "manual")
    items = build_plan(
        args.root,
        policies=policies,
        state=state,
        source=args.source,
        cadence=args.cadence,
        trigger=args.trigger,
        due_only=due_only,
        max_sources=args.max_sources,
    )

    results: list[dict[str, Any]] = []
    failed = False
    changed_parents: set[str] = set()
    for it in items:
        pol = policies[it.source_id]
        res = run_source(
            pol,
            reg.get(it.source_id, {}),
            state,
            root=args.root,
            dotenv=dotenv,
            consumed_path=args.consumed,
            dry_run=args.dry_run,
            strict=True,
        )
        results.append(res)
        if not args.dry_run:
            write_state(state, args.root, args.state)
        if res["status"] == ExecutionStatus.SUCCESS_WITH_CHANGE.value:
            changed_parents.add(it.source_id)
        if res["status"] not in SUCCESS_STATUSES and res["status"] not in (
            ExecutionStatus.NOT_DUE.value,
            ExecutionStatus.DISABLED.value,
            ExecutionStatus.MANUAL_INPUT_MISSING.value,
            ExecutionStatus.DEPENDENCY_NOT_READY.value,
            ExecutionStatus.MISSING_SECRET.value,
        ):
            failed = True
            if not args.continue_on_error:
                break

    # trigger newly-due dependents (spec §10) unless suppressed
    if not args.no_dependents and not args.dry_run and changed_parents:
        dep_items = build_plan(
            args.root, policies=policies, state=state, trigger="dependency", due_only=True
        )
        for it in dep_items:
            if it.source_id in {r["source_id"] for r in results}:
                continue
            pol = policies[it.source_id]
            res = run_source(
                pol,
                reg.get(it.source_id, {}),
                state,
                root=args.root,
                dotenv=dotenv,
                consumed_path=args.consumed,
                strict=True,
            )
            results.append(res)
            write_state(state, args.root, args.state)

    _emit(
        {
            "ran": len(results),
            "failed": failed,
            "results": results,
        },
        args.json,
    )
    return 1 if failed else 0


def cmd_resume(args: argparse.Namespace) -> int:
    if not args.source:
        print("resume requires --source", file=sys.stderr)
        return 2
    args.trigger = None
    args.cadence = None
    return cmd_run(args)


def cmd_state(args: argparse.Namespace) -> int:
    from moneysweep.update_controller.state import load_state

    policies = build_effective_policies(args.root, args.policy)
    state = load_state(args.root, args.state, policies=policies)
    if args.json:
        _emit(state, True)
    else:
        rs = state.get("registry_snapshot", {})
        print(
            f"source_count: {rs.get('source_count')}  hash: {rs.get('source_ids_sha256', '')[:16]}"
        )
        statuses: dict[str, int] = {}
        for row in state.get("sources", {}).values():
            statuses[row.get("last_status", "?")] = statuses.get(row.get("last_status", "?"), 0) + 1
        print(f"statuses: {statuses}")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def _common_parser() -> argparse.ArgumentParser:
    """Global flags shared by every subcommand (so they may follow the command)."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=REPO_ROOT)
    common.add_argument("--policy", default=None, help="Path to the policy overlay.")
    common.add_argument("--state", default=None, help="Path to the state file.")
    common.add_argument("--consumed", default=None, help="Path to the consumed-drops manifest.")
    common.add_argument("--dry-run", action="store_true")
    common.add_argument("--json", action="store_true")
    common.add_argument("--strict", action="store_true")
    common.add_argument("--max-sources", type=int, default=None)
    common.add_argument("--continue-on-error", action="store_true")
    common.add_argument("--no-dependents", action="store_true")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(prog="update_sources", description=__doc__, parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-policy", parents=[common]).set_defaults(func=cmd_validate_policy)

    p_plan = sub.add_parser("plan", parents=[common])
    p_plan.add_argument("--due", action="store_true")
    p_plan.add_argument("--cadence", default=None)
    p_plan.add_argument("--source", default=None)
    p_plan.add_argument("--trigger", default=None)
    p_plan.set_defaults(func=cmd_plan)

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--due", action="store_true")
    p_run.add_argument("--cadence", default=None)
    p_run.add_argument("--source", default=None)
    p_run.add_argument("--trigger", default=None)
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("scan-drops", parents=[common]).set_defaults(func=cmd_scan_drops)
    sub.add_parser("ingest-drops", parents=[common]).set_defaults(func=cmd_ingest_drops)
    sub.add_parser("freshness", parents=[common]).set_defaults(func=cmd_freshness)
    sub.add_parser("state", parents=[common]).set_defaults(func=cmd_state)

    p_resume = sub.add_parser("resume", parents=[common])
    p_resume.add_argument("--source", default=None)
    p_resume.set_defaults(func=cmd_resume)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # normalize optional attrs that not every subcommand defines
    for attr in ("due", "cadence", "source", "trigger"):
        if not hasattr(args, attr):
            setattr(args, attr, None if attr != "due" else False)
    args.root = Path(args.root)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
