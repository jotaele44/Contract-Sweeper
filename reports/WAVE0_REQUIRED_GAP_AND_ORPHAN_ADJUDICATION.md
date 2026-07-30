# MoneySweep Wave 0 — Required-Gap and Output-Ownership Adjudication

**Reconciled:** 2026-07-30  
**Target:** PR #448  
**Last certified v0.8 head:** `b1f088c98c8175298b856a5df8215c77fa933877`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`  
**Live fetch authorized:** No

## Required-source decision

The required-source result remains **10/14 fully materialized**. No source received new materialization credit.

| Source | Current evidence | Canonical outputs | Credit |
|---|---|---|---:|
| `cor3` | Public export surface verified; workbook bytes absent | `pr_cor3_projects.csv` | No |
| `hud_drgr_authorized` | Authorized export absent | `hud_drgr_activities.csv`, `hud_drgr_projects.csv` | No |
| `pr_cabilderos` | Department of Justice registry verified; full export absent | `pr_cabilderos.csv` | No |
| `prasa` | Official contract-export route verified; PRASA export absent | `pr_prasa_contracts.csv` | No |

HUD DRGR normalized Parquet products remain available for downstream analysis, but the two staging CSVs above are the registry materialization contract.

## Output ownership and lineage

The six positive-row files omitted from registry `expected_outputs` remain outside source-materialization credit. Their row bucket is adjudicated, but one producer lineage is unresolved.

| File | Rows | Classification | Producer status |
|---|---:|---|---|
| `entity_master.csv` | 104,280 | `DERIVED_OUTPUT` | `UNRESOLVED_STAGING_LINEAGE` |
| `pr_entity_profiles.csv` | 104,280 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` confirmed |
| `high_value_unresolved.csv` | 4,085 | `DERIVED_OUTPUT` | `scripts/parent_collapse.py` confirmed |
| `pr_report_builder_master.csv` | 238 | `DERIVED_OUTPUT` | `scripts/ingest_report_builder.py` confirmed |
| `pr_entity_gaps.csv` | 37 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` confirmed |
| `sam_entities.csv` | 10 | `DERIVED_OUTPUT` | `scripts/sam_uei_parent_lookup.py` confirmed |

`scripts/build_entity_master.py` is only a candidate for the first file: it declares `data/reference/entity_master.csv`, not `data/staging/processed/entity_master.csv`. The staging copy/materialization step must be identified before lineage is certified.

Equal row counts between the two 104,280-row products do not establish duplication. `scripts/compare_entity_products.py` must be run against the operator corpus.

## Row-accounting parity

```text
registry-declared rows                         849,898
adjudicated derived-output rows                212,930
pipeline-intermediate rows                     120,737
unadjudicated orphan rows                            0
                                               -------
total physical rows                          1,183,565
```

The unresolved 104,280-row lineage is a subset of the derived-output bucket; it is not an additional row bucket.

## Boundary

This record certifies local ownership buckets and arithmetic only. It does not certify source freshness, external-universe completeness, production export, downstream consumers, or promotion readiness.
