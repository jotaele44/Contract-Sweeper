"""Schema-contract tests for the canonical government entity registry (PR1).

These lock down the PR1 scaffold: the new government-entity JSON schemas, the
config vocabularies, and the versioned policy registry. Structural assertions run
unconditionally (no third-party dependency). Instance-level rejection tests are
gated on ``jsonschema`` per repo convention (it is not a hard dependency).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
CONFIG_DIR = ROOT / "config" / "government_entities"

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

NEW_SCHEMAS = [
    "government_entities.schema.json",
    "government_entity_names.schema.json",
    "government_entity_identifiers.schema.json",
    "government_entity_relationships.schema.json",
    "government_entity_source_assertions.schema.json",
    "government_entity_resolution_events.schema.json",
    "government_entity_conflicts.schema.json",
    "government_entity_coverage_audit.schema.json",
]

ENTITY_TYPE_VALUES = {
    "constitutional_office",
    "executive_department",
    "executive_agency",
    "authority",
    "public_corporation",
    "public_instrumentality",
    "board",
    "commission",
    "bureau",
    "administration",
    "office",
    "council",
    "institute",
    "trust",
    "fund",
    "public_university",
    "judicial_entity",
    "legislative_entity",
    "municipality",
    "municipal_instrumentality",
    "regional_entity",
    "program_office",
    "temporary_recovery_office",
    "other_public_entity",
}

IDENTIFIER_SCHEME_VALUES = {
    "ocpr_entity_code",
    "hacienda_agency_code",
    "ogp_budget_entity_code",
    "prifas_agency_code",
    "procurement_entity_code",
    "asg_licitador_id",
    "transition_report_agency_code",
    "cor3_applicant_id",
    "fema_recipient_id",
    "fema_subrecipient_id",
    "sam_uei",
    "legacy_duns",
    "cage_code",
    "ein",
    "fips_county_equivalent_code",
    "gnis_id",
    "municipality_code",
    "bond_issuer_code",
    "custom_source_code",
}

RELATIONSHIP_TYPE_VALUES = {
    "parent_of",
    "component_of",
    "reports_to",
    "controlled_by",
    "owns",
    "predecessor_of",
    "successor_of",
    "renamed_to",
    "merged_into",
    "split_into",
    "absorbed_functions_from",
    "transferred_functions_to",
    "created_from",
    "abolished_by",
    "fiscal_agent_for",
    "bond_issuer_for",
    "operator_of",
    "concessionaire_for",
    "procurement_agent_for",
    "oversight_of",
    "regulated_by",
    "administers_program_for",
    "municipal_component_of",
    "possible_successor_of",
    "possible_predecessor_of",
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _config(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def _registry_yaml() -> dict:
    return yaml.safe_load(
        (ROOT / "registries" / "government_entity_registry.yaml").read_text(encoding="utf-8")
    )


def _registry_body() -> dict:
    return _registry_yaml()["government_entity_registry"]


# ---------------------------------------------------------------------------
# Structural assertions (always run)
# ---------------------------------------------------------------------------
def test_every_new_schema_loads_as_strict_draft_2020_12():
    for name in NEW_SCHEMAS:
        schema = _schema(name)
        assert schema["$schema"] == DRAFT_2020_12, name
        assert schema["$id"] == f"https://moneysweep-pr/schemas/{name}", name
        assert schema["additionalProperties"] is False, f"{name} must be strict"
        assert schema["type"] == "object", name
        assert schema["required"], f"{name} must declare required fields"


def test_required_fields_present_per_schema():
    expected = {
        "government_entities.schema.json": {
            "entity_id",
            "entity_type",
            "status",
            "source_assertion_id",
        },
        "government_entity_names.schema.json": {
            "entity_id",
            "language",
            "name_type",
            "name",
            "normalized_name",
            "valid_from",
            "is_preferred",
            "source_assertion_id",
        },
        "government_entity_identifiers.schema.json": {
            "entity_id",
            "identifier_scheme",
            "identifier_value",
            "source_system",
            "status",
            "confidence",
            "source_assertion_id",
        },
        "government_entity_relationships.schema.json": {
            "subject_entity_id",
            "relationship_type",
            "object_entity_id",
            "valid_from",
            "confidence",
            "source_assertion_id",
        },
        "government_entity_source_assertions.schema.json": {
            "source_assertion_id",
            "source_id",
            "source_locator",
            "evidence_tier",
            "retrieved_at",
            "content_hash",
            "verification_status",
        },
        "government_entity_resolution_events.schema.json": {
            "resolution_event_id",
            "raw_values",
            "candidates",
            "matching_rule",
            "confidence",
            "resolver_version",
            "review_state",
            "source_assertion_id",
        },
        "government_entity_conflicts.schema.json": {
            "conflict_id",
            "conflict_type",
            "entity_ids",
            "status",
            "source_assertion_id",
        },
        "government_entity_coverage_audit.schema.json": {
            "coverage_dimension",
            "denominator_source",
            "snapshot_date",
            "source_hash",
            "denominator",
            "resolved",
            "unresolved",
            "excluded",
            "computed_pct",
        },
    }
    for name, required in expected.items():
        assert required.issubset(set(_schema(name)["required"])), name


def test_schema_enums_carry_the_mandated_vocabularies():
    ent = _schema("government_entities.schema.json")
    assert set(ent["$defs"]["entity_type"]["enum"]) == ENTITY_TYPE_VALUES

    ids = _schema("government_entity_identifiers.schema.json")
    assert set(ids["$defs"]["identifier_scheme"]["enum"]) == IDENTIFIER_SCHEME_VALUES

    rel = _schema("government_entity_relationships.schema.json")
    assert set(rel["$defs"]["relationship_type"]["enum"]) == RELATIONSHIP_TYPE_VALUES

    assertion = _schema("government_entity_source_assertions.schema.json")
    assert set(assertion["$defs"]["evidence_tier"]["enum"]) == {"T1", "T2", "T3", "T4"}


def test_entity_id_is_not_name_derived():
    # Registry-assigned opaque pattern, and the entity record carries no name.
    ent = _schema("government_entities.schema.json")
    assert ent["properties"]["entity_id"]["pattern"] == "^GOV_[A-Z0-9]{4,}$"
    assert "name" not in ent["properties"]
    assert "preferred_name" not in ent["properties"]


def test_bare_identifier_value_is_not_sufficient():
    ids = _schema("government_entity_identifiers.schema.json")
    required = set(ids["required"])
    # A bare value can never stand alone: scheme + source_system + provenance required.
    assert {"identifier_scheme", "identifier_value", "source_system"} <= required
    assert required - {"identifier_value"}, "more than identifier_value is required"
    # The 4-part uniqueness scope is documented on the schema.
    assert "identifier_scheme" in ids["$comment"]
    assert "source_system" in ids["$comment"]
    assert "valid_from" in ids["$comment"]


def test_same_numeric_value_allowed_under_different_schemes():
    # Uniqueness is scoped by scheme (+ source_system + valid_from), so the same
    # identifier_value under two schemes is two distinct identifiers.
    ids = _schema("government_entity_identifiers.schema.json")
    assert len(ids["$defs"]["identifier_scheme"]["enum"]) >= 2
    body = _registry_body()
    assert body["identifier_schemes"]["namespaced_required"] is True


def test_source_system_and_provenance_required():
    ids = _schema("government_entity_identifiers.schema.json")
    assert "source_system" in ids["required"]
    assert "source_assertion_id" in ids["required"]
    assertion = _schema("government_entity_source_assertions.schema.json")
    for field in (
        "source_id",
        "source_locator",
        "evidence_tier",
        "content_hash",
        "verification_status",
    ):
        assert field in assertion["required"], field


def test_valid_from_valid_to_shapes_enforced():
    for name in (
        "government_entity_names.schema.json",
        "government_entity_identifiers.schema.json",
        "government_entity_relationships.schema.json",
    ):
        props = _schema(name)["properties"]
        for field in ("valid_from", "valid_to"):
            assert props[field]["format"] == "date", f"{name}:{field}"
            assert props[field]["type"] == ["string", "null"], f"{name}:{field}"


def test_coverage_denominator_metadata_required():
    cov = _schema("government_entity_coverage_audit.schema.json")
    required = set(cov["required"])
    for field in (
        "denominator",
        "denominator_source",
        "source_hash",
        "snapshot_date",
        "computed_pct",
    ):
        assert field in required, field


def test_immutable_id_policy_declared():
    policy = _registry_body()["canonical_id_policy"]
    assert policy["immutable"] is True
    assert policy["name_derived"] is False
    assert policy["assignment"] == "registry_assigned"
    assert policy["id_pattern"] == "^GOV_[A-Z0-9]{4,}$"


def test_all_validation_gates_declared():
    gates = {g["id"] for g in _registry_body()["validation_gates"]}
    expected = {
        "SCHEMA_VALID",
        "CANONICAL_ID_STABLE",
        "IDENTIFIER_NAMESPACED",
        "NO_UNSCOPED_CODE",
        "TEMPORAL_NONOVERLAP",
        "RELATIONSHIP_VALID",
        "SUCCESSION_SYMMETRY",
        "NO_SELF_RELATION",
        "PROVENANCE_REQUIRED",
        "MUNICIPALITY_COMPLETE",
        "CURRENT_ENTITY_COMPLETE",
        "SOURCE_CODE_COMPLETE",
        "ROUND_TRIP_RESOLUTION",
        "CONFLICT_QUEUE_EMPTY_OR_ACCEPTED",
        "COVERAGE_REPORT_GENERATED",
        "LEGACY_PROJECTION_VALID",
        "EXPORTED_SCHEMA_UNCHANGED",
        "REGISTRY_YAML_JSON_SYNC",
        "NAME_DERIVED_ID_NOT_USED_FOR_NEW_GOV_ENTITIES",
    }
    assert expected <= gates


def test_self_relation_is_rejected():
    # JSON Schema cannot compare two field values, so NO_SELF_RELATION is a
    # semantic gate: it must be declared, the conflict queue must model it, and a
    # subject==object relation must be flagged.
    gates = {g["id"] for g in _registry_body()["validation_gates"]}
    assert "NO_SELF_RELATION" in gates
    conflicts = _schema("government_entity_conflicts.schema.json")
    assert "self_relation" in conflicts["properties"]["conflict_type"]["enum"]

    def no_self_relation(rel: dict) -> bool:
        return rel["subject_entity_id"] != rel["object_entity_id"]

    assert no_self_relation({"subject_entity_id": "GOV_1", "object_entity_id": "GOV_2"})
    assert not no_self_relation({"subject_entity_id": "GOV_1", "object_entity_id": "GOV_1"})


def test_config_vocabularies_match_schema_enums():
    entity_ids = {t["id"] for t in _config("entity_types.yml")["entity_types"]}
    assert entity_ids == ENTITY_TYPE_VALUES

    scheme_ids = {s["id"] for s in _config("identifier_schemes.yml")["identifier_schemes"]}
    assert scheme_ids == IDENTIFIER_SCHEME_VALUES
    assert all(
        s.get("namespaced") is True for s in _config("identifier_schemes.yml")["identifier_schemes"]
    )

    rel_ids = {r["id"] for r in _config("relationship_types.yml")["relationship_types"]}
    assert rel_ids == RELATIONSHIP_TYPE_VALUES


def test_operators_and_concessionaires_are_not_legal_successors():
    by_id = {r["id"]: r for r in _config("relationship_types.yml")["relationship_types"]}
    for rel_id in ("operator_of", "concessionaire_for"):
        assert by_id[rel_id]["legal_succession"] is False, rel_id
    # Rename continuity is kept distinct from succession.
    assert by_id["renamed_to"]["category"] == "continuity"
    assert by_id["renamed_to"]["legal_succession"] is False


def test_governed_schema_manifest_is_complete():
    manifest = _registry_body()["schema_manifest"]
    assert manifest["contract_version"]
    assert manifest["governance"] == "internal_derived"
    governed = manifest["schemas"]
    for rel in governed:
        assert (ROOT / rel).is_file(), rel
    # No ungoverned schema and no stray manifest entry.
    assert {Path(p).name for p in governed} == set(NEW_SCHEMAS)


def test_registry_config_refs_exist_and_versions_match():
    body = _registry_body()
    checks = {
        "entity_types": "government_entity_types_v1",
        "identifier_schemes": "government_entity_identifier_schemes_v1",
        "relationship_types": "government_entity_relationship_types_v1",
        "resolution_policy": "government_entity_resolution_policy_v1",
    }
    for key, declared_version in checks.items():
        ref = body[key]
        path = ROOT / ref["config_ref"]
        assert path.is_file(), ref["config_ref"]
        assert ref["schema_version"] == declared_version, f"registry ref {key}"
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert cfg["schema_version"] == declared_version, f"config file {key}"


def test_no_duplicate_enum_or_config_ids():
    for name, def_key in [
        ("government_entities.schema.json", "entity_type"),
        ("government_entity_identifiers.schema.json", "identifier_scheme"),
        ("government_entity_relationships.schema.json", "relationship_type"),
    ]:
        enum = _schema(name)["$defs"][def_key]["enum"]
        assert len(enum) == len(set(enum)), f"duplicate in {name}:{def_key}"
    for cfg_name, list_key in [
        ("entity_types.yml", "entity_types"),
        ("identifier_schemes.yml", "identifier_schemes"),
        ("relationship_types.yml", "relationship_types"),
    ]:
        ids = [r["id"] for r in _config(cfg_name)[list_key]]
        assert len(ids) == len(set(ids)), f"duplicate id in {cfg_name}"


def test_registry_yaml_and_generated_json_are_equivalent():
    yaml_data = _registry_yaml()
    json_data = json.loads(
        (ROOT / "registries" / "government_entity_registry.json").read_text(encoding="utf-8")
    )
    assert yaml_data == json_data, (
        "registries/government_entity_registry.json is stale — "
        "run scripts/regenerate_registry_json.py"
    )


# ---------------------------------------------------------------------------
# Exported-contract preservation and legacy compatibility
# ---------------------------------------------------------------------------
def test_no_exported_schema_file_changed():
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "schemas/"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    changed = [p for p in out.splitlines() if p]
    offenders = [
        p
        for p in changed
        if (p.startswith("schemas/moneysweep_") and p.endswith(".schema.json"))
        or p.startswith("schemas/canonical_v1/")
    ]
    assert offenders == [], f"exported/frozen schema modified: {offenders}"


def test_legacy_schema_paths_still_exist():
    for rel in (
        "schemas/agency_master.schema.json",
        "schemas/entity_aliases.schema.json",
        "schemas/entity_master.schema.json",
        "schemas/municipality_crosswalk.schema.json",
        "schemas/moneysweep_entity.schema.json",
        "schemas/moneysweep_relationship.schema.json",
        "schemas/canonical_v1/entities.schema.json",
        "schemas/canonical_v1/edges.schema.json",
    ):
        assert (ROOT / rel).is_file(), rel


# ---------------------------------------------------------------------------
# Instance-level rejection tests (require jsonschema; skip if absent)
# ---------------------------------------------------------------------------
def _validator(name: str):
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(_schema(name))


def test_instance_valid_records_pass():
    _validator("government_entity_identifiers.schema.json").validate(
        {
            "entity_id": "GOV_000123",
            "identifier_scheme": "hacienda_agency_code",
            "identifier_value": "081",
            "source_system": "hacienda",
            "status": "active",
            "confidence": 0.99,
            "source_assertion_id": "SA_1",
        }
    )
    _validator("government_entity_relationships.schema.json").validate(
        {
            "subject_entity_id": "GOV_0001",
            "relationship_type": "parent_of",
            "object_entity_id": "GOV_0002",
            "valid_from": "2000-01-01",
            "confidence": 0.9,
            "source_assertion_id": "SA_1",
        }
    )


def test_instance_unsupported_relationship_type_rejected():
    v = _validator("government_entity_relationships.schema.json")
    assert not v.is_valid(
        {
            "subject_entity_id": "GOV_0001",
            "relationship_type": "not_a_real_type",
            "object_entity_id": "GOV_0002",
            "valid_from": "2000-01-01",
            "confidence": 0.9,
            "source_assertion_id": "SA_1",
        }
    )


def test_instance_missing_source_system_rejected():
    v = _validator("government_entity_identifiers.schema.json")
    # bare identifier_value without source_system/scheme is not valid
    assert not v.is_valid(
        {
            "entity_id": "GOV_0001",
            "identifier_value": "081",
            "status": "active",
            "confidence": 0.5,
            "source_assertion_id": "SA_1",
        }
    )


def test_instance_bad_valid_from_shape_rejected():
    v = _validator("government_entity_names.schema.json")
    assert not v.is_valid(
        {
            "entity_id": "GOV_0001",
            "language": "es",
            "name_type": "official",
            "name": "Departamento de Hacienda",
            "normalized_name": "departamento de hacienda",
            "valid_from": 20000101,  # wrong type: integer, not date string/null
            "is_preferred": True,
            "source_assertion_id": "SA_1",
        }
    )


def test_instance_coverage_missing_denominator_rejected():
    v = _validator("government_entity_coverage_audit.schema.json")
    assert not v.is_valid(
        {
            "coverage_dimension": "municipality",
            "denominator_source": "census_2020",
            "snapshot_date": "2026-01-01",
            "source_hash": "sha256:deadbeef",
            # denominator omitted
            "resolved": 78,
            "unresolved": 0,
            "excluded": 0,
            "computed_pct": 100.0,
        }
    )


def test_instance_source_assertion_hash_rules():
    v = _validator("government_entity_source_assertions.schema.json")
    good = {
        "source_assertion_id": "SA_1",
        "source_id": "hacienda",
        "source_locator": "https://example/doc#p1",
        "evidence_tier": "T1",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "content_hash": "sha256:deadbeefcafe",
        "verification_status": "machine_verified",
    }
    v.validate(good)
    assert not v.is_valid({**good, "content_hash": "short"})  # below minLength 8
