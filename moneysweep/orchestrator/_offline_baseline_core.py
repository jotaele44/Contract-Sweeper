"""Core invariants and file helpers for the offline baseline profile."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = "moneysweep_offline_baseline_v1"
CLASSIFICATION = "CANON_BASELINE_PROVISIONAL"
PRODUCTION_STATUS = "NON_PRODUCTION_DIAGNOSTIC"
REQUIRED_TOTAL = 14
REQUIRED_CREDIT_CEILING = 10

InputSpec = tuple[str, tuple[str, ...], bool, str]

INPUTS: tuple[InputSpec, ...] = (
    (
        "cor3_official_workbook",
        ("cor3_official_projects_export.xlsx",),
        True,
        "data/raw/COR3/COR3 Transparency Portal_Operator_Export.xlsx",
    ),
    (
        "entity_master",
        ("entity_master.csv", "entity_master(2).csv"),
        True,
        "data/staging/processed/entity_master.csv",
    ),
    (
        "entity_profiles",
        ("pr_entity_profiles.csv",),
        True,
        "data/staging/processed/pr_entity_profiles.csv",
    ),
    (
        "nonprofits",
        ("pr_nonprofits.csv",),
        False,
        "data/staging/processed/pr_nonprofits.csv",
    ),
    (
        "fdic_institutions",
        ("pr_fdic_institutions.csv",),
        False,
        "data/staging/processed/pr_fdic_institutions.csv",
    ),
    (
        "fdic_financials",
        ("pr_fdic_financials.csv",),
        False,
        "data/staging/processed/pr_fdic_financials.csv",
    ),
    (
        "cabilderos_pdf",
        ("Registro_de_cabilderos_Abril_18_2026 2.pdf",),
        False,
        "data/manual/pr_cabilderos/Registro_de_cabilderos_Abril_18_2026.pdf",
    ),
)

KEY_CANDIDATES = (
    "normalized_name",
    "entity_key",
    "canonical_name",
    "recipient_name_normalized",
    "recipient_name",
    "vendor_normalized",
    "vendor_name",
    "entity_name",
    "name",
)

REGISTRATION_RE = re.compile(r"\b20\d{2}Q[1-4]-\d{5}\b")
WAYBACK_RE = re.compile(r"The Wayback Machine - (https://web\.archive\.org/web/(\d{14})/\S+)")
CREDENTIAL_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")



class OfflineBaselineViolation(RuntimeError):
    """Raised when an offline-baseline invariant is violated."""


@dataclass(frozen=True)
class BaselineConfig:
    input_dir: Path
    output_root: Path
    repo_root: Path | None = None
    git_sha: str = "UNKNOWN"
    generated_at: str | None = None
    strict_inputs: bool = False


def _json_bytes(value: Any) -> bytes:
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    return f"{text}\n".encode()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_info(path: Path) -> tuple[int, list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        return sum(1 for _ in reader), header


def _file_info(path: Path, display: str | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": display or path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        info["row_count"], info["schema"] = _csv_info(path)
    elif suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError:
            info["row_count"] = None
            info["profile_status"] = "PYARROW_UNAVAILABLE"
        else:
            metadata = pq.read_metadata(path)
            info["row_count"] = metadata.num_rows
            info["schema"] = [
                metadata.schema.column(index).name for index in range(metadata.num_columns)
            ]
    return info


def discover_inputs(input_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    found: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for logical_name, filenames, required, stage_path in INPUTS:
        selected = next(
            (input_dir / name for name in filenames if (input_dir / name).is_file()),
            None,
        )
        if selected is None:
            missing.append(
                {
                    "logical_name": logical_name,
                    "accepted_filenames": list(filenames),
                    "required_for_run": required,
                    "status": "MISSING",
                }
            )
            continue
        record = _file_info(selected)
        record.update(
            {
                "logical_name": logical_name,
                "required_for_run": required,
                "stage_path": stage_path,
                "source_path": selected.as_posix(),
                "status": "PRESENT_NONEMPTY" if selected.stat().st_size else "PRESENT_EMPTY",
            }
        )
        found.append(record)
    return found, missing


def _credential_names(env: Mapping[str, str]) -> list[str]:
    names = []
    for name in env:
        if any(marker in name.upper() for marker in CREDENTIAL_MARKERS):
            names.append(name)
    return sorted(names)


def sanitized_child_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    result = dict(os.environ if env is None else env)
    for name in _credential_names(result):
        result.pop(name, None)
    proxy_names = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    for name in proxy_names:
        result.pop(name, None)
    result["MONEYSWEEP_OFFLINE_BASELINE"] = "1"
    result["NO_PROXY"] = "*"
    result["no_proxy"] = "*"
    return result


@contextlib.contextmanager
def block_network() -> Iterator[None]:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create = socket.create_connection

    def denied(*_args: Any, **_kwargs: Any) -> Any:
        raise OfflineBaselineViolation("network access is forbidden in offline-baseline mode")

    socket.socket.connect = denied  # type: ignore[method-assign]
    socket.socket.connect_ex = denied  # type: ignore[method-assign]
    socket.create_connection = denied  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]
        socket.create_connection = original_create  # type: ignore[assignment]


