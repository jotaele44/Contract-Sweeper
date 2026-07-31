# MoneySweep — Road to 100

**Reconciled:** 2026-07-30  
**Merged PR:** #448  
**Active draft PR:** #452  
**Main:** `9e911203a05cf8f2e99c762161b7ec18de8cef73`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Current control plane

PR #448 passed **17/17 triggered workflows** and was squash-merged with expected-head protection. PR #452 remains draft and unmerged. Its input head `d1d0dcb24c03760c3e67f83297f2de22d09cf3ea` passed **15/15 triggered workflows** before this evidence update.

No live acquisition, credential automation, raw-data commit, data promotion, or production activation was authorized.

## Certified baseline

| Control | Result |
|---|---:|
| Registry sources | 151 |
| Automatable / structurally ready | 104 / 104 |
| Queued or excluded | 47 |
| Fully / partially / not materialized | 67 / 11 / 73 |
| Required fully materialized | 10 / 14 |
| Registry source-ID digest | `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0` |
| Physical processed rows | 1,183,565 |
| Registry-declared rows | 849,898 |
| Adjudicated derived rows | 212,930 |
| Pipeline intermediates | 120,737 |
| Unadjudicated orphan rows | 0 |
| Derived rows with unresolved lineage | 0 |
| Live universe probe | Not run |

The complete 151-source audit was not rerun because the supplied upload set is only a partial corpus. Baseline source counts remain certified and unchanged.

## Required-export upload adjudication

| Source | Supplied evidence | Result |
|---|---|---|
| `cor3` | `pr_cor3_projects.csv` | Header-only, 0 rows; no credit |
| `hud_drgr_authorized` | Two HUD DRGR Parquets | Both 0 rows and not registry staging CSVs; no credit |
| `pr_cabilderos` | `pr_cabilderos.csv` | Header-only, 0 rows; no credit |
| `prasa` | `pr_prasa_contracts(1).csv` | Header-only, 0 rows; no credit |

`pr_hud_hcv.csv` is a Housing Choice Voucher summary, not a DRGR export. Federal awards mentioning PRASA and PREPA contract records are not substitutes for an official PRASA contract export.

Evidence is recorded in `reports/WAVE0_REQUIRED_EXPORT_INGESTION_RECEIPT_2026-07-30.json`.

## Entity-product comparison

The uploaded `entity_master(2).csv` contains 104,280 valid rows. The uploaded 453,352-row awards master reproducibly generated a 104,280-row entity-profile spine using the `analyze_entity_profiles.py` normalization and aggregation contract.

A comparator defect was corrected: staging `entity_master.csv` uses `entity_key`, but `entity_key` was absent from the stable-key candidate list. With the proper keys:

- left stable key: `entity_key`;
- right stable key: `normalized_name`;
- unique keys: 104,280 on each side;
- intersection: 104,280;
- stable-key overlap and Jaccard: 100%;
- shared `award_count` and `fiscal_year_range` row projection: 100%;
- classification: `OVERLAPPING_DERIVED_PRODUCTS`;
- not byte-identical and not semantic duplicates because the schemas serve different purposes.

The actual enriched `pr_entity_profiles.csv` and its 990, CMS, and FDIC supplementary inputs were not supplied, so the comparison is certified for the common awards spine rather than every enrichment column.

## Lineage resolution

`data/staging/processed/entity_master.csv` is produced by `scripts/build_unified_master.py`, not `scripts/build_entity_master.py`. The uploaded artifact matches the reconstructed awards aggregation on all 104,280 entity keys and seven non-numeric aggregate fields. All six derived-output producer lineages are now confirmed.

## Gates remaining before production consideration

1. Supply non-empty COR3, authorized HUD DRGR, Department of Justice cabilderos, and PRASA exports.
2. Run the comparison against the actual enriched `pr_entity_profiles.csv` when supplied.
3. Re-run the complete 151-source audit after valid source ingestion.
4. Certify source freshness and external-universe completeness.
5. Complete PR2.5/PR2.6 reconciliation before PR3 deduplication.
6. Validate production export and downstream federation consumers.
7. Keep promotion guards closed until every blocker is cleared.

## Preservation

PR #452 remains draft and unmerged. This roadmap does not authorize an additional merge, direct write to `main`, live fetch, credential automation, raw data commit, data promotion, production activation, force push, or history rewrite.
