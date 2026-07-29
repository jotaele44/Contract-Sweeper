# MoneySweep Wave 0 — Required Gaps and Processed-Output Ownership

**Date:** 2026-07-29  
**Target:** PR #448 at certified-status head `33c123f1c3826f1b27b67172dd3227d81353af47`  
**Operator audit:** `MONEYSWEEP_WAVE0_OPERATOR_AUDIT.zip`  
**Bundle SHA-256:** `2a37bf4c49f5e4d267ca4cbdc8366c718efc1738de607cdbe3cbbbd3ec8b9f85`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Decision

The six files previously reported as orphans are now classified for accounting purposes. None is promoted into registry source-output coverage. The four required-source gaps remain unmaterialized and are formally classified by acquisition boundary because this vector authorizes neither a live fetch nor substitution of synthetic data.

## Required-source adjudication

| Source | Audit status | Required input | v0.7 disposition |
|---|---|---|---|
| `cor3` | Partially materialized; `pr_cor3_projects.csv` absent | Authorized live acquisition or an operator-supplied official capture | `LIVE_ACQUISITION_REQUIRED`; deferred because no live fetch is authorized |
| `hud_drgr_authorized` | Not materialized; two declared outputs absent | Operator-supplied authorized HUD DRGR export | `MANUAL_EXPORT_REQUIRED`; no substitute permitted |
| `pr_cabilderos` | Partially materialized; declared output absent | Official/manual lobbying export | `MANUAL_EXPORT_REQUIRED` |
| `prasa` | Partially materialized; declared output absent | Official PRASA contracts export with schema and provenance validation | `MANUAL_EXPORT_REQUIRED` |

Required-source materialization remains **10/14**. Formal classification closes ambiguity; it does not claim data acquisition.

## Processed-output ownership

| File | Rows | Classification | Owner / producer | Accounting treatment |
|---|---:|---|---|---|
| `entity_master.csv` | 104,280 | `INTENTIONAL_EXCLUSION` | Legacy entity pipeline; exact producer unresolved | Excluded from source-output accounting pending provenance closure |
| `pr_entity_profiles.csv` | 104,280 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` | Terminal analytical output; not a source row set |
| `high_value_unresolved.csv` | 4,085 | `DERIVED_OUTPUT` | `scripts/parent_collapse.py` | Manual-review analytical queue |
| `pr_report_builder_master.csv` | 238 | `DERIVED_OUTPUT` | `scripts/ingest_report_builder.py` | Reporting-layer master |
| `pr_entity_gaps.csv` | 37 | `DERIVED_OUTPUT` | `scripts/analyze_entity_profiles.py` | Derived unmatched-entity queue |
| `sam_entities.csv` | 10 | `DERIVED_OUTPUT` | `scripts/sam_uei_parent_lookup.py` | Derived SAM entity enrichment |

No file is classified as `DUPLICATE` because the certification evidence establishes equal row counts for some files, not record-level or byte-level equivalence.

## Row accounting

| Bucket | Rows |
|---|---:|
| Registry source outputs | 849,898 |
| Non-terminal intermediates | 120,737 |
| Derived outputs | 108,650 |
| Intentional exclusions | 104,280 |
| Duplicates | 0 |
| Unclassified orphans | 0 |
| **Physical total** | **1,183,565** |

The buckets reconcile exactly and are mutually exclusive. Derived and intentionally excluded rows remain outside the source-materialization numerator, preventing double counting.

## Provenance and schema boundary

- Repository producer paths are recorded where directly supported by existing scripts.
- `entity_master.csv` remains intentionally excluded because the exact producer for the operator-corpus copy is unresolved.
- This adjudication does not validate the row schemas of gitignored corpus files in a clean GitHub checkout.
- The prior operator audit remains the authority for row counts.
- Freshness and external-universe completeness remain uncertified.
- Any future reclassification requires a new operator-corpus run and row-total parity check.

## Remaining gates

1. Obtain explicit authorization before a live COR3 acquisition.
2. Supply official/manual exports for HUD DRGR, cabilderos, and PRASA.
3. Resolve the producer and lineage of the operator-corpus `entity_master.csv`.
4. Re-run the offline audit after materialization or ownership changes.
5. Complete production export and downstream federation-consumer validation.

No merge, auto-merge, live fetch, data promotion, force push, or history rewrite is authorized by this report.
