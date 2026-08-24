"""Core invariants and file helpers for the offline baseline profile."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import socket
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = "moneysweep_offline_baseline_v1"
CLASSIFICATION = "CANON_BASELINE_PROVISIONAL"
PRODUCTION_STATUS = "NON_PRODUCTION_DIAGNOSTIC"
REQUIRED_TOTAL = 14
REQUIRED_CREDIT_CEILING = 10

LOCAL_CORPUS_SCHEMA_VERSION = "moneysweep_local_corpus_v1"
LOCAL_CORPUS_CLASSIFICATION = "LOCAL_EVIDENCE_CORPUS_PROVISIONAL"
LOCAL_CORPUS_EXTENSIONS = frozenset(
    {".csv", ".json", ".jsonl", ".parquet", ".pdf", ".xlsx", ".xls", ".sqlite", ".db", ".txt"}
)
_LOCAL_EXCLUDED_PARTS = frozenset({".git", ".env", "secrets", "credentials", "__pycache__"})

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

import re

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


@dataclass(frozen=True)
class LocalCorpusConfig:
    """Configuration for a read-only, bounded local evidence inventory.

    ``bindings`` is keyed by exact corpus-relative path.  A binding may carry
    ``source_ids`` (existing registry IDs only), ``semantic_class``, and
    ``evidence_class`` (``financial`` or ``control``).  Bindings classify source
    manifestation; they never assert entity identity.
    """

    input_dir: Path
    output_path: Path | None = None
    bindings: Mapping[str, Mapping[str, Any]] | None = None
    generated_at: str | None = None
    recursive: bool = True
    include_extensions: frozenset[str] = LOCAL_CORPUS_EXTENSIONS


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


def _detected_format(path: Path) -> str:
    """Content-aware format detection; extension is never the sole classifier."""

    with path.open("rb") as handle:
        head = handle.read(16)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PAR1"):
        return "parquet"
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if head.startswith(b"PK\x03\x04"):
        return "zip_container"
    if path.suffix.casefold() in {".json", ".jsonl"}:
        return path.suffix.casefold().lstrip(".")
    if path.suffix.casefold() == ".csv":
        return "csv"
    if path.suffix.casefold() == ".txt":
        return "text"
    return "unknown"


def _zip_member_manifest(path: Path) -> list[dict[str, Any]]:
    """Hash archive payload members by path and uncompressed size.

    This supports archive adjudication without treating outer ZIP hashes as
    payload identity.  Directory members are omitted.
    """

    if _detected_format(path) != "zip_container":
        return []
    members: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                digest = hashlib.sha256(archive.read(info.filename)).hexdigest()
                members.append(
                    {
                        "path": info.filename,
                        "uncompressed_size": info.file_size,
                        "sha256": digest,
                    }
                )
    except (OSError, zipfile.BadZipFile):
        return []
    return members


def certify_record_conservation(
    *,
    source_records: int,
    retained_records: int,
    excluded_records: int,
    unresolved_records: int,
    provenance_complete_records: int,
) -> dict[str, Any]:
    """Fail-closed record conservation gate for a materialized local source."""

    values = (
        source_records,
        retained_records,
        excluded_records,
        unresolved_records,
        provenance_complete_records,
    )
    if any(value < 0 for value in values):
        raise ValueError("record conservation counts must be non-negative")
    arithmetic_closed = source_records == retained_records + excluded_records
    provenance_closed = provenance_complete_records == source_records
    state = (
        "PASS"
        if arithmetic_closed and provenance_closed and unresolved_records == 0
        else "FAIL"
    )
    return {
        "state": state,
        "source_records": source_records,
        "retained_records": retained_records,
        "excluded_records": excluded_records,
        "unresolved_records": unresolved_records,
        "provenance_complete_records": provenance_complete_records,
        "arithmetic_closed": arithmetic_closed,
        "provenance_closed": provenance_closed,
        "queryable": state == "PASS",
    }


def _excluded_local_path(relative_path: Path) -> bool:
    lowered = {part.casefold() for part in relative_path.parts}
    return bool(lowered & _LOCAL_EXCLUDED_PARTS)


def inventory_local_corpus(config: LocalCorpusConfig) -> dict[str, Any]:
    """Freeze and classify a bounded local directory without materializing rows.

    The inventory is read-only.  Symlinks are rejected to prevent an allowlisted
    root from escaping through filesystem indirection.  Absolute operator paths
    are never written to the manifest.  All financial inputs remain non-queryable
    until a source-specific parser supplies a PASS record-conservation receipt.
    """

    root = config.input_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise OfflineBaselineViolation(f"local corpus root is not a directory: {root}")

    bindings = dict(config.bindings or {})
    iterator = root.rglob("*") if config.recursive else root.iterdir()
    files: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for path in sorted(iterator, key=lambda item: item.as_posix()):
        if path.is_symlink():
            excluded.append({"path": path.relative_to(root).as_posix(), "reason": "SYMLINK_REJECTED"})
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if _excluded_local_path(relative):
            excluded.append({"path": relative_text, "reason": "SENSITIVE_OR_INTERNAL_PATH"})
            continue
        extension = path.suffix.casefold()
        if extension not in config.include_extensions:
            excluded.append({"path": relative_text, "reason": "UNSUPPORTED_EXTENSION"})
            continue
        binding = dict(bindings.get(relative_text) or {})
        evidence_class = str(binding.get("evidence_class") or "unresolved")
        detected = _detected_format(path)
        item: dict[str, Any] = {
            "relative_path": relative_text,
            "filename_raw": path.name,
            "extension": extension,
            "detected_format": detected,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "source_ids": list(binding.get("source_ids") or []),
            "semantic_class": str(binding.get("semantic_class") or "UNRESOLVED"),
            "evidence_class": evidence_class,
            "binding_status": "BINDING" if binding else "UNRESOLVED",
            "file_conservation_status": "PASS",
            "record_conservation_status": "NOT_APPLICABLE" if evidence_class == "control" else "OPEN",
            "provenance_status": "FILE_LEVEL_PASS",
            "queryable": False,
        }
        if detected == "zip_container":
            item["archive_members"] = _zip_member_manifest(path)
        files.append(item)

    by_hash: dict[str, list[str]] = {}
    for item in files:
        by_hash.setdefault(str(item["sha256"]), []).append(str(item["relative_path"]))
    duplicate_groups = [
        {"sha256": digest, "paths": sorted(paths), "classification": "BYTE_IDENTICAL"}
        for digest, paths in sorted(by_hash.items())
        if len(paths) > 1
    ]

    financial = [item for item in files if item["evidence_class"] == "financial"]
    control = [item for item in files if item["evidence_class"] == "control"]
    unresolved = [item for item in files if item["evidence_class"] == "unresolved"]
    file_arithmetic_closed = len(files) == len(financial) + len(control) + len(unresolved)
    generated_at = config.generated_at or datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": LOCAL_CORPUS_SCHEMA_VERSION,
        "classification": LOCAL_CORPUS_CLASSIFICATION,
        "generated_at": generated_at,
        "root_disclosure": "REDACTED_OPERATOR_ROOT",
        "recursive": config.recursive,
        "file_count": len(files),
        "financial_file_count": len(financial),
        "control_file_count": len(control),
        "unresolved_file_count": len(unresolved),
        "excluded_path_count": len(excluded),
        "duplicate_byte_group_count": len(duplicate_groups),
        "files": files,
        "excluded_paths": excluded,
        "byte_duplicate_groups": duplicate_groups,
        "certification": {
            "scope": "bounded files discovered under the explicit local root",
            "file_conservation": "PASS" if file_arithmetic_closed else "FAIL",
            "file_arithmetic_closed": file_arithmetic_closed,
            "record_conservation": "OPEN" if financial else "NOT_APPLICABLE",
            "record_provenance": "OPEN" if financial else "NOT_APPLICABLE",
            "identity_certification": "NOT_ATTEMPTED",
            "canonical_certification": False,
            "queryable_evidence": False,
            "promotion_authorized": False,
        },
    }
    if config.output_path is not None:
        _write_json(config.output_path, manifest)
    return manifest
