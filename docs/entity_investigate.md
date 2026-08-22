# Entity Investigate

Status: **PROVISIONAL IMPLEMENTATION** — canonical target resolution and bounded local lineage/correlation are implemented; remote entity-mode fanout reuses the existing query dispatcher. Name-only cross-source matches remain discovery candidates.

## Canonical identity decision

Money Sweep uses the following identity hierarchy for investigations:

1. `ENT_*` is the internal canonical identity authority.
2. UEI, CAGE, DUNS, EIN, CIK and registry identifiers are attached external identifiers.
3. `entity_aliases.csv` is an authoritative alias binding to `ENT_*` because the alias row carries the canonical foreign key.
4. Normalized names in derived products are discovery keys only and never identity proof.
5. Specialized graph IDs such as `prepa_titleiii:*` remain domain-local until explicitly bridged to `ENT_*`.
6. Tied canonical/alias candidates fail closed to `REVIEW`; no deterministic winner is promoted.

Run the namespace set audit with:

```bash
python scripts/audit_entity_namespaces.py
```

It computes `INTERSECTION`, `A_ONLY`, `B_ONLY`, `UNION`, and `SYMMETRIC_DIFFERENCE` for derived name universes while classifying those overlaps `CANDIDATE_NOT_IDENTITY`.

## InvestigationTarget

The stable contract is defined by `moneysweep/investigate/models.py` and `schemas/investigation_target.schema.json`.

Core fields:

- requested value/kind
- `RESOLVED | REVIEW | UNRESOLVED`
- canonical `ENT_*` id/name/type/jurisdiction
- match method and matched authoritative value
- aliases
- attached external identifiers
- complete candidate set when ambiguous
- identity evidence and notes

External identifiers can only be attached to an explicit canonical `ENT_*` binding. They do not resolve a raw name by proximity.

## Modes

- `PROFILE` — canonical target and identity evidence.
- `LINEAGE` — bounded traversal of canonical parent/operator relationships.
- `CORRELATION` — stream local entity products and preserve exact canonical/alias discovery matches; shared UEI may be `LINKED`.
- `RELATIONSHIP` — lineage plus preserved cross-source correlations among selected targets.
- `CONVERGENCE` — bounded shared-node/correlation projection; v1 does not manufacture inferred graph identity.
- `FULL` — expands to all modes above.

## CLI

```bash
python scripts/investigate_entities.py PREPA Genera Arcadis --mode FULL
```

Optional bounded external identifier attachment:

```bash
python scripts/investigate_entities.py ENT_ORG_0f8f1789b2c687ed \
  --bind ENT_ORG_0f8f1789b2c687ed:uei:EXAMPLEUEI123 \
  --remote --source sam_entities --source usaspending_prime
```

Controls:

- `--depth`
- `--max-nodes`
- `--max-edges`
- `--max-local-matches`
- `--remote`
- repeated `--source`
- `--force-refresh`
- `--output`

Remote name results are discovery candidates unless independently bound by authoritative identifiers.

## Three-entity pilot regression

The regression pilot deliberately uses three different entity shapes:

| Input | Canonical result | Expected lineage behavior |
|---|---|---|
| `PREPA` | `ENT_AGENCY_6c1d858c1babe390` | Commonwealth instrumentality edge plus LUMA/Genera operator edges available |
| `Genera` | `ENT_ORG_0f8f1789b2c687ed` | PREPA operator edge available |
| `Arcadis` | `ENT_ORG_21371fab1b27e788` | no curated parent/operator edge; negative gate must remain empty |

`tests/test_investigate.py` also asserts that an unknown name remains `UNRESOLVED` and cannot generate lineage.

## Existing systems reused

The implementation intentionally does not create a new entity database. It reuses:

- `data/reference/entity_master.csv`
- `data/reference/entity_aliases.csv`
- `data/reference/entity_parent_map.csv`
- `EntityQuery` / `EntityIdentifier`
- `query_entities()` and `query()`
- `ENTITY_ADAPTER_REGISTRY` / `ADAPTER_REGISTRY`
- canonical name normalization for discovery only

## Remaining gaps

This v1 does **not** certify universal entity lineage. Remaining work includes dynamic corporate predecessor/successor discovery, canonical bridges for domain-local graph IDs, additional entity-mode adapters, generalized officer/address/property graph producers, and evidence-row materialization for every remote relationship edge.
