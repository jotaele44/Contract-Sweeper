# MoneySweep — Normalized Road to 100

**Reconciled:** 2026-07-30  
**Merged PR:** #448  
**Active draft PR:** #452  
**Main:** `9e911203a05cf8f2e99c762161b7ec18de8cef73`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Certified denominator and local corpus

| Measure | Value | Boundary |
|---|---:|---|
| Registry sources | 151 | Source-ID digest parity passed |
| Automatable wiring | 104/104 | Structural readiness only |
| Queued/excluded | 47 | 40 manual, 2 scraper, 3 semantic duplicates, 2 deferred |
| Fully materialized | 67/151 | Offline operator corpus |
| Partially materialized | 11/151 | Offline operator corpus |
| Not materialized | 73/151 | Offline operator corpus |
| Required fully materialized | 10/14 | Uploaded required products remain zero-row |
| Physical processed rows | 1,183,565 | Certified baseline; full audit not rerun on partial upload set |
| Registry-declared rows | 849,898 | Source-output bucket |
| Adjudicated derived rows | 212,930 | No source credit |
| Intermediate rows | 120,737 | No source credit |
| Unadjudicated orphan rows | 0 | Ownership bucket closure |
| Derived rows with unresolved lineage | 0 | All six producers confirmed |
| Live universe probe | Not run | `probe_ran=false` |

## Completed gates

1. PR #448 passed 17/17 triggered workflows and was squash-merged as `9e911203a05cf8f2e99c762161b7ec18de8cef73`.
2. PR #452 remains draft and unmerged; its input head passed 15/15 workflows.
3. The required upload set was hashed, schema-checked, and adjudicated without committing raw files.
4. COR3, HUD DRGR, cabilderos, and PRASA remain at zero positive rows and receive no materialization credit.
5. `entity_key` was added to the comparator stable-key contract.
6. The entity products share 104,280/104,280 normalized keys and are classified `OVERLAPPING_DERIVED_PRODUCTS`.
7. `data/staging/processed/entity_master.csv` lineage is resolved to `scripts/build_unified_master.py`.
8. Row ownership arithmetic remains closed with zero unadjudicated orphan rows.

## Remaining gates

1. Supply non-empty official COR3, HUD DRGR, cabilderos, and PRASA exports.
2. Compare against the actual enriched `pr_entity_profiles.csv` when supplied.
3. Re-run the complete 151-source materialization audit after valid ingestion.
4. Certify freshness and external-universe completeness separately from file presence.
5. Complete PR2.5/PR2.6 reconciliation before PR3 deduplication.
6. Validate production export and downstream federation consumers.

## Boundary

Local ownership and entity-spine comparison are certified. Required-source materialization and production readiness are not. No merge, direct write to `main`, live fetch, credential automation, raw-data commit, promotion, production activation, force push, or history rewrite is authorized by this roadmap.
