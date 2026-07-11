"""Typed models, enums and shared constants for the source update controller.

Kept dependency-light (stdlib only) so every other controller module can import
it without pulling in networkx / pandas at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    FILE_DROP = "file_drop"
    DEPENDENCY = "dependency"
    ON_DROP = "on_drop"
    MANUAL = "manual"
    DISABLED = "disabled"


class ExecutionBackend(str, Enum):
    GITHUB_ACTIONS = "github_actions"
    SELF_HOSTED = "self_hosted"
    LOCAL = "local"
    EXTERNAL = "external"


class EmptyResultPolicy(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    FAIL = "fail"
    PRESERVE_PREVIOUS = "preserve_previous"


class OutputChangePolicy(str, Enum):
    ALWAYS = "always"
    CONTENT_HASH = "content_hash"
    ROW_COUNT_OR_HASH = "row_count_or_hash"
    UPSTREAM_CHANGE = "upstream_change"


# --- Execution statuses (spec §9) ---
class ExecutionStatus(str, Enum):
    NEVER_RUN = "NEVER_RUN"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    SUCCESS_WITH_CHANGE = "SUCCESS_WITH_CHANGE"
    SUCCESS_NO_CHANGE = "SUCCESS_NO_CHANGE"
    EMPTY_EXPECTED = "EMPTY_EXPECTED"
    EMPTY_SUSPICIOUS = "EMPTY_SUSPICIOUS"
    MISSING_SECRET = "MISSING_SECRET"
    MANUAL_INPUT_MISSING = "MANUAL_INPUT_MISSING"
    DEPENDENCY_NOT_READY = "DEPENDENCY_NOT_READY"
    NOT_DUE = "NOT_DUE"
    DISABLED = "DISABLED"
    RATE_LIMITED = "RATE_LIMITED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PRODUCER_IMPORT_FAILED = "PRODUCER_IMPORT_FAILED"
    PRODUCER_EXECUTION_FAILED = "PRODUCER_EXECUTION_FAILED"
    OUTPUT_MISSING = "OUTPUT_MISSING"
    OUTPUT_REGRESSION = "OUTPUT_REGRESSION"
    SCHEMA_FAILED = "SCHEMA_FAILED"
    FRESHNESS_FAILED = "FRESHNESS_FAILED"
    CHECKPOINTED = "CHECKPOINTED"


# Statuses that count as a successful (non-error) execution outcome (spec §9).
SUCCESS_STATUSES: frozenset[str] = frozenset(
    {
        ExecutionStatus.SUCCESS_WITH_CHANGE.value,
        ExecutionStatus.SUCCESS_NO_CHANGE.value,
        ExecutionStatus.EMPTY_EXPECTED.value,
        ExecutionStatus.CHECKPOINTED.value,
    }
)

# Statuses that may be retried by the executor (transient, environmental).
RETRYABLE_STATUSES: frozenset[str] = frozenset(
    {
        ExecutionStatus.RATE_LIMITED.value,
        ExecutionStatus.SOURCE_UNAVAILABLE.value,
    }
)


# --- Freshness statuses (spec §12) ---
class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    DUE = "DUE"
    STALE = "STALE"
    NEVER_MATERIALIZED = "NEVER_MATERIALIZED"
    BLOCKED_MISSING_SECRET = "BLOCKED_MISSING_SECRET"
    BLOCKED_MANUAL_INPUT = "BLOCKED_MANUAL_INPUT"
    DISABLED = "DISABLED"
    TERMINAL = "TERMINAL"
    UNKNOWN = "UNKNOWN"


# Cadence → default freshness SLA in hours (spec §12). ad_hoc has no time-based
# SLA (None). on_drop measures 168h from unconsumed-file arrival, handled in the
# planner/validation freshness logic.
CADENCE_SLA_HOURS: dict[str, float | None] = {
    "weekly": 192.0,
    "monthly": 840.0,
    "quarterly": 2400.0,
    "yearly": 9000.0,
    "ad_hoc": None,
    "on_drop": 168.0,
}

# Cadence → nominal interval in hours, used to compute next_due_at from the last
# successful materialization.
CADENCE_INTERVAL_HOURS: dict[str, float | None] = {
    "weekly": 168.0,
    "monthly": 720.0,
    "quarterly": 2160.0,
    "yearly": 8760.0,
    "ad_hoc": None,
    "on_drop": None,
}

# Cadence → UTC cron used by the scheduled GitHub Actions workflows (spec §15).
# GitHub schedules are UTC; Puerto Rico is UTC-4 year-round (no DST).
CADENCE_CRON: dict[str, str] = {
    "weekly": "17 10 * * 1",
    "monthly": "23 10 1 * *",
    "quarterly": "31 10 1 1,4,7,10 *",
    "yearly": "41 10 15 1 *",
}

SCHEDULE_CADENCES: tuple[str, ...] = ("weekly", "monthly", "quarterly", "yearly")

# The only secrets the controller / CI passes through (spec §15). Any other
# api_key requirement resolves to MISSING_SECRET rather than being injected.
KNOWN_SECRETS: tuple[str, ...] = (
    "CENSUS_API_KEY",
    "EIA_API_KEY",
    "FAC_API_KEY",
    "FEC_API_KEY",
    "FINANCIALDATA_API_KEY",
    "FINANCIALDATA_LICENSE_APPROVED",
    "FRED_API_KEY",
    "HIGHERGOV_API_KEY",
    "OPENSTATES_API_KEY",
    "SAM_API_KEY",
)

# Suspected-area vocabulary for failure packets (spec §14).
SUSPECTED_AREAS: frozenset[str] = frozenset(
    {
        "policy",
        "registry",
        "preflight",
        "missing_secret",
        "dependency",
        "dropzone",
        "producer_import",
        "producer_execution",
        "timeout",
        "rate_limit",
        "network",
        "output_missing",
        "output_regression",
        "schema",
        "freshness",
        "checkpoint",
        "state_write",
        "unknown",
    }
)


@dataclass
class SourceUpdatePolicy:
    """A fully-resolved effective policy for one canonical source."""

    source_id: str
    trigger_type: str
    enabled: bool
    runner: str
    freshness_sla_hours: float
    timeout_minutes: int
    max_retries: int
    empty_result_policy: str
    output_change_policy: str = "row_count_or_hash"
    execution_backend: str = "github_actions"
    atomic_output_required: bool = True
    freshness_grace_hours: float = 24.0
    row_regression_tolerance_pct: float = 40.0
    cadence: str | None = None
    cron: str | None = None
    runner_args: list[str] = field(default_factory=list)
    required_secrets: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    watch_paths: list[str] = field(default_factory=list)
    filename_patterns: list[str] = field(default_factory=list)
    dedupe_method: str | None = None
    checkpoint_strategy: str | None = None
    max_pages_per_run: int | None = None
    trigger_dependents_on: str | None = None
    minimum_output_rows: int | None = None
    notes: str = ""
    # Provenance / classification carried from the registry + readiness matrix.
    path_type: str = ""
    required: bool = False
    terminal: bool = False
    source_of_policy: str = "inferred"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source_id": self.source_id,
            "trigger_type": self.trigger_type,
            "enabled": self.enabled,
            "runner": self.runner,
            "freshness_sla_hours": self.freshness_sla_hours,
            "timeout_minutes": self.timeout_minutes,
            "max_retries": self.max_retries,
            "empty_result_policy": self.empty_result_policy,
            "output_change_policy": self.output_change_policy,
            "execution_backend": self.execution_backend,
            "atomic_output_required": self.atomic_output_required,
            "freshness_grace_hours": self.freshness_grace_hours,
            "row_regression_tolerance_pct": self.row_regression_tolerance_pct,
            "cadence": self.cadence,
            "cron": self.cron,
            "runner_args": list(self.runner_args),
            "required_secrets": list(self.required_secrets),
            "depends_on": list(self.depends_on),
            "watch_paths": list(self.watch_paths),
            "filename_patterns": list(self.filename_patterns),
            "dedupe_method": self.dedupe_method,
            "checkpoint_strategy": self.checkpoint_strategy,
            "max_pages_per_run": self.max_pages_per_run,
            "trigger_dependents_on": self.trigger_dependents_on,
            "minimum_output_rows": self.minimum_output_rows,
            "path_type": self.path_type,
            "required": self.required,
            "terminal": self.terminal,
            "notes": self.notes,
        }
        return d


@dataclass
class OutputSnapshot:
    """Pre/post-run snapshot of a single declared output file (spec §13)."""

    path: str
    exists: bool
    size_bytes: int = 0
    sha256: str | None = None
    row_count: int | None = None
    mtime: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "mtime": self.mtime,
        }


@dataclass
class FreshnessResult:
    source_id: str
    trigger_type: str
    enabled: bool
    required: bool
    path_type: str
    update_cadence: str
    freshness_sla_hours: float
    last_success_at: str | None
    last_materialized_at: str | None
    age_hours: float | None
    freshness_status: str
    next_due_at: str | None
    consecutive_failures: int
    last_status: str

    def to_row(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "trigger_type": self.trigger_type,
            "enabled": self.enabled,
            "required": self.required,
            "path_type": self.path_type,
            "update_cadence": self.update_cadence,
            "freshness_sla_hours": self.freshness_sla_hours,
            "last_success_at": self.last_success_at or "",
            "last_materialized_at": self.last_materialized_at or "",
            "age_hours": "" if self.age_hours is None else round(self.age_hours, 2),
            "freshness_status": self.freshness_status,
            "next_due_at": self.next_due_at or "",
            "consecutive_failures": self.consecutive_failures,
            "last_status": self.last_status,
        }


@dataclass
class UpdatePlanItem:
    source_id: str
    trigger_type: str
    due: bool
    reason: str
    enabled: bool
    order_index: int = 0
    depends_on: list[str] = field(default_factory=list)
    required_secrets: list[str] = field(default_factory=list)
    missing_secrets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "trigger_type": self.trigger_type,
            "due": self.due,
            "reason": self.reason,
            "enabled": self.enabled,
            "order_index": self.order_index,
            "depends_on": list(self.depends_on),
            "required_secrets": list(self.required_secrets),
            "missing_secrets": list(self.missing_secrets),
        }


@dataclass
class FailurePacket:
    """Structured failure record (spec §14). Never carries secret values."""

    command: list[str]
    exit_code: int | None
    source_id: str
    run_id: str
    status: str
    suspected_area: str
    retryable: bool
    last_40_lines: list[str] = field(default_factory=list)
    files_recently_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "last_40_lines": list(self.last_40_lines),
            "files_recently_changed": list(self.files_recently_changed),
            "suspected_area": self.suspected_area,
            "source_id": self.source_id,
            "run_id": self.run_id,
            "status": self.status,
            "retryable": self.retryable,
        }


@dataclass
class UpdateRunRecord:
    """Append-only run-ledger record (spec §8)."""

    run_id: str
    source_id: str
    trigger: str
    started_at: str
    finished_at: str
    status: str
    exit_code: int | None
    attempt: int
    command: list[str] = field(default_factory=list)
    input_hashes: dict[str, str] = field(default_factory=dict)
    output_hashes_before: dict[str, str | None] = field(default_factory=dict)
    output_hashes_after: dict[str, str | None] = field(default_factory=dict)
    row_counts_before: dict[str, int | None] = field(default_factory=dict)
    row_counts_after: dict[str, int | None] = field(default_factory=dict)
    duration_seconds: float = 0.0
    failure_packet: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "source_update_run_v1",
            "run_id": self.run_id,
            "source_id": self.source_id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "exit_code": self.exit_code,
            "attempt": self.attempt,
            "command": list(self.command),
            "input_hashes": dict(self.input_hashes),
            "output_hashes_before": dict(self.output_hashes_before),
            "output_hashes_after": dict(self.output_hashes_after),
            "row_counts_before": dict(self.row_counts_before),
            "row_counts_after": dict(self.row_counts_after),
            "duration_seconds": self.duration_seconds,
            "failure_packet": self.failure_packet,
        }


def new_source_state(source_id: str, trigger_type: str, enabled: bool) -> dict[str, Any]:
    """Return a fresh per-source state block (spec §8)."""
    return {
        "source_id": source_id,
        "trigger_type": trigger_type,
        "enabled": enabled,
        "last_attempt_at": None,
        "last_success_at": None,
        "last_materialized_at": None,
        "last_output_change_at": None,
        "last_status": ExecutionStatus.NEVER_RUN.value,
        "last_exit_code": None,
        "next_due_at": None,
        "consecutive_failures": 0,
        "input_manifest_hash": None,
        "output_manifest_hash": None,
        "output_hashes": {},
        "output_row_counts": {},
        "dependency_versions_consumed": {},
        "checkpoint": None,
        "freshness_status": FreshnessStatus.UNKNOWN.value,
        "last_run_id": None,
    }
