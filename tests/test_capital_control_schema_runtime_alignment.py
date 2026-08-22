import json
from pathlib import Path

from moneysweep.capital_control.models import (
    AMENDMENT_STATUSES,
    BINDING_BASES,
    BYTE_STATUSES,
    CANONICALITY_STATES,
    DIRECTNESS_STATES,
    IDENTITY_LEVELS,
    IDENTITY_STATUSES,
    POSITION_CLASSES,
    SOURCE_FAMILIES,
    TRISTATE_STATES,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def _schema(name: str) -> dict[str, object]:
    with (SCHEMAS / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _enum(schema: dict[str, object], property_name: str) -> set[str]:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    property_schema = properties[property_name]
    assert isinstance(property_schema, dict)
    values = property_schema["enum"]
    assert isinstance(values, list)
    return set(values)


def test_investor_runtime_enums_match_schema() -> None:
    schema = _schema("capital_control_investor.schema.json")
    assert _enum(schema, "identity_level") == IDENTITY_LEVELS
    assert _enum(schema, "identity_status") == IDENTITY_STATUSES
    assert _enum(schema, "binding_basis") == BINDING_BASES


def test_holding_runtime_enums_match_schema() -> None:
    schema = _schema("capital_control_holding_observation.schema.json")
    assert _enum(schema, "position_class") == POSITION_CLASSES
    assert _enum(schema, "direct_or_indirect") == DIRECTNESS_STATES
    assert _enum(schema, "beneficial_owner_status") == TRISTATE_STATES
    assert _enum(schema, "investment_adviser_status") == TRISTATE_STATES
    assert _enum(schema, "control_status") == TRISTATE_STATES
    assert _enum(schema, "amendment_status") == AMENDMENT_STATUSES
    assert _enum(schema, "identity_status") == IDENTITY_STATUSES


def test_source_runtime_enums_match_schema() -> None:
    schema = _schema("capital_control_source_manifest.schema.json")
    assert _enum(schema, "source_family") == SOURCE_FAMILIES
    assert _enum(schema, "byte_status") == BYTE_STATUSES
    assert _enum(schema, "canonicality") == CANONICALITY_STATES


def test_schema_conditionals_reject_nullable_shortcuts_by_contract_shape() -> None:
    holding = _schema("capital_control_holding_observation.schema.json")
    security_alternatives = holding["anyOf"]
    assert isinstance(security_alternatives, list)
    assert all(
        alternative["properties"][next(iter(alternative["properties"]))]["type"] == "string"
        for alternative in security_alternatives
    )

    source = _schema("capital_control_source_manifest.schema.json")
    frozen_then = source["allOf"][0]["then"]
    assert frozen_then["properties"]["raw_bytes_sha256"]["type"] == "string"
    assert frozen_then["properties"]["raw_bytes_size"]["type"] == "integer"
