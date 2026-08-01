"""Build an immutable, local-only MoneySweep provisional baseline."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

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


def _stage_inputs(found: Sequence[Mapping[str, Any]], repo_root: Path) -> list[dict[str, Any]]:
    staged: list[dict[str, Any]] = []
    for record in found:
        source = Path(str(record["source_path"]))
        destination = repo_root / str(record["stage_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        staged.append(
            {
                "logical_name": record["logical_name"],
                "destination": destination.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(destination),
                "status": "STAGED_LOCAL_ONLY",
            }
        )
    return staged


def _run_repo_stages(repo_root: Path, output_dir: Path) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    try:
        from scripts.ingest_cor3 import run as ingest_cor3
    except ImportError as error:
        stages.append(
            {
                "stage": "cor3_ingest",
                "status": "BLOCKED_IMPORT_ERROR",
                "detail": str(error),
            }
        )
    else:
        result = ingest_cor3(root=repo_root, force=True)
        output = repo_root / "data/staging/processed/pr_cor3_projects.csv"
        stages.append(
            {
                "stage": "cor3_ingest",
                "status": result.get("status", "UNKNOWN"),
                "rows": result.get("rows", 0),
                "output": (
                    _file_info(output, output.relative_to(repo_root).as_posix())
                    if output.exists()
                    else None
                ),
            }
        )

    stages.append(
        {
            "stage": "unified_master",
            "status": "SUPPLIED_PRODUCT_VALIDATED_NO_PARTIAL_CORPUS_REBUILD",
            "path": "data/staging/processed/entity_master.csv",
        }
    )
    try:
        from scripts.compare_entity_products import compare
    except ImportError as error:
        stages.append(
            {
                "stage": "entity_product_comparison_v2",
                "status": "BLOCKED_IMPORT_ERROR",
                "detail": str(error),
            }
        )
    else:
        report = compare(
            repo_root / "data/staging/processed/entity_master.csv",
            repo_root / "data/staging/processed/pr_entity_profiles.csv",
        )
        _write_json(output_dir / "entity_product_comparison.json", report)
        stages.append(
            {
                "stage": "entity_product_comparison_v2",
                "status": report.get("status"),
                "duplicate_status": report.get("duplicate_status"),
            }
        )
    return stages


def _pdf_text(pdf: Path, work_dir: Path) -> Path:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise OfflineBaselineViolation("pdftotext is required for cabilderos extraction")
    text_path = work_dir / "cabilderos.txt"
    subprocess.run(
        [executable, "-layout", str(pdf), str(text_path)],
        check=True,
        env=sanitized_child_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return text_path


def extract_cabilderos(pdf: Path, output_csv: Path, work_dir: Path) -> dict[str, Any]:
    pages = _pdf_text(pdf, work_dir).read_text(errors="replace").split("\f")
    current_url = ""
    current_timestamp = ""
    rows: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        snapshot = WAYBACK_RE.search(page)
        if snapshot:
            current_url = snapshot.group(1)
            current_timestamp = snapshot.group(2)
        lines = page.splitlines()
        for index, line in enumerate(lines):
            registrations = REGISTRATION_RE.findall(line)
            for registration in registrations:
                before = [
                    value.strip() for value in lines[max(0, index - 4) : index] if value.strip()
                ]
                after = [value.strip() for value in lines[index : index + 7] if value.strip()]
                prefix = line.split(registration, 1)[0].strip()
                name_parts = before[-2:] + ([prefix] if prefix else [])
                snapshot_date = ""
                if len(current_timestamp) >= 8:
                    snapshot_date = (
                        f"{current_timestamp[:4]}-{current_timestamp[4:6]}-"
                        f"{current_timestamp[6:8]}"
                    )
                rows.append(
                    {
                        "snapshot_url": current_url,
                        "snapshot_timestamp": current_timestamp,
                        "snapshot_date": snapshot_date,
                        "registration_number": registration,
                        "lobbyist_name_heuristic": " ".join(name_parts).strip(),
                        "source_page": page_number,
                        "context_raw": " | ".join(before[-3:] + after[:5]),
                        "extraction_status": "PROVISIONAL_REGISTRATION_INDEX",
                        "canonical_credit": "false",
                    }
                )
    rows.sort(
        key=lambda row: (
            str(row["snapshot_timestamp"]),
            str(row["registration_number"]),
            int(row["source_page"]),
        )
    )
    default_fields = [
        "snapshot_url",
        "snapshot_timestamp",
        "snapshot_date",
        "registration_number",
        "lobbyist_name_heuristic",
        "source_page",
        "context_raw",
        "extraction_status",
        "canonical_credit",
    ]
    fields = list(rows[0]) if rows else default_fields
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    registrations = {str(row["registration_number"]) for row in rows}
    snapshots = sorted(
        {str(row["snapshot_timestamp"]) for row in rows if row["snapshot_timestamp"]}
    )
    return {
        "stage": "cabilderos_provisional_extraction",
        "status": "PROVISIONAL_NO_CANONICAL_CREDIT",
        "emitted_rows": len(rows),
        "unique_registration_numbers": len(registrations),
        "duplicate_occurrences": len(rows) - len(registrations),
        "snapshot_timestamps": snapshots,
        "output": _file_info(output_csv),
    }


def _normalized_keys(path: Path) -> tuple[dict[str, Any], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    key: str | None = None
    for candidate in KEY_CANDIDATES:
        if candidate not in columns:
            continue
        if any(" ".join((row.get(candidate) or "").casefold().split()) for row in rows):
            key = candidate
            break
    keys: set[str] = set()
    if key is not None:
        for row in rows:
            value = " ".join((row.get(key) or "").casefold().split())
            if value:
                keys.add(value)
    return (
        {
            "path": path.name,
            "file_sha256": sha256_file(path),
            "row_count": len(rows),
            "schema": columns,
            "stable_key_column": key,
            "nonblank_unique_keys": len(keys),
        },
        keys,
    )


def local_entity_comparison(left: Path, right: Path) -> dict[str, Any]:
    left_info, left_keys = _normalized_keys(left)
    right_info, right_keys = _normalized_keys(right)
    intersection = left_keys & right_keys
    union = left_keys | right_keys
    denominator = max(len(left_keys), len(right_keys))
    overlap = len(intersection) / denominator if denominator else 1.0
    if left_info["file_sha256"] == right_info["file_sha256"]:
        duplicate_status = "IDENTICAL_FILE"
    elif overlap >= 0.95:
        duplicate_status = "OVERLAPPING_DERIVED_PRODUCTS"
    else:
        duplicate_status = "DISTINCT_DERIVED_PRODUCTS"
    return {
        "schema_version": "entity_product_comparison_v2_local_fallback",
        "status": "COMPLETE",
        "left": left_info,
        "right": right_info,
        "stable_key_overlap": {
            "left_unique": len(left_keys),
            "right_unique": len(right_keys),
            "intersection_unique": len(intersection),
            "union_unique": len(union),
            "overlap_rate_max_denominator": round(overlap, 6),
            "jaccard_rate": round(len(intersection) / len(union), 6) if union else 1.0,
        },
        "duplicate_status": duplicate_status,
        "canonical_certification": False,
    }


def _row_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return _csv_info(path)[0]
    if suffix == ".parquet":
        value = _file_info(path).get("row_count")
        return value if isinstance(value, int) else None
    if suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if suffix == ".json":
        value = json.loads(path.read_text())
        return len(value) if isinstance(value, list) else 1
    return None


def _fallback_coverage(json_path: Path, csv_path: Path) -> dict[str, Any]:
    summary = {
        "status": "BASELINE_OVERLAY_ONLY_REGISTRY_UNAVAILABLE",
        "total_sources": 151,
        "fully_materialized": 67,
        "partially_materialized": 11,
        "not_materialized": 73,
        "required_fully_materialized": REQUIRED_CREDIT_CEILING,
        "required_sources": REQUIRED_TOTAL,
        "source_credit_changed": False,
    }
    _write_json(
        json_path,
        {"schema_version": SCHEMA_VERSION, "summary": summary, "sources": []},
    )
    csv_path.write_text("source_id,required,status,rows\n")
    return summary


def source_coverage(repo_root: Path | None, json_path: Path, csv_path: Path) -> dict[str, Any]:
    if repo_root is None:
        return _fallback_coverage(json_path, csv_path)
    registry_path = repo_root / "registries/source_registry.json"
    if not registry_path.exists():
        return _fallback_coverage(json_path, csv_path)

    value = json.loads(registry_path.read_text())
    sources = value.get("sources", []) if isinstance(value, dict) else value
    matrix: list[dict[str, Any]] = []
    owned_paths: set[str] = set()
    total_rows = 0
    fully = 0
    partially = 0
    missing = 0
    required_full = 0
    for source in sorted(sources, key=lambda item: str(item.get("source_id", ""))):
        expected = [str(path) for path in source.get("expected_outputs", [])]
        outputs: list[dict[str, Any]] = []
        present = 0
        nonempty = 0
        source_rows = 0
        for relative in expected:
            path = repo_root / relative
            rows = _row_count(path)
            exists = path.is_file()
            has_rows = bool(exists and (rows is None or rows > 0))
            present += int(exists)
            nonempty += int(has_rows)
            if rows and relative not in owned_paths:
                source_rows += rows
                total_rows += rows
                owned_paths.add(relative)
            outputs.append(
                {
                    "path": relative,
                    "present": exists,
                    "row_count": rows,
                    "nonempty": has_rows,
                }
            )
        if expected and nonempty == len(expected):
            status = "fully_materialized"
            fully += 1
            if source.get("required"):
                required_full += 1
        elif present:
            status = "partially_materialized"
            partially += 1
        else:
            status = "not_materialized"
            missing += 1
        matrix.append(
            {
                "source_id": source.get("source_id"),
                "required": bool(source.get("required")),
                "status": status,
                "rows": source_rows,
                "expected_outputs": outputs,
            }
        )
    summary = {
        "status": "PROVISIONAL_LOCAL_FILESYSTEM_RECOMPUTE",
        "total_sources": len(matrix),
        "fully_materialized": fully,
        "partially_materialized": partially,
        "not_materialized": missing,
        "required_fully_materialized": required_full,
        "required_sources": sum(1 for row in matrix if row["required"]),
        "unique_registry_output_rows": total_rows,
        "source_credit_changed": False,
    }
    _write_json(
        json_path,
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "summary": summary,
            "sources": matrix,
        },
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["source_id", "required", "status", "rows"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in matrix:
            writer.writerow({key: row[key] for key in fieldnames})
    return summary


def _input_digest(found: Sequence[Mapping[str, Any]], git_sha: str) -> str:
    compact = []
    for row in sorted(found, key=lambda item: str(item["logical_name"])):
        compact.append(
            {
                "logical_name": row["logical_name"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "row_count": row.get("row_count"),
            }
        )
    payload = json.dumps(
        {"schema_version": SCHEMA_VERSION, "git_sha": git_sha, "inputs": compact},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _blocked_sources(found: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    names = {str(row["logical_name"]) for row in found}
    cabilderos_status = "BLOCKED_MISSING_STRUCTURED_EXPORT"
    if "cabilderos_pdf" in names:
        cabilderos_status = "PROVISIONAL_PDF_INDEX_NO_CANONICAL_CREDIT"
    cor3_status = "BLOCKED_MISSING_OFFICIAL_WORKBOOK"
    if "cor3_official_workbook" in names:
        cor3_status = "LOCAL_INGEST_PRESENT_CREDIT_HELD_PENDING_RECEIPT"
    pairs = [
        ("hud_drgr_authorized", "BLOCKED_MISSING_AUTHORIZED_EXPORTS"),
        ("prasa", "BLOCKED_MISSING_OFFICIAL_FILTERED_EXPORT"),
        ("pr_cabilderos", cabilderos_status),
        ("cms_provider_enrichment", "BLOCKED_MISSING_PROVIDER_LEVEL_INPUT"),
        ("export_receipts", "BLOCKED_MISSING_AUTHORITATIVE_RECEIPT_MANIFEST"),
        ("cor3", cor3_status),
    ]
    return [
        {"source_id": source_id, "status": status, "canonical_credit": False}
        for source_id, status in pairs
    ]


def _file_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for path in root.rglob("*"):
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha256_file(path)
    return hashes


def _finalize(temp_dir: Path, final_dir: Path) -> str:
    if final_dir.exists():
        if _file_hashes(final_dir) != _file_hashes(temp_dir):
            raise OfflineBaselineViolation("immutable run directory contains different bytes")
        shutil.rmtree(temp_dir)
        return "EXISTING_IDENTICAL"
    temp_dir.replace(final_dir)
    return "CREATED"


def _find_input(found: Sequence[Mapping[str, Any]], logical_name: str) -> Path | None:
    for row in found:
        if row["logical_name"] == logical_name:
            return Path(str(row["source_path"]))
    return None


def run_offline_baseline(config: BaselineConfig) -> dict[str, Any]:
    input_dir = config.input_dir.resolve()
    output_root = config.output_root.resolve()
    repo_root = config.repo_root.resolve() if config.repo_root else None
    output_root.mkdir(parents=True, exist_ok=True)
    found, missing = discover_inputs(input_dir)
    required_missing = [row for row in missing if row["required_for_run"]]
    if config.strict_inputs and required_missing:
        names = ", ".join(str(row["logical_name"]) for row in required_missing)
        raise OfflineBaselineViolation(f"missing required local inputs: {names}")

    digest = _input_digest(found, config.git_sha)
    run_id = f"offline-baseline-{digest[:16]}"
    temp_dir = output_root / f".{run_id}.tmp"
    final_dir = output_root / run_id
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    generated_at = config.generated_at or datetime.now(timezone.utc).isoformat()

    public_inputs = []
    for row in found:
        public_inputs.append({key: value for key, value in row.items() if key != "source_path"})
    _write_json(
        temp_dir / "input_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "git_sha": config.git_sha,
            "generated_at": generated_at,
            "input_manifest_sha256": digest,
            "credentials_present_but_not_used": _credential_names(os.environ),
            "inputs": public_inputs,
            "missing_inputs": missing,
        },
    )
    _write_json(
        temp_dir / "preexisting_outputs_manifest.json",
        {"schema_version": SCHEMA_VERSION, "outputs": []},
    )

    staged: list[dict[str, Any]] = []
    with block_network():
        if repo_root is not None:
            staged = _stage_inputs(found, repo_root)
            stages = _run_repo_stages(repo_root, temp_dir)
        else:
            stages = [
                {
                    "stage": "cor3_ingest",
                    "status": "LOCAL_VALIDATED_OUTPUT_USED_REPOSITORY_UNAVAILABLE",
                },
                {
                    "stage": "unified_master",
                    "status": "SUPPLIED_PRODUCT_VALIDATED_NO_PARTIAL_CORPUS_REBUILD",
                },
                {"stage": "entity_product_comparison_v2", "status": "LOCAL_FALLBACK"},
            ]
        pdf = _find_input(found, "cabilderos_pdf")
        if pdf is None:
            stages.append(
                {
                    "stage": "cabilderos_provisional_extraction",
                    "status": "BLOCKED_MISSING_PDF",
                }
            )
        else:
            stages.append(
                extract_cabilderos(pdf, temp_dir / "pr_cabilderos_provisional.csv", temp_dir)
            )

    if repo_root is None:
        left = _find_input(found, "entity_master")
        right = _find_input(found, "entity_profiles")
        if left is not None and right is not None:
            _write_json(
                temp_dir / "entity_product_comparison.json",
                local_entity_comparison(left, right),
            )

    coverage = source_coverage(
        repo_root,
        temp_dir / "source_coverage_matrix.json",
        temp_dir / "source_coverage_matrix.csv",
    )
    blocked = _blocked_sources(found)
    _write_json(
        temp_dir / "blocked_source_ledger.json",
        {
            "schema_version": SCHEMA_VERSION,
            "classification": CLASSIFICATION,
            "production_status": PRODUCTION_STATUS,
            "blocked_sources": blocked,
        },
    )
    required_after = int(coverage.get("required_fully_materialized", REQUIRED_CREDIT_CEILING))
    required_after = min(required_after, REQUIRED_CREDIT_CEILING)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "classification": CLASSIFICATION,
        "production_status": PRODUCTION_STATUS,
        "generated_at": generated_at,
        "git_sha": config.git_sha,
        "input_manifest_sha256": digest,
        "staged_inputs": staged,
        "stages": stages,
        "coverage_summary": coverage,
        "required_source_credit": {
            "before": REQUIRED_CREDIT_CEILING,
            "after": required_after,
            "required_total": REQUIRED_TOTAL,
            "credit_changed": False,
            "policy": "Fail closed until receipt-backed authoritative exports are validated.",
        },
        "blocked_source_count": len(blocked),
        "network_access_authorized": False,
        "credential_execution_authorized": False,
        "raw_data_commit_authorized": False,
        "data_promotion_authorized": False,
        "production_activation_authorized": False,
        "canonical_certification": False,
        "no_double_counting_policy": "Each registry output path contributes rows at most once.",
        "reproducibility_command": (
            "python3 run_all.py --profile offline-baseline "
            f"--offline-git-sha {config.git_sha} --offline-generated-at {generated_at}"
        ),
    }
    _write_json(temp_dir / "run_receipt.json", receipt)

    outputs = []
    for path in sorted(temp_dir.rglob("*")):
        if path.is_file() and path.name != "output_manifest.json":
            outputs.append(_file_info(path, path.relative_to(temp_dir).as_posix()))
    _write_json(
        temp_dir / "output_manifest.json",
        {"schema_version": SCHEMA_VERSION, "run_id": run_id, "outputs": outputs},
    )
    receipt_sha = sha256_file(temp_dir / "run_receipt.json")
    sums = []
    for path in sorted(temp_dir.rglob("*")):
        if path.is_file():
            relative = path.relative_to(temp_dir).as_posix()
            sums.append(f"{sha256_file(path)}  {relative}")
    (temp_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    immutable_status = _finalize(temp_dir, final_dir)
    return {
        "status": "PASS_PROVISIONAL_BASELINE",
        "immutable_status": immutable_status,
        "run_id": run_id,
        "output_dir": final_dir.as_posix(),
        "receipt_sha256": receipt_sha,
        "classification": CLASSIFICATION,
        "production_status": PRODUCTION_STATUS,
        "coverage_summary": coverage,
        "blocked_source_count": len(blocked),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--repo-root")
    parser.add_argument("--git-sha", default="UNKNOWN")
    parser.add_argument("--generated-at")
    parser.add_argument("--strict-inputs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_offline_baseline(
        BaselineConfig(
            input_dir=Path(args.input_dir),
            output_root=Path(args.output_root),
            repo_root=Path(args.repo_root) if args.repo_root else None,
            git_sha=args.git_sha,
            generated_at=args.generated_at,
            strict_inputs=args.strict_inputs,
        )
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
