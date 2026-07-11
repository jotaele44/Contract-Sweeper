"""Coverage-contract control plane: schema sync, validation, and the
min_rows-can-never-mean-complete invariant."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from moneysweep.validation.completeness import (
    CANONICAL_GRAINS,
    CONTRACTS_JSON,
    GEOGRAPHY_SCOPES,
    MATERIALITY_LABELS,
    UNIVERSE_METHODS,
    certification_status,
    compute_status_vector,
    evaluate_coverage,
    evaluate_monetary,
    load_coverage_contracts,
    materiality_label,
    validate_contracts,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Registry hygiene
# ---------------------------------------------------------------------------
def test_yaml_and_json_are_in_sync():
    yaml_data = yaml.safe_load(
        (ROOT / "registries" / "coverage_contracts.yaml").read_text(encoding="utf-8")
    )
    json_data = json.loads((ROOT / CONTRACTS_JSON).read_text(encoding="utf-8"))
    assert yaml_data == json_data, (
        "registries/coverage_contracts.json is stale — run scripts/regenerate_registry_json.py"
    )


def test_committed_contracts_validate_clean():
    assert validate_contracts(ROOT) == []


def test_contracts_load_with_defaults_merged():
    contracts = load_coverage_contracts(ROOT)
    assert len(contracts) >= 20
    for sid, contract in contracts.items():
        assert contract["source_id"] == sid
        # file defaults reach every contract
        assert contract["production_fixtures_forbidden"] is True
        assert isinstance(contract["pagination_required"], bool)


def test_schema_file_vocabularies_match_module():
    schema = json.loads(
        (ROOT / "schemas" / "coverage_contract.schema.json").read_text(encoding="utf-8")
    )
    defs = schema["$defs"]
    assert set(defs["canonical_grain"]["enum"]) == CANONICAL_GRAINS
    assert set(defs["geography_scope"]["enum"]) == GEOGRAPHY_SCOPES
    assert set(defs["authoritative_universe_method"]["enum"]) == UNIVERSE_METHODS


def test_validator_rejects_floor_without_universe_method(tmp_path):
    data = json.loads((ROOT / CONTRACTS_JSON).read_text(encoding="utf-8"))
    entry = {
        "source_id": "fec",
        "contract_version": 1,
        "canonical_grain": "transaction",
        "geography_scope": "PR",
        "uniqueness_key": ["sub_id"],
        "minimum_coverage_pct": 95.0,
    }
    data["contracts"] = [entry]
    _write_fake_root(tmp_path, data)
    errors = validate_contracts(tmp_path)
    assert any("authoritative_universe_method" in e for e in errors)


def test_validator_rejects_unknown_source_and_duplicates(tmp_path):
    data = json.loads((ROOT / CONTRACTS_JSON).read_text(encoding="utf-8"))
    good = dict(data["contracts"][0])
    ghost = dict(good, source_id="no_such_source_zzz")
    data["contracts"] = [good, dict(good), ghost]
    _write_fake_root(tmp_path, data)
    errors = validate_contracts(tmp_path)
    assert any("duplicate contract" in e for e in errors)
    assert any("not in the live source registry" in e for e in errors)


def _write_fake_root(tmp_path: Path, contracts_data: dict) -> None:
    """Minimal root: real source registry + synthetic contracts file."""
    reg_dir = tmp_path / "registries"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / "coverage_contracts.json").write_text(json.dumps(contracts_data), encoding="utf-8")
    real = (ROOT / "registries" / "source_registry.json").read_text(encoding="utf-8")
    (reg_dir / "source_registry.json").write_text(real, encoding="utf-8")


# ---------------------------------------------------------------------------
# The invariant: min_rows/row-count alone can never mean complete
# ---------------------------------------------------------------------------
def test_one_row_uncontracted_source_can_never_be_validated_complete():
    """The old control plane called min_rows:1 'fully materialized'. The new
    labels cap an uncontracted source at seed/partial/substantial forever."""
    status, _ = evaluate_coverage(None, unique_rows=1)
    assert status == "uncontracted"
    for rows in (1, 49, 50, 999, 1000, 10_000_000):
        label = materiality_label(
            rows,
            fixture_detected=False,
            coverage_status="uncontracted",
            freshness_status="fresh",
        )
        assert label != "validated_complete", f"{rows} rows escaped the contract gate"
    assert (
        certification_status(
            materialization_status="fully_materialized",
            coverage_status="uncontracted",
            reconciliation_status="not_applicable",
            freshness_status="fresh",
            fixture_detected=False,
        )
        == "provisional"
    )


def test_fixtures_can_never_certify():
    label = materiality_label(
        500,
        fixture_detected=True,
        coverage_status="meets_contract",
        freshness_status="fresh",
    )
    assert label == "fixture"
    assert (
        certification_status(
            materialization_status="fully_materialized",
            coverage_status="meets_contract",
            reconciliation_status="reconciled",
            freshness_status="fresh",
            fixture_detected=True,
        )
        == "uncertified"
    )


def test_contract_with_unmeasured_universe_is_unverifiable_not_passing():
    contracts = load_coverage_contracts(ROOT)
    ocpr = contracts["ocpr_contracts"]
    assert ocpr["authoritative_universe_total"] is None
    status, reasons = evaluate_coverage(ocpr, unique_rows=1_000_000)
    assert status == "unverifiable"
    assert any("not yet measured" in r for r in reasons)


def test_act_contract_meets_and_below_paths():
    contracts = load_coverage_contracts(ROOT)
    act = contracts["act_transition_contracts"]
    full_fields = {"contractor_name": 100.0, "contract_number": 100.0, "amount": 100.0}

    status, _ = evaluate_coverage(act, unique_rows=656, field_completeness_pct=full_fields)
    assert status == "meets_contract"
    assert (
        materiality_label(
            656,
            fixture_detected=False,
            coverage_status=status,
            freshness_status="fresh",
        )
        == "validated_complete"
    )

    status, reasons = evaluate_coverage(act, unique_rows=100, field_completeness_pct=full_fields)
    assert status == "below_contract"
    assert any("coverage" in r for r in reasons)

    weak_fields = dict(full_fields, amount=10.0)
    status, reasons = evaluate_coverage(act, unique_rows=656, field_completeness_pct=weak_fields)
    assert status == "below_contract"
    assert any("field amount" in r for r in reasons)

    status, _ = evaluate_coverage(act, unique_rows=656, field_completeness_pct=None)
    assert status == "unverifiable"


def test_stale_complete_source_labels_complete_stale():
    assert (
        materiality_label(
            656,
            fixture_detected=False,
            coverage_status="meets_contract",
            freshness_status="stale",
        )
        == "complete_stale"
    )


def test_monetary_reconciliation_paths():
    contract = {
        "monetary_reconciliation": {
            "amount_field": "amount",
            "tolerance_pct": 1.0,
            "reference_total": 1_000_000.0,
        }
    }
    assert evaluate_monetary(None) == "not_applicable"
    assert evaluate_monetary({}, observed_total=5.0) == "not_applicable"
    assert evaluate_monetary(contract, observed_total=None) == "not_evaluated"
    assert evaluate_monetary(contract, observed_total=1_005_000.0) == "reconciled"
    assert evaluate_monetary(contract, observed_total=1_020_000.0) == "variance_exceeds_tolerance"


def test_status_vector_wiring():
    contracts = load_coverage_contracts(ROOT)
    vec = compute_status_vector(
        {"source_id": "act_transition_contracts"},
        path_type="manual_export",
        materialization_status="fully_materialized",
        local_rows=656,
        contract=contracts["act_transition_contracts"],
        field_completeness_pct={
            "contractor_name": 100.0,
            "contract_number": 100.0,
            "amount": 100.0,
        },
        freshness_status="fresh",
    )
    assert vec.wired_status == "manual_dropzone"
    assert vec.acquisition_status == "acquired_ingested"
    assert vec.coverage_status == "meets_contract"
    assert vec.reconciliation_status == "not_evaluated"  # reference_total: null
    assert vec.certification_status == "provisional"  # meets contract, not yet reconciled
    assert vec.materiality_label == "validated_complete"
    assert vec.as_dict()["coverage_reasons"] == ""

    empty_vec = compute_status_vector(
        {"source_id": "cor3"},
        path_type="api_producer",
        materialization_status="not_materialized",
        local_rows=0,
        contract=contracts["cor3"],
    )
    assert empty_vec.wired_status == "wired_producer"
    assert empty_vec.acquisition_status == "automated"
    assert empty_vec.materiality_label == "empty"
    assert empty_vec.certification_status == "uncertified"
    assert empty_vec.materiality_label in MATERIALITY_LABELS
