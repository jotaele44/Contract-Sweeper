from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def _load(name: str) -> dict[str, object]:
    with (SCHEMAS / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_investor_schema_separates_identity_levels() -> None:
    schema = _load("capital_control_investor.schema.json")
    properties = schema["properties"]
    assert isinstance(properties, dict)

    for field in (
        "raw_name",
        "normalized_name",
        "canonical_name",
        "legal_entity_id",
        "investor_family_id",
        "ultimate_parent_id",
        "identity_level",
        "identity_status",
        "binding_basis",
    ):
        assert field in properties

    level_enum = properties["identity_level"]["enum"]
    assert "LEGAL_ENTITY" in level_enum
    assert "FUND_OR_VEHICLE" in level_enum
    assert "INVESTOR_FAMILY" in level_enum
    assert "ULTIMATE_PARENT" in level_enum

    basis_enum = properties["binding_basis"]["enum"]
    assert "HEURISTIC_DISCOVERY_ONLY" in basis_enum
    assert "NONE" in basis_enum


def test_holding_schema_is_temporal_and_source_bound() -> None:
    schema = _load("capital_control_holding_observation.schema.json")
    required = set(schema["required"])
    assert {
        "observation_id",
        "holder_id",
        "issuer_id",
        "position_class",
        "as_of_date",
        "report_date",
        "source_id",
        "source_record_id",
        "identity_status",
    } <= required

    properties = schema["properties"]
    assert isinstance(properties, dict)
    position_classes = set(properties["position_class"]["enum"])
    assert {
        "BENEFICIAL_OWNERSHIP",
        "INVESTMENT_DISCRETION",
        "VOTING_AUTHORITY",
        "FUND_HOLDING",
        "CUSTODY",
        "PARENT_CONTROL",
        "DEBT",
        "BONDHOLDING",
        "LIEN",
        "COLLATERAL",
    } <= position_classes

    assert "anyOf" in schema
    security_alternatives = schema["anyOf"]
    assert {tuple(item["required"]) for item in security_alternatives} == {
        ("security_id",),
        ("security_class_raw",),
    }


def test_source_manifest_requires_hash_and_size_when_frozen() -> None:
    schema = _load("capital_control_source_manifest.schema.json")
    required = set(schema["required"])
    assert {
        "source_id",
        "source_family",
        "source_authority",
        "retrieval_utc",
        "source_url_or_locator",
        "byte_status",
    } <= required

    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "DISCOVERY_ONLY" in properties["source_family"]["enum"]
    assert "DISCOVERY_ONLY" in properties["canonicality"]["enum"]

    frozen_rule = schema["allOf"][0]
    assert frozen_rule["if"]["properties"]["byte_status"]["const"] == "FROZEN"
    assert set(frozen_rule["then"]["required"]) == {
        "raw_bytes_sha256",
        "raw_bytes_size",
    }
