# Road to 100%

This ledger states what remains between `moneysweep-pr` and production
certification. Current counts come from `reports/materialization_readiness.json`
and the certified offline operator audit, not from older narrative snapshots.

## Current state — 2026-07-30

| Gate | Current result |
|---|---:|
| Registry sources | **151** |
| Automatable sources structurally ready | **104/104** |
| Queued or intentionally excluded | **47** |
| Fully materialized | **67/151** |
| Partially materialized | **11/151** |
| Not materialized | **73/151** |
| Required sources fully materialized | **10/14** |
| Physical processed rows | **1,183,565** |
| Registry-declared rows | **849,898** |
| Adjudicated derived-output rows | **212,930** |
| Pipeline-intermediate rows | **120,737** |
| Unadjudicated orphan rows | **0** |
| Production status | **`NON_PRODUCTION_DIAGNOSTIC`** |

The code and control plane are substantially complete. The remaining work is
dominated by valid source acquisition, freshness and universe certification,
entity-product comparison, production export, and downstream-consumer checks.

## Certified Wave 0 evidence

The authoritative offline operator bundle is
`MONEYSWEEP_WAVE0_OPERATOR_AUDIT.zip`, SHA-256
`2a37bf4c49f5e4d267ca4cbdc8366c718efc1738de607cdbe3cbbbd3ec8b9f85`.
It records `probe_ran=false`; no public-universe probe or live producer was used
to derive the current materialization counts.

Output ownership is adjudicated in
`reports/WAVE0_REQUIRED_GAP_AND_ORPHAN_ADJUDICATION.json`. Six positive-row
files previously surfaced by the raw filename audit are derived products rather
than primary registry-source outputs. Their 212,930 rows remain excluded from
source-materialization credit, and the complete physical-row equation has exact
parity with no double counting.

## Four required-source gaps

Access and provenance evidence is recorded in
`reports/WAVE0_REQUIRED_SOURCE_EVIDENCE_2026-07-30.json`.

| Source | Current disposition | Materialization credit |
|---|---|---:|
| `cor3` | Official export surface verified; workbook bytes not acquired | No |
| `hud_drgr_authorized` | Authorized local export required and not present | No |
| `pr_cabilderos` | Public registry verified; complete export not acquired | No |
| `prasa` | Official contract-export route verified; PRASA-filtered export not acquired | No |

The result remains **10/14 required sources fully materialized**. Access-surface
availability is not equivalent to possession of a validated, current export.
No credentialed login, live producer execution, or production-data promotion
occurred in this vector.

### Required operator inputs

- COR3 Transparency Portal Excel workbooks under `data/raw/COR3/`.
- Authorized HUD DRGR exports under `data/manual/hud_drgr/` or a documented
  legacy HUD raw path.
- Official cabilderos CSV/XLSX exports under `data/raw/Cabilderos/`.
- PRASA/AAA contract CSV/XLSX exports under `data/raw/PRASA/`.

Each ingest must retain source filename provenance, pass schema and row-level
validation, establish an explicit as-of boundary, and regenerate coverage before
materialization credit changes.

## Entity-product comparison

`entity_master.csv` and `pr_entity_profiles.csv` each had 104,280 rows in the
certified operator inventory. Equal row counts do not establish duplication.
The products also have different intended semantics:

- `entity_master` is an export-facing entity authority with canonical IDs and
  evidence metadata.
- `pr_entity_profiles` is an awards-derived enrichment keyed by normalized
  recipient names and supplementary financial attributes.

`scripts/compare_entity_products.py` now performs an offline deterministic
comparison covering:

1. ordered schemas and schema fingerprints;
2. file SHA-256 values;
3. canonical row-hash multisets;
4. independently selected stable name keys;
5. blank and duplicate key counts;
6. normalized stable-key intersection and Jaccard rates;
7. shared-column projected-row overlap;
8. an explicit duplicate-status decision.

The certified evidence bundle did not contain either CSV, so the comparison is
currently **`PENDING_OPERATOR_CORPUS_EXECUTION`**. Run:

```bash
python3 scripts/compare_entity_products.py \
  --output reports/entity_product_comparison.json
```

Only the generated report should be committed. The gitignored operator CSVs
remain local. The report certifies local structure and overlap; it does not
certify freshness of upstream external sources.

## Remaining production gates

### P0 — data and identity

1. Supply and ingest the four required-source exports.
2. Execute the entity-product comparison and adjudicate the resulting status.
3. Reconcile PR2.5 and PR2.6 before PR3 entity deduplication.
4. Regenerate the 151-source materialization audit with registry-digest parity.

### P1 — external completeness and freshness

1. Establish source-specific as-of timestamps and cadence rules.
2. Compare local row universes with authoritative public or authorized totals.
3. Preserve partial, inaccessible, and manual-source states explicitly.
4. Implement the two genuine scraper stubs: `hacienda_sut_ivu` and
   `pr_act_154_excise`.

### P2 — production and federation

1. Validate production export schemas, hashes, lineage, and no-double-counting.
2. Validate downstream federation consumers against pinned exports.
3. Run the production-status and promotion guards.
4. Change `production_status` only through an explicitly authorized promotion
   vector after every required gate passes.

## Preservation rules

- PR #448 remains draft and unmerged.
- No auto-merge, force push, or history rewrite.
- No credentialed or live fetch without separate explicit authorization and
  valid source access.
- No production-data promotion.
- No materialization credit based solely on reachable pages, header-only files,
  equal row counts, or unverified endpoint guesses.

## Next controlled vector

`INGEST_REQUIRED_EXPORTS_AND_RUN_ENTITY_PRODUCT_COMPARISON`

The production status remains `NON_PRODUCTION_DIAGNOSTIC` until the required
data gaps, entity comparison, freshness, production export, and downstream
consumer gates pass.
