# Road to 100 — normalized federation score

**Audit date:** 2026-08-04  
**Scoring model:** code completeness 20%; main-branch availability 15%; CI enforcement 15%; data materialization 15%; operator verification 15%; GUI completeness 10%; federation readiness 10%.

## Current normalized score: 61.70 / 100

| Dimension | Weight | Score | Weighted |
|---|---:|---:|---:|
| Code completeness | 20 | 78 | 15.60 |
| Main-branch availability | 15 | 72 | 10.80 |
| CI enforcement | 15 | 82 | 12.30 |
| Data materialization | 15 | 45 | 6.75 |
| Operator verification | 15 | 35 | 5.25 |
| GUI completeness | 10 | 70 | 7.00 |
| Federation readiness | 10 | 40 | 4.00 |

This repository remains `NON_PRODUCTION_DIAGNOSTIC`. The normalized score does not award production credit for registered sources, schemas or resumable producers until source bytes, lineage and operator receipts exist.

## State reconciliation

- The Wave 0 architecture, source registry, ingestion framework, desktop/frontend improvements and release guard are substantially implemented.
- Required sources remain incomplete: COR3, HUD DRGR, cabilderos and PRASA.
- PR #453 is the O&M contract-universe candidate; its OCPR materialization and completeness gates remain unresolved.
- PR #457 is the isolated-clone candidate.
- PR #458 is a release-safety guard and should land before any desktop tag can be considered.
- PR #459 is rescued audit/staging state, not certified production data.
- FEC Schedule E and related reconciliation remain operator-run work.
- Entity-master lineage, source freshness and external-universe completeness remain unresolved.

## Priority exit sequence

1. Materialize the four required source exports with exact receipts.
2. Complete OCPR O&M materialization and 78-municipality/public-corporation accounting.
3. Complete FEC Schedule E/B reconciliation and preserve unresolved-row evidence.
4. Resolve entity-master lineage and rerun the 151-source audit.
5. Adjudicate rescued PR #459 without promoting deletions or outputs by assumption.
6. Land release and isolation guards.
7. Recompute production status only after real-data R5 gates and downstream federation validation pass.

## Machine-readable authority

See `docs/unfinished_implementation_ledger.v1.json`. New analytical verticals do not outrank required-source closure.
