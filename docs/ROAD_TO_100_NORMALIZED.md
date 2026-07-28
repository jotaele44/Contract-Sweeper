# MoneySweep-PR — Normalized Road to 100 Status

**Governance version:** `road_to_100_normalization_v0_3`  
**Audit date:** 2026-07-28  
**Base commit:** `c977eb3c3b1174b091f8bc84eecb6e05fb1e3900`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Authoritative current denominator

The source denominator is controlled by `reports/materialization_readiness.json` and the live registry digest, not by older narrative counts.

| Registry metric | Current value |
|---|---:|
| Total sources | **151** |
| Automatable sources | **104** |
| Automatable ready | **104** |
| Excluded/queued sources | **47** |
| Manual exports | **40** |
| Genuine scraper stubs | **2** |
| Semantic duplicates | **3** |
| Deferred stubs | **2** |
| Broken producers | **0** |
| Registry digest | `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0` |

## Normalized scorecard

| Metric | Value | Evidence meaning |
|---|---:|---|
| Implemented scope | **75%** | Legacy engineering estimate from the detailed roadmap; code, contracts, producer wiring, and CI are substantially implemented. |
| CI-enforced maturity | **73%** | Legacy professional-maturity audit score; measures enforcement rather than live data coverage. |
| Automatable wiring readiness | **100% (104/104)** | Every current automatable registry entry is structurally ready. This does **not** mean it has been executed successfully. |
| Required-source materialization | **57.14% (8/14)** | Dated July 13 local-corpus snapshot. It remains useful evidence, but it is not a current-denominator rerun. |
| Current materialization coverage | **Not certified** | The latest committed local audit used 144 sources; the live registry now contains 151, and the gitignored operator corpus is unavailable in a clean checkout. |
| Production gate | **false** | No status or readiness normalization changes the production gate. |
| Evidence depth | **D2 — partial dated corpus** | Real materialized data exists, but current-denominator coverage, recurrent intake, and consumer certification remain incomplete. |

## Why the percentages differ

The figures measure different layers:

1. **75% implemented scope** asks whether the intended code and operational surfaces exist.
2. **73% CI maturity** asks whether automated gates keep those surfaces working.
3. **100% automatable readiness** asks whether the 104 automatable sources are structurally runnable.
4. **57.14% required materialization** asks whether the dated operator corpus held outputs for the 14 required sources.
5. **Current materialization coverage** cannot be asserted until the coverage audit is rerun against the 151-source registry and authoritative gitignored corpus.

These values must not be collapsed into a single completion percentage.

## Current critical path

1. Complete draft PR #430 and verify every workflow compiles.
2. Run the three repaired workflows in `preflight` mode only during review.
3. Provision the nine documented secret names without exposing values.
4. Execute bounded producer runs and preserve artifacts/manifests without promoting data automatically.
5. Rerun `scripts/audit_materialization_coverage.py` on the authoritative operator corpus.
6. Regenerate readiness, coverage, reconciliation, and status surfaces from one pinned commit.
7. Reconcile PR2.5/PR2.6 and complete PR3 entity deduplication.
8. Ingest the outstanding manual-source tranche and implement the two genuine scraper stubs.

## Certification rule

MoneySweep remains `NON_PRODUCTION_DIAGNOSTIC` until all of the following are true:

- workflow compilation and bounded-dispatch gates pass;
- source-count and registry-digest parity pass;
- coverage is rerun against the current 151-source denominator;
- required-source gaps are explicitly resolved or formally classified;
- the production export and downstream federation consumer validation pass.

The detailed historical and implementation narrative remains in `docs/ROAD_TO_100.md`. This document controls cross-repository comparisons after 2026-07-28.
