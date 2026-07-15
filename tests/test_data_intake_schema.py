"""Schema-parse + structural checks for the new fusion/intake schemas.

Follows the dependency-light pattern of ``tests/test_canonical_v1_schema.py``:
parse the JSON and assert structure (no jsonschema dependency).
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"

NEW_SCHEMAS = [
    "data_intake_record.schema.json",
    "fusion_observation.schema.json",
    "publication_review.schema.json",
    "records_request.schema.json",
]


@pytest.mark.unit
@pytest.mark.parametrize("schema_file", NEW_SCHEMAS)
def test_schema_parses_and_is_wellformed(schema_file):
    data = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
    assert data.get("$schema"), f"{schema_file} missing $schema"
    assert data.get("title"), f"{schema_file} missing title"
    assert data.get("type") == "object"
    props = set(data.get("properties", {}))
    assert set(data.get("required", [])) <= props, (
        f"{schema_file} has required fields not declared as properties"
    )


@pytest.mark.unit
def test_intake_record_enums_present():
    data = json.loads((SCHEMA_DIR / "data_intake_record.schema.json").read_text())
    props = data["properties"]
    assert props["domain"]["enum"] == ["np_layer", "fin_audit", "inf_ctrl", "shared"]
    assert props["evidence_tier"]["enum"] == ["T1", "T2", "T3", "T4"]
    assert set(props["access_class"]["enum"]) == {"public", "restricted_public", "internal"}
    # PII + publication-eligibility are required, boolean gates.
    assert props["contains_pii"]["type"] == "boolean"
    assert props["publication_eligible"]["type"] == "boolean"
    assert "contains_pii" in data["required"]


@pytest.mark.unit
def test_fusion_observation_influence_conclusion_is_null_typed():
    """The observation schema pins influence_conclusion to the null type."""
    data = json.loads((SCHEMA_DIR / "fusion_observation.schema.json").read_text())
    assert data["properties"]["influence_conclusion"]["type"] == "null"
    assert "influence_conclusion" in data["required"]


@pytest.mark.unit
def test_publication_review_states():
    data = json.loads((SCHEMA_DIR / "publication_review.schema.json").read_text())
    assert data["properties"]["review_status"]["enum"] == [
        "internal",
        "legal_review",
        "fact_check",
        "public",
    ]
