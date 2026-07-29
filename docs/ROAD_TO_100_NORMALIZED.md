# MoneySweep — Normalized Road to 100

**Generated:** 2026-07-29  
**Base:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`  
**Certified audit code:** `1dc726893a3a15879fe828aeeeb46ddd8807c870`  
**Status PR:** #448, clean successor to closed/unmerged #447  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Current denominator and certified local corpus

| Measure | Current value | Certification |
|---|---:|---|
| Registry sources | 151 | Verified from `reports/materialization_readiness.json` |
| Automatable sources | 104 | Verified |
| Automatable structurally ready | 104/104 | Wiring readiness only; not proof of current external-source freshness |
| Queued/excluded | 47 | Verified: 40 manual, 2 scraper, 3 semantic duplicates, 2 deferred |
| Registry digest | `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0` | Parity pass |
| Fully materialized | 67/151 | Certified offline operator corpus |
| Partially materialized | 11/151 | Certified offline operator corpus |
| Not materialized | 73/151 | Certified offline operator corpus |
| Sources with positive rows | 64/151 | Row-materiality axis; independent of output-presence status |
| Required-source materialization | 10/14 | 71.43%; four required gaps remain |
| Operator audit bundle | `2a37bf4c49f5e4d267ca4cbdc8366c718efc1738de607cdbe3cbbbd3ec8b9f85` | Eight-file bundle; internal payload hashes pass |
| Live universe probe | Not run | `probe_ran=false`; no live fetch authorized |

## Normalized maturity

| Dimension | Value | Interpretation |
|---|---:|---|
| Implemented scope | 75% | Legacy engineering estimate retained for continuity |
| CI-enforced maturity | 73% | Legacy engineering estimate; status-refresh CI must remain gating |
| Automatable wiring | 100% | 104/104 producers structurally ready |
| Fully materialized | 44.37% | 67/151 on the current operator corpus |
| Fully or partially materialized | 51.66% | 78/151 on the current operator corpus |
| Required materialization | 71.43% | 10/14 required sources fully materialized |
| Evidence depth | D3 | Current-denominator offline operator corpus certified |
| Production gate | false | No promotion authorization |

## Required-source closure

The four required sources below remain unresolved:

- `cor3`
- `hud_drgr_authorized`
- `pr_cabilderos`
- `prasa`

Required-source remediation must distinguish missing outputs, schema/provenance defects, inaccessible external inputs, and intentionally deferred acquisition. A source must not be promoted merely because a file exists.

## Registry-drift and file-accounting closure

The processed corpus contains **1,183,565** physical rows across **120** CSV files:

- **849,898** rows are claimed by registry outputs.
- **212,930** rows across six files are currently orphaned from registry ownership.
- **120,737** rows across eleven files are classified as non-terminal intermediates.

Priority orphan adjudication:

| File | Rows |
|---|---:|
| `entity_master.csv` | 104,280 |
| `pr_entity_profiles.csv` | 104,280 |
| `high_value_unresolved.csv` | 4,085 |
| `pr_report_builder_master.csv` | 238 |
| `pr_entity_gaps.csv` | 37 |
| `sam_entities.csv` | 10 |

## Completed Wave 0 gates

1. PR #444 full CI passed.
2. Three hosted `mode=preflight` dispatches passed; all live jobs were skipped.
3. PR #446 full CI passed.
4. Clean status input head `1dc726893a3a15879fe828aeeeb46ddd8807c870` passed its full CI suite.
5. The authoritative 151-source offline corpus audit passed with digest and count parity.
6. PR #447 was closed unmerged after its restored connector-side write; #448 preserves the clean certified input head without history rewrite.

## Remaining path to production eligibility

1. Resolve or formally classify the four required-source gaps.
2. Reconcile six orphan files with registry ownership, derived-output status, or explicit exclusion.
3. Assess freshness and external-universe completeness separately from local file presence.
4. Complete PR2.5/PR2.6 reconciliation before PR3 entity deduplication.
5. Validate production export behavior and downstream federation consumers.
6. Require full CI, status parity, registry-digest parity, and review approval on the refreshed #448 head.

## Boundary

The current 151-source **offline local-corpus accounting is certified**. External-universe completeness, source freshness, production export, and downstream federation-consumer behavior are **not certified**. Structural readiness and local output presence do not authorize a live fetch, data promotion, merge, or production-status change.
