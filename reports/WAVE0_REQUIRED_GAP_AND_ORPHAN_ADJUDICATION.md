# MoneySweep Wave 0 — Required-Gap and Output-Ownership Adjudication

**Reconciled:** 2026-07-30  
**Target:** draft PR #452  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`  
**Live fetch authorized:** No

## Required-source decision

The required-source result remains **10/14 fully materialized**. All four source-specific uploads were inspected, but none contains positive rows.

| Source | Supplied evidence | Canonical requirement | Credit |
|---|---|---|---:|
| `cor3` | Header-only `pr_cor3_projects.csv` | Non-empty official COR3 project rows | No |
| `hud_drgr_authorized` | Two zero-row Parquets | Non-empty `hud_drgr_activities.csv` and `hud_drgr_projects.csv` | No |
| `pr_cabilderos` | Header-only `pr_cabilderos.csv` | Non-empty Justice registry export | No |
| `prasa` | Header-only `pr_prasa_contracts(1).csv` | Non-empty official PRASA contract export | No |

`pr_hud_hcv.csv` is not a DRGR export. Federal awards that mention PRASA and PREPA contract records are not substitutes for the required PRASA source contract.

## Output ownership and lineage

All six positive-row non-registry products remain derived outputs and receive no source-materialization credit. All six producer lineages are now confirmed.

| File | Rows | Classification | Producer |
|---|---:|---|---|
| `entity_master.csv` | 104,280 | `DERIVED_OUTPUT` | `scripts/build_unified_master.py` |
| `pr_entity_profiles.csv` | 104,280 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` |
| `high_value_unresolved.csv` | 4,085 | `DERIVED_OUTPUT` | `scripts/parent_collapse.py` |
| `pr_report_builder_master.csv` | 238 | `DERIVED_OUTPUT` | `scripts/ingest_report_builder.py` |
| `pr_entity_gaps.csv` | 37 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` |
| `sam_entities.csv` | 10 | `DERIVED_OUTPUT` | `scripts/sam_uei_parent_lookup.py` |

The earlier lineage conflict was caused by checking `scripts/build_entity_master.py`, which produces a different top-form reference table. The staging artifact is explicitly written by `scripts/build_unified_master.py`. The supplied file matches the reconstructed awards aggregation on all 104,280 entity keys and seven non-numeric aggregate fields.

## Entity-product comparison

The comparator now recognizes `entity_key`, the actual stable key in the staging Entity Master.

```text
left stable key               entity_key
right stable key              normalized_name
left unique keys              104,280
right unique keys             104,280
intersection                  104,280
union                         104,280
stable-key overlap            100%
Jaccard                       100%
shared projection overlap     100%
classification                OVERLAPPING_DERIVED_PRODUCTS
```

The files are not byte-identical and are not semantic duplicates because their schemas serve different analytical purposes. The right-side profile was reconstructed from the supplied awards master; the actual enriched profile and supplementary 990, CMS, and FDIC inputs were not supplied.

## Row-accounting parity

```text
registry-declared rows                         849,898
adjudicated derived-output rows                212,930
pipeline-intermediate rows                     120,737
unadjudicated orphan rows                            0
                                               -------
total physical rows                          1,183,565
```

Unresolved derived-lineage rows are now **0**. The certified row buckets and source-materialization counts are unchanged.

## Boundary

This record certifies local ownership buckets, derived lineage, and the common entity awards spine. It does not certify required-source freshness, external-universe completeness, the absent enrichment columns, production export, downstream consumers, or promotion readiness.
