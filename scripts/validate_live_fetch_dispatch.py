#!/usr/bin/env python3
"""Validate operator-controlled source workflow dispatch inputs.

This module is intentionally stdlib-only. Preflight mode never authorizes a
producer fetch; live execution requires explicit, case-sensitive tokens.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]*$")
WORKFLOWS = {
    "materialize-sources": {"secondary": False, "days": False},
    "highergov-fetch": {"secondary": True, "days": False},
    "sam-opportunities-fetch": {"secondary": True, "days": True},
}


class DispatchValidationError(ValueError):
    """Raised when a dispatch violates the source-workflow safety contract."""


@dataclass(frozen=True)
class DispatchDecision:
    workflow: str
    mode: str
    execute_live_fetch: bool
    source: str = ""
    family: str = ""
    days: int | None = None


def _bounded_token(name: str, value: str) -> str:
    value = value.strip()
    if not _TOKEN_RE.fullmatch(value):
        raise DispatchValidationError(
            f"{name} may contain only letters, digits, underscore, dot, and hyphen"
        )
    return value


def validate_dispatch(
    *,
    workflow: str,
    mode: str,
    confirm: str,
    confirm_secondary: str = "",
    source: str = "",
    family: str = "",
    days: str | int | None = None,
) -> DispatchDecision:
    if workflow not in WORKFLOWS:
        raise DispatchValidationError(f"unsupported workflow: {workflow}")

    mode = mode.strip()
    if mode not in {"preflight", "fetch"}:
        raise DispatchValidationError("mode must be 'preflight' or 'fetch'")

    source = _bounded_token("source", source)
    family = _bounded_token("family", family)

    parsed_days: int | None = None
    if WORKFLOWS[workflow]["days"]:
        raw_days = "365" if days in (None, "") else str(days).strip()
        if not raw_days.isascii() or not raw_days.isdigit() or len(raw_days) > 4:
            raise DispatchValidationError("days must be 1-4 ASCII digits")
        parsed_days = int(raw_days, 10)
        if not 1 <= parsed_days <= 3650:
            raise DispatchValidationError("days must be between 1 and 3650")
    elif days not in (None, ""):
        raise DispatchValidationError(f"{workflow} does not accept days")

    if mode == "fetch":
        if confirm != "YES":
            raise DispatchValidationError("live fetch requires confirm=YES exactly")
        if WORKFLOWS[workflow]["secondary"] and confirm_secondary != "FETCH":
            raise DispatchValidationError("live fetch requires confirm_secondary=FETCH exactly")

    return DispatchDecision(
        workflow=workflow,
        mode=mode,
        execute_live_fetch=mode == "fetch",
        source=source,
        family=family,
        days=parsed_days,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, choices=sorted(WORKFLOWS))
    parser.add_argument("--mode", required=True, choices=("preflight", "fetch"))
    parser.add_argument("--confirm", default="")
    parser.add_argument("--confirm-secondary", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--family", default="")
    parser.add_argument("--days")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        decision = validate_dispatch(
            workflow=args.workflow,
            mode=args.mode,
            confirm=args.confirm,
            confirm_secondary=args.confirm_secondary,
            source=args.source,
            family=args.family,
            days=args.days,
        )
    except DispatchValidationError as exc:
        print(f"dispatch validation failed: {exc}")
        return 2

    print(json.dumps(asdict(decision), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
