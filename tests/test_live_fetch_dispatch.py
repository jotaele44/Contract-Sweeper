from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_live_fetch_dispatch.py"
SPEC = importlib.util.spec_from_file_location("validate_live_fetch_dispatch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

DispatchValidationError = MODULE.DispatchValidationError
validate_dispatch = MODULE.validate_dispatch


def test_preflight_never_executes_live_fetch() -> None:
    decision = validate_dispatch(
        workflow="materialize-sources",
        mode="preflight",
        confirm="no",
        source="fec",
        family="federal",
    )
    assert decision.execute_live_fetch is False


@pytest.mark.parametrize(
    ("workflow", "secondary"),
    [
        ("highergov-fetch", "FETCH"),
        ("sam-opportunities-fetch", "FETCH"),
    ],
)
def test_fetch_requires_both_confirmation_tokens(
    workflow: str, secondary: str
) -> None:
    decision = validate_dispatch(
        workflow=workflow,
        mode="fetch",
        confirm="YES",
        confirm_secondary=secondary,
        days="365" if workflow == "sam-opportunities-fetch" else None,
    )
    assert decision.execute_live_fetch is True


@pytest.mark.parametrize(
    ("confirm", "secondary"),
    [
        ("yes", "FETCH"),
        ("YES", "fetch"),
        ("", ""),
    ],
)
def test_fetch_rejects_non_exact_confirmation_tokens(
    confirm: str, secondary: str
) -> None:
    with pytest.raises(DispatchValidationError):
        validate_dispatch(
            workflow="sam-opportunities-fetch",
            mode="fetch",
            confirm=confirm,
            confirm_secondary=secondary,
            days="365",
        )


@pytest.mark.parametrize("days", ["0", "1096", "abc"])
def test_sam_days_are_bounded(days: str) -> None:
    with pytest.raises(DispatchValidationError):
        validate_dispatch(
            workflow="sam-opportunities-fetch",
            mode="preflight",
            confirm="",
            days=days,
        )


@pytest.mark.parametrize("value", ["fec;echo BAD", "$(id)", "family/name", "space value"])
def test_source_and_family_reject_shell_metacharacters(value: str) -> None:
    with pytest.raises(DispatchValidationError):
        validate_dispatch(
            workflow="materialize-sources",
            mode="preflight",
            confirm="",
            source=value,
        )
