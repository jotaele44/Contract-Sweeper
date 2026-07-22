# schemas/

JSON Schema definitions for canonical outputs and internal/derived tables.

## Two schema classes

| Prefix | Class | Purpose |
|---|---|---|
| `moneysweep_*.schema.json` | **Exported canonical contract** | Read by downstream consumers — most importantly `spiderweb-pr`'s federation adapter. Version changes here are a cross-repo coordination event. |
| _(no prefix)_ | Internal / derived | Schemas for tables this repo produces but doesn't export across the federation boundary. Free to evolve without cross-repo sign-off. |

The audit (Phase 3, Audit #8 in `reports/codebase_audit.md`) flagged the
prefix convention as load-bearing but undocumented. This file is the policy
document.

## The exported set (`moneysweep_*`)

```
moneysweep_entity.schema.json
moneysweep_export_manifest.schema.json
moneysweep_funding_award.schema.json
moneysweep_relationship.schema.json
moneysweep_source.schema.json
moneysweep_transaction.schema.json
moneysweep_finance_lane_report.schema.json
```

The first six files define the public surface area moneysweep-pr publishes for
federated consumption. The README at repo root cites a "Contract-Finance"
export contract (currently v1.2.0, the single source of truth being
`EXPORT_CONTRACT_VERSION` in `scripts/build_export_package.py`); these schemas are
how that contract is expressed in machine-readable form.

#### Two independent versioned contracts (don't conflate)

The seventh file, `moneysweep_finance_lane_report.schema.json`, models the
report dict emitted by `readiness/moneysweep_finance_lane.py` — the
moneysweep-pr counterpart to spiderweb-pr's spatial-lane report. It is a
**separate** exported contract with its **own** version lineage, currently **1.0.0**
(the single source of truth being `EXPORT_CONTRACT_VERSION` in that module). The two
module-level constants share a name (`EXPORT_CONTRACT_VERSION`) but version different
things — bump them independently:

| Contract | Version constant | Current | Schema |
|---|---|---|---|
| Federation "moneysweep-pr-export" (→ spiderweb-pr query-hub) | `scripts/build_export_package.py` | 1.2.0 | the first six files |
| Finance-lane report | `readiness/moneysweep_finance_lane.py` | 1.0.0 | `moneysweep_finance_lane_report.schema.json` |

### Editing rules for exported schemas

1. **Bump the schema version** when changing field shapes, types, or
   required-flag values. Patch bumps for additions, minor bumps for required
   relaxations, major bumps for breaking removals or renames.
2. **Coordinate with `spiderweb-pr`** before changing exported schemas — the
   downstream adapter pins specific shapes. Open a PR in both repos in lockstep.
3. **Add a regression fixture** under `tests/` whenever you add or rename a
   field, to lock down the contract.

## The internal set (everything else)

The other internal schemas (`agency_master`, `entity_aliases`, `graph_edges`,
`influence_edges`, `municipality_crosswalk`, …) describe tables this repo
produces for its own use. They're free to evolve in single PRs without
cross-repo sign-off.

### Canonical government entity registry (internal)

The `government_entity_*` schemas model the canonical Puerto Rico government
entity registry. They are **internal / derived** — deliberately **not** part of
the exported `moneysweep_*` contract — so they carry no cross-repo coordination
burden. See `docs/canonical_government_entity_registry.md` and the policy
registry in `registries/government_entity_registry.yaml`.

```
government_entities.schema.json
government_entity_names.schema.json
government_entity_identifiers.schema.json
government_entity_relationships.schema.json
government_entity_source_assertions.schema.json
government_entity_resolution_events.schema.json
government_entity_conflicts.schema.json
government_entity_coverage_audit.schema.json
```

## Versioning by directory

The `schemas/canonical_v1/` directory holds the v1-frozen exported schemas
for compatibility while v2 is in development. When you cut v2:

1. Copy the v1 exported schemas to `schemas/canonical_v1/` (if not already).
2. Bump the schemas in `schemas/` to v2 shape.
3. Update `spiderweb-pr`'s adapter to read whichever version it pins.

## Naming convention quick reference

| Pattern | Means |
|---|---|
| `<name>.schema.json` | JSON Schema file (the `.schema` suffix is the marker). |
| `moneysweep_<name>.schema.json` | Member of the exported canonical contract. Treat as a public API surface. |
| `schemas/canonical_v1/<name>.schema.json` | Frozen v1 snapshot for downstream-pin compatibility. |

## Federation cross-reference: PR natural-features gazetteer

The federation maintains a canonical Puerto Rico **natural-features gazetteer**
(rivers, quebradas, lakes, reservoirs, wetlands, mountains, peaks, valleys,
coastal features), owned/curated by `spiderweb-pr` and derived from USGS GNIS.
Producers consume domain slices under one shared contract
(`pr_natural_feature.schema.json`; see spiderweb-pr
`docs/NATURAL_FEATURES_CONTRACT.md`).

**moneysweep-pr is a non-consumer of the gazetteer** — public-money entities have
no natural-feature records, so no slice is vendored here. Any spatial correlation
with natural features happens at the Hub on the shared **PR municipality**
vocabulary — this repo's `municipality_crosswalk.schema.json` and the municipality
code / coordinates carried on award and transaction rows (the municipality code is
the primary spatial match key; see `docs/export_mapping.md`). It is **not** a
name-based join to feature names: `normalized_name` on `moneysweep_entity`
canonicalizes a funding party (contractor/agency), not a place, and entity rows
carry no geography. If a future lane ever needs feature-level geography, add it as
a vendored slice + a `pr_natural_feature` reference schema then, per the contract's
lockstep change protocol.
