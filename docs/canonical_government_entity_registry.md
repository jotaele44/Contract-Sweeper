# Canonical Government Entity Registry

The canonical government entity registry is the single, versioned model of Puerto
Rico government entities: their **immutable identity**, their **names over time**,
the **source-system codes** that refer to them, the **relationships** between them,
the **provenance** behind every assertion, and the **coverage** of the universe.

Historically, entity identity was spread across `agency_master`, `entity_master`,
the alias tables, and the `canonical_v1` CSVs. This registry unifies that identity
model without disturbing those legacy outputs — legacy agency/entity projections
and every exported `moneysweep_*` schema are preserved.

## PR1 scope

PR1 is a **scaffold**. It ships the schema contracts, config vocabularies, a
versioned **policy** registry, this document, and a schema-contract test. It does
**not** seed an entity inventory. The runtime enforcers for the semantic
validation gates arrive in later PRs; PR1 only *declares* them.

## Files

| Concern | File |
|---|---|
| Policy registry (YAML, authoritative) | `registries/government_entity_registry.yaml` |
| Policy registry (JSON, generated) | `registries/government_entity_registry.json` |
| Entity record | `schemas/government_entities.schema.json` |
| Names (temporal) | `schemas/government_entity_names.schema.json` |
| Identifiers (source codes) | `schemas/government_entity_identifiers.schema.json` |
| Relationships | `schemas/government_entity_relationships.schema.json` |
| Source assertions (provenance) | `schemas/government_entity_source_assertions.schema.json` |
| Resolution events | `schemas/government_entity_resolution_events.schema.json` |
| Conflict queue | `schemas/government_entity_conflicts.schema.json` |
| Coverage audit | `schemas/government_entity_coverage_audit.schema.json` |
| Entity-type vocabulary | `config/government_entities/entity_types.yml` |
| Identifier-scheme vocabulary | `config/government_entities/identifier_schemes.yml` |
| Relationship-type vocabulary | `config/government_entities/relationship_types.yml` |
| Resolution policy | `config/government_entities/resolution_policy.yml` |

## Schema governance and versioning

The eight `government_entity_*` schemas are **internal / derived** and are
versioned **as a set** through the `schema_manifest` block in
`registries/government_entity_registry.yaml` (`contract_version`, currently
`1.0.0`), rather than carrying a per-file version. The manifest is the governance
list: every schema it names must exist, and every `government_entity_*` schema on
disk must appear in it — the schema-contract test fails if the two drift.

## Immutable identity

`entity_id` is an **immutable, registry-assigned, opaque** identifier matching
`^GOV_[A-Z0-9]{4,}$`. It is **never derived from a name** (gate
`NAME_DERIVED_ID_NOT_USED_FOR_NEW_GOV_ENTITIES`) and is **stable across renames,
reorganizations, and status changes** (gate `CANONICAL_ID_STABLE`). Names live in
the names table, not on the entity, so the identity of an entity never depends on
what it is currently called.

This is deliberately different from the name-hash IDs produced by
`moneysweep.runtime.canonical_ids` for other node types: those are content-derived
by design, whereas government entities require a stable identity that survives
renames.

## Identifier namespacing and uniqueness

Every identifier is namespaced by an `identifier_scheme` (gates
`IDENTIFIER_NAMESPACED`, `NO_UNSCOPED_CODE`); a bare `identifier_value` is never
sufficient. Identifier uniqueness is scoped by:

```
identifier_scheme + identifier_value + source_system + valid_from
```

so the same numeric string may legitimately exist under two different schemes (for
example a value that is both a `hacienda_agency_code` and an
`ogp_budget_entity_code`). JSON Schema cannot express this composite key, so the
schema requires all four components and the registry documents the key; the
composite-uniqueness check is a registry gate, not a schema constraint.

## Temporal validity, rename vs. succession

Names, identifiers, and relationships carry `valid_from` / `valid_to` intervals
(`valid_to = null` means currently valid). Preferred names per entity, and
identifiers per `(scheme, source_system)`, must not overlap in time (gate
`TEMPORAL_NONOVERLAP`).

**Rename continuity is kept separate from succession.** A rename is a new name row
(with `name_type` `former`/`official`) on the *same* `entity_id`, optionally with a
`renamed_to` relationship — it does **not** change legal identity. Merger, split,
abolition, and function transfer *do* change identity or functions and use the
succession/function-transfer relationship types. Succession relations are recorded
symmetrically (`predecessor_of` ⇔ `successor_of`, and the `possible_*` variants for
unproven cases; gate `SUCCESSION_SYMMETRY`).

**Private operators and concessionaires are never legal successors.**
`operator_of` and `concessionaire_for` are flagged `legal_succession: false`; a
concessionaire or operator of a public asset is not a successor of the owning
entity unless evidence explicitly proves legal succession.

## Provenance

Every entity, name, identifier, and relationship references a `source_assertion_id`
that resolves to a source-assertion record (gate `PROVENANCE_REQUIRED`). An
assertion captures the `source_id`, `source_locator`, `evidence_tier` (T1–T4),
`retrieved_at`, `content_hash`, and `verification_status`.

## Coverage

Coverage audits measure how completely a denominator universe resolves to canonical
entities across three dimensions: `municipality` (the 78 municipalities),
`current_entity` (all active entities), and `source_code` (every source-system
code). The denominator source and its hash are required, so a percentage can never
be reported without a traceable universe (gates `MUNICIPALITY_COMPLETE`,
`CURRENT_ENTITY_COMPLETE`, `SOURCE_CODE_COMPLETE`, `COVERAGE_REPORT_GENERATED`).

## Validation gates

The registry declares the full gate set:

`SCHEMA_VALID`, `CANONICAL_ID_STABLE`, `IDENTIFIER_NAMESPACED`, `NO_UNSCOPED_CODE`,
`TEMPORAL_NONOVERLAP`, `RELATIONSHIP_VALID`, `SUCCESSION_SYMMETRY`,
`NO_SELF_RELATION`, `PROVENANCE_REQUIRED`, `MUNICIPALITY_COMPLETE`,
`CURRENT_ENTITY_COMPLETE`, `SOURCE_CODE_COMPLETE`, `ROUND_TRIP_RESOLUTION`,
`CONFLICT_QUEUE_EMPTY_OR_ACCEPTED`, `COVERAGE_REPORT_GENERATED`,
`LEGACY_PROJECTION_VALID`, `EXPORTED_SCHEMA_UNCHANGED`, `REGISTRY_YAML_JSON_SYNC`,
`NAME_DERIVED_ID_NOT_USED_FOR_NEW_GOV_ENTITIES`.

## Editing workflow

The registry follows the repo's YAML-authoritative / JSON-generated convention
(see `registries/README.md`):

```bash
# edit registries/government_entity_registry.yaml, then:
python3 scripts/regenerate_registry_json.py
git add registries/government_entity_registry.json
```

Never hand-edit the JSON. The `registry-sync.yml` CI check regenerates in a clean
checkout and fails on drift.
