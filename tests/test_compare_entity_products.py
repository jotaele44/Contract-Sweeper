from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.compare_entity_products import compare, main

pytestmark = pytest.mark.unit


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_different_products_with_same_entities_are_overlapping(tmp_path: Path) -> None:
    left = tmp_path / "entity_master.csv"
    right = tmp_path / "pr_entity_profiles.csv"
    _write_csv(
        left,
        ["entity_id", "canonical_name", "entity_type"],
        [
            {
                "entity_id": "ENT_ORG_1",
                "canonical_name": "Acme, LLC",
                "entity_type": "organization",
            },
            {
                "entity_id": "ENT_ORG_2",
                "canonical_name": "Beta Corp",
                "entity_type": "organization",
            },
        ],
    )
    _write_csv(
        right,
        ["normalized_name", "recipient_name", "award_count"],
        [
            {"normalized_name": "acme llc", "recipient_name": "ACME LLC", "award_count": "4"},
            {"normalized_name": "beta corp", "recipient_name": "Beta Corp.", "award_count": "2"},
        ],
    )
    report = compare(left, right)
    assert report["status"] == "COMPLETE"
    assert report["duplicate_status"] == "OVERLAPPING_DERIVED_PRODUCTS"
    assert report["schema_comparison"]["identical_ordered_schema"] is False
    assert report["stable_key_overlap"]["overlap_rate_max_denominator"] == 1.0


def test_same_schema_and_rows_in_different_order_are_semantic_duplicate(tmp_path: Path) -> None:
    columns = ["normalized_name", "award_count"]
    rows = [
        {"normalized_name": "Acme", "award_count": "4"},
        {"normalized_name": "Beta", "award_count": "2"},
    ]
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    _write_csv(left, columns, rows)
    _write_csv(right, columns, list(reversed(rows)))
    report = compare(left, right)
    assert report["duplicate_status"] == "SEMANTIC_DUPLICATE"
    assert report["left"]["row_hash_multiset_sha256"] == report["right"]["row_hash_multiset_sha256"]


def test_blank_preferred_key_falls_back_to_populated_name(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    _write_csv(
        left,
        ["normalized_name", "canonical_name"],
        [{"normalized_name": "", "canonical_name": "Acme LLC"}],
    )
    _write_csv(right, ["recipient_name"], [{"recipient_name": "Acme LLC"}])
    report = compare(left, right)
    assert report["left"]["stable_key_column"] == "canonical_name"
    assert report["duplicate_status"] == "OVERLAPPING_DERIVED_PRODUCTS"


def test_no_shared_columns_reports_projection_not_computable(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    _write_csv(left, ["canonical_name"], [{"canonical_name": "Acme"}])
    _write_csv(right, ["recipient_name"], [{"recipient_name": "Acme"}])
    projection = compare(left, right)["shared_projection_row_overlap"]
    assert projection["status"] == "NOT_COMPUTABLE_NO_SHARED_COLUMNS"
    assert projection["overlap_rate_max_denominator"] is None


def test_duplicate_headers_are_invalid(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    left.write_text("name,name\nAcme,Alias\n", encoding="utf-8")
    _write_csv(right, ["name"], [{"name": "Acme"}])
    report = compare(left, right)
    assert report["status"] == "INDETERMINATE_INVALID_INPUT"
    assert report["duplicate_status"] == "INDETERMINATE_INVALID_INPUT"
    assert report["left"]["duplicate_headers"] == ["name"]


def test_extra_fields_are_invalid(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    left.write_text("name\nAcme,Unexpected\n", encoding="utf-8")
    _write_csv(right, ["name"], [{"name": "Acme"}])
    report = compare(left, right)
    assert report["status"] == "INDETERMINATE_INVALID_INPUT"
    assert report["left"]["validation_error_count"] == 1


def test_empty_product_is_indeterminate(tmp_path: Path) -> None:
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    _write_csv(left, ["name"], [])
    _write_csv(right, ["name"], [{"name": "Acme"}])
    report = compare(left, right)
    assert report["status"] == "INDETERMINATE_EMPTY_PRODUCT"
    assert report["duplicate_status"] == "INDETERMINATE_EMPTY_PRODUCT"


def test_missing_input_is_indeterminate(tmp_path: Path) -> None:
    report = compare(tmp_path / "missing-left.csv", tmp_path / "missing-right.csv")
    assert report["status"] == "INDETERMINATE_MISSING_INPUT"
    assert len(report["missing_inputs"]) == 2


def test_cli_allow_missing_writes_report_and_exits_zero(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = main(
        [
            "--root",
            str(tmp_path),
            "--left",
            "left.csv",
            "--right",
            "right.csv",
            "--output",
            output.name,
            "--allow-missing",
        ]
    )
    assert result == 0
    assert output.exists()


def test_cli_invalid_input_exits_nonzero_even_with_allow_missing(tmp_path: Path) -> None:
    _write_csv(tmp_path / "left.csv", ["name"], [])
    _write_csv(tmp_path / "right.csv", ["name"], [{"name": "Acme"}])
    result = main(
        [
            "--root",
            str(tmp_path),
            "--left",
            "left.csv",
            "--right",
            "right.csv",
            "--output",
            "report.json",
            "--allow-missing",
        ]
    )
    assert result == 3
