"""Compare two entity CSV products without loading either file into memory.

The comparison is deliberately offline and deterministic. It reports file and
schema fingerprints, selects a stable key independently for each product,
computes normalized-key overlap, hashes canonical rows, and assigns a duplicate
status without treating equal row counts as evidence of duplication.

Default inputs are the two Wave 0 derived products found in the operator corpus::

    data/staging/processed/entity_master.csv
    data/staging/processed/pr_entity_profiles.csv

The report is written to ``reports/entity_product_comparison.json``.
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

# Prefer names across independently derived products. Opaque IDs are useful only
# when neither product exposes a canonical or normalized entity name.
KEY_CANDIDATES = (
    "normalized_name",
    "canonical_name",
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


def _choose_key(columns: list[str]) -> str | None:
    column_set = set(columns)
    return next((candidate for candidate in KEY_CANDIDATES if candidate in column_set), None)


def _counter_digest(counter: Counter[str]) -> str:
    digest = hashlib.sha256()
    for value, count in sorted(counter.items()):
        digest.update(f"{value}:{count}\n".encode("ascii"))
    return digest.hexdigest()


def _inspect_csv(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        key_column = _choose_key(columns)
        row_hashes: Counter[str] = Counter()
        key_hashes: Counter[str] = Counter()
        row_count = 0
        blank_key_rows = 0

        for raw_row in reader:
            row = {column: raw_row.get(column, "") or "" for column in columns}
            row_count += 1
            row_hashes[_row_digest(row, columns)] += 1
            if key_column:
                key = _normalize_text(row.get(key_column))
                if key:
                    key_hashes[hashlib.sha256(key.encode("utf-8")).hexdigest()] += 1
                else:
                    blank_key_rows += 1

    return {
        "path": path.as_posix(),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "file_sha256": _sha256_file(path),
        "schema": columns,
        "schema_sha256": hashlib.sha256(
            json.dumps(columns, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "row_count": row_count,
        "stable_key_column": key_column,
        "nonblank_unique_keys": len(key_hashes),
        "blank_key_rows": blank_key_rows,
        "duplicate_key_rows": sum(count - 1 for count in key_hashes.values() if count > 1),
        "row_hash_multiset_sha256": _counter_digest(row_hashes),
        "key_hash_set_sha256": _counter_digest(Counter(key_hashes.keys())),
        "_row_hashes": row_hashes,
        "_key_hashes": key_hashes,
    }


def _projection_hashes(path: Path, columns: list[str]) -> Counter[str]:
    hashes: Counter[str] = Counter()
    if not columns:
        return hashes
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


def _duplicate_status(
    left: dict[str, Any],
    right: dict[str, Any],
    key_overlap: dict[str, Any],
) -> str:
    if left["file_sha256"] == right["file_sha256"]:
        return "IDENTICAL_FILE"
    if left["schema"] == right["schema"] and left["_row_hashes"] == right["_row_hashes"]:
        return "SEMANTIC_DUPLICATE"
    if not left["stable_key_column"] or not right["stable_key_column"]:
        return "INDETERMINATE_NO_STABLE_KEY"
    if not left["_key_hashes"] or not right["_key_hashes"]:
        return "INDETERMINATE_NO_NONBLANK_KEYS"
    if key_overlap["overlap_rate_max_denominator"] >= 0.95:
        return "OVERLAPPING_DERIVED_PRODUCTS"
    return "DISTINCT_DERIVED_PRODUCTS"


def compare(left_path: Path, right_path: Path) -> dict[str, Any]:
    missing = [path.as_posix() for path in (left_path, right_path) if not path.exists()]
    if missing:
        return {
            "schema_version": "entity_product_comparison_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "INDETERMINATE_MISSING_INPUT",
            "missing_inputs": missing,
            "freshness_boundary": (
                "Local filesystem metadata only; external-source freshness not certified."
            ),
        }

    left = _inspect_csv(left_path)
    right = _inspect_csv(right_path)
    shared_columns = sorted(set(left["schema"]) & set(right["schema"]))
    left_projection = _projection_hashes(left_path, shared_columns)
    right_projection = _projection_hashes(right_path, shared_columns)
    key_overlap = _set_overlap(left["_key_hashes"], right["_key_hashes"])
    projected_overlap = _multiset_overlap(left_projection, right_projection)
    duplicate_status = _duplicate_status(left, right, key_overlap)

    for record in (left, right):
        record.pop("_row_hashes")
        record.pop("_key_hashes")

    return {
        "schema_version": "entity_product_comparison_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "left": left,
        "right": right,
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
            "IDENTICAL_FILE": "Byte SHA-256 values match.",
            "SEMANTIC_DUPLICATE": "Ordered schemas and canonical row-hash multisets match.",
            "OVERLAPPING_DERIVED_PRODUCTS": (
                "Different products share at least 95% of normalized stable keys."
            ),
            "DISTINCT_DERIVED_PRODUCTS": "Normalized stable-key overlap is below 95%.",
            "INDETERMINATE_NO_STABLE_KEY": (
                "At least one product has no recognized stable-key column."
            ),
            "INDETERMINATE_NO_NONBLANK_KEYS": (
                "At least one recognized key column contains no nonblank values."
            ),
        },
        "freshness_boundary": (
            "Local filesystem metadata only; external-source freshness not certified."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare MoneySweep entity CSV products.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--left", default=DEFAULT_LEFT)
    parser.add_argument("--right", default=DEFAULT_RIGHT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Write an indeterminate report and exit zero when inputs are absent.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = compare(root / args.left, root / args.right)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] == "INDETERMINATE_MISSING_INPUT" and not args.allow_missing:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
