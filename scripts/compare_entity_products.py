"""Deterministically compare two local entity CSV products.

The comparator is offline and streaming. It validates CSV structure, fingerprints
files and ordered schemas, selects the first populated stable-key candidate,
computes canonical row and key overlap, and emits an explicit duplicate status.
Equal row counts are never treated as evidence of duplication.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_LEFT = "data/staging/processed/entity_master.csv"
DEFAULT_RIGHT = "data/staging/processed/pr_entity_profiles.csv"
DEFAULT_OUTPUT = "reports/entity_product_comparison.json"
SCHEMA_VERSION = "entity_product_comparison_v2"

KEY_CANDIDATES = (
    "normalized_name",
    "canonical_name",
    "recipient_name_normalized",
    "recipient_name",
    "vendor_normalized",
    "vendor_name",
    "entity_name",
    "name",
    "entity_id",
    "canonical_entity_id",
)

_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_MAX_VALIDATION_DETAILS = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold().strip()
    text = _NON_WORD_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _canonical_row(row: dict[str, str], columns: Iterable[str]) -> bytes:
    values = [_normalize_text(row.get(column, "")) for column in columns]
    return json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _row_digest(row: dict[str, str], columns: Iterable[str]) -> str:
    return hashlib.sha256(_canonical_row(row, columns)).hexdigest()


def _counter_digest(counter: Counter[str]) -> str:
    digest = hashlib.sha256()
    for value, count in sorted(counter.items()):
        digest.update(f"{value}:{count}\n".encode("ascii"))
    return digest.hexdigest()


def _append_error(errors: list[str], message: str) -> None:
    if len(errors) < _MAX_VALIDATION_DETAILS:
        errors.append(message)


def _key_profile(counter: Counter[str], nonblank_rows: int) -> dict[str, Any]:
    unique = len(counter)
    duplicates = sum(count - 1 for count in counter.values() if count > 1)
    return {
        "nonblank_rows": nonblank_rows,
        "unique_keys": unique,
        "duplicate_key_rows": duplicates,
    }


def _inspect_csv(path: Path) -> dict[str, Any]:
    stat = path.stat()
    validation_errors: list[str] = []
    validation_error_count = 0

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        duplicate_headers = sorted(
            column for column, count in Counter(columns).items() if count > 1
        )
        if not columns:
            validation_error_count += 1
            _append_error(validation_errors, "CSV header is missing")
        if duplicate_headers:
            validation_error_count += len(duplicate_headers)
            _append_error(
                validation_errors,
                "duplicate CSV headers: " + ", ".join(duplicate_headers),
            )

        candidate_columns = [candidate for candidate in KEY_CANDIDATES if candidate in columns]
        candidate_hashes = {candidate: Counter() for candidate in candidate_columns}
        candidate_nonblank_rows = Counter[str]()
        row_hashes: Counter[str] = Counter()
        row_count = 0

        for line_number, raw_row in enumerate(reader, start=2):
            row_count += 1
            extra_values = raw_row.get(None)
            if extra_values:
                validation_error_count += 1
                _append_error(
                    validation_errors,
                    f"line {line_number}: {len(extra_values)} unexpected field(s)",
                )
            missing_columns = [column for column in columns if raw_row.get(column) is None]
            if missing_columns:
                validation_error_count += 1
                _append_error(
                    validation_errors,
                    f"line {line_number}: missing field(s): {', '.join(missing_columns)}",
                )

            row = {column: raw_row.get(column, "") or "" for column in columns}
            row_hashes[_row_digest(row, columns)] += 1
            for candidate in candidate_columns:
                key = _normalize_text(row.get(candidate))
                if key:
                    candidate_nonblank_rows[candidate] += 1
                    candidate_hashes[candidate][
                        hashlib.sha256(key.encode("utf-8")).hexdigest()
                    ] += 1

    selected_key = next(
        (
            candidate
            for candidate in KEY_CANDIDATES
            if candidate_nonblank_rows.get(candidate, 0) > 0
        ),
        None,
    )
    selected_hashes = candidate_hashes.get(selected_key, Counter())
    selected_nonblank_rows = candidate_nonblank_rows.get(selected_key, 0)
    key_profiles = {
        candidate: _key_profile(
            candidate_hashes[candidate], candidate_nonblank_rows.get(candidate, 0)
        )
        for candidate in candidate_columns
    }

    return {
        "path": path.as_posix(),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "file_sha256": _sha256_file(path),
        "schema": columns,
        "schema_sha256": hashlib.sha256(
            json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "duplicate_headers": duplicate_headers,
        "row_count": row_count,
        "stable_key_column": selected_key,
        "stable_key_candidates": key_profiles,
        "nonblank_unique_keys": len(selected_hashes),
        "blank_key_rows": row_count - selected_nonblank_rows if selected_key else row_count,
        "duplicate_key_rows": sum(
            count - 1 for count in selected_hashes.values() if count > 1
        ),
        "row_hash_multiset_sha256": _counter_digest(row_hashes),
        "key_hash_set_sha256": _counter_digest(Counter(selected_hashes.keys())),
        "validation_error_count": validation_error_count,
        "validation_errors": validation_errors,
        "validation_errors_truncated": validation_error_count > len(validation_errors),
        "_row_hashes": row_hashes,
        "_key_hashes": selected_hashes,
    }


def _projection_hashes(path: Path, columns: list[str]) -> Counter[str]:
    hashes: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            row = {column: raw_row.get(column, "") or "" for column in columns}
            hashes[_row_digest(row, columns)] += 1
    return hashes


def _multiset_overlap(left: Counter[str], right: Counter[str]) -> dict[str, Any]:
    left_total = sum(left.values())
    right_total = sum(right.values())
    intersection = sum((left & right).values())
    denominator = max(left_total, right_total)
    return {
        "status": "COMPUTED",
        "left_count": left_total,
        "right_count": right_total,
        "intersection_count": intersection,
        "overlap_rate_max_denominator": round(intersection / denominator, 6)
        if denominator
        else 1.0,
    }


def _set_overlap(left: Counter[str], right: Counter[str]) -> dict[str, Any]:
    left_set = set(left)
    right_set = set(right)
    intersection = left_set & right_set
    union = left_set | right_set
    max_denominator = max(len(left_set), len(right_set))
    return {
        "left_unique": len(left_set),
        "right_unique": len(right_set),
        "intersection_unique": len(intersection),
        "union_unique": len(union),
        "overlap_rate_max_denominator": round(len(intersection) / max_denominator, 6)
        if max_denominator
        else 1.0,
        "jaccard_rate": round(len(intersection) / len(union), 6) if union else 1.0,
    }


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def _base_report(status: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "status": status,
        "freshness_boundary": (
            "Local filesystem metadata only; external-source freshness is not certified."
        ),
    }


def compare(left_path: Path, right_path: Path) -> dict[str, Any]:
    missing = [path.as_posix() for path in (left_path, right_path) if not path.exists()]
    if missing:
        return {**_base_report("INDETERMINATE_MISSING_INPUT"), "missing_inputs": missing}

    left = _inspect_csv(left_path)
    right = _inspect_csv(right_path)
    public_left = _public(left)
    public_right = _public(right)

    if left["validation_error_count"] or right["validation_error_count"]:
        return {
            **_base_report("INDETERMINATE_INVALID_INPUT"),
            "left": public_left,
            "right": public_right,
            "duplicate_status": "INDETERMINATE_INVALID_INPUT",
        }

    if left["row_count"] == 0 or right["row_count"] == 0:
        return {
            **_base_report("INDETERMINATE_EMPTY_PRODUCT"),
            "left": public_left,
            "right": public_right,
            "duplicate_status": "INDETERMINATE_EMPTY_PRODUCT",
        }

    shared_columns = sorted(set(left["schema"]) & set(right["schema"]))
    if shared_columns:
        projected_overlap = _multiset_overlap(
            _projection_hashes(left_path, shared_columns),
            _projection_hashes(right_path, shared_columns),
        )
    else:
        projected_overlap = {
            "status": "NOT_COMPUTABLE_NO_SHARED_COLUMNS",
            "left_count": left["row_count"],
            "right_count": right["row_count"],
            "intersection_count": None,
            "overlap_rate_max_denominator": None,
        }

    key_overlap = _set_overlap(left["_key_hashes"], right["_key_hashes"])
    if left["file_sha256"] == right["file_sha256"]:
        duplicate_status = "IDENTICAL_FILE"
    elif left["schema"] == right["schema"] and left["_row_hashes"] == right["_row_hashes"]:
        duplicate_status = "SEMANTIC_DUPLICATE"
    elif not left["stable_key_column"] or not right["stable_key_column"]:
        duplicate_status = "INDETERMINATE_NO_STABLE_KEY"
    elif key_overlap["overlap_rate_max_denominator"] >= 0.95:
        duplicate_status = "OVERLAPPING_DERIVED_PRODUCTS"
    else:
        duplicate_status = "DISTINCT_DERIVED_PRODUCTS"

    return {
        **_base_report("COMPLETE"),
        "left": public_left,
        "right": public_right,
        "schema_comparison": {
            "identical_ordered_schema": left["schema"] == right["schema"],
            "shared_columns": shared_columns,
            "shared_column_count": len(shared_columns),
            "left_only_columns": sorted(set(left["schema"]) - set(right["schema"])),
            "right_only_columns": sorted(set(right["schema"]) - set(left["schema"])),
        },
        "stable_key_overlap": key_overlap,
        "shared_projection_row_overlap": projected_overlap,
        "duplicate_status": duplicate_status,
        "decision_rules": {
            "IDENTICAL_FILE": "Non-empty valid files have matching byte SHA-256 values.",
            "SEMANTIC_DUPLICATE": "Ordered schemas and canonical row-hash multisets match.",
            "OVERLAPPING_DERIVED_PRODUCTS": "Different products share at least 95% of normalized stable keys.",
            "DISTINCT_DERIVED_PRODUCTS": "Normalized stable-key overlap is below 95%.",
            "INDETERMINATE_NO_STABLE_KEY": "At least one product has no populated recognized stable-key column.",
            "INDETERMINATE_INVALID_INPUT": "At least one CSV is structurally malformed.",
            "INDETERMINATE_EMPTY_PRODUCT": "At least one valid CSV has zero data rows."
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--left", default=DEFAULT_LEFT)
    parser.add_argument("--right", default=DEFAULT_RIGHT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Write a missing-input report and exit zero; invalid or empty inputs still fail.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = compare(root / args.left, root / args.right)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] == "COMPLETE":
        return 0
    if report["status"] == "INDETERMINATE_MISSING_INPUT" and args.allow_missing:
        return 0
    return 2 if report["status"] == "INDETERMINATE_MISSING_INPUT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
