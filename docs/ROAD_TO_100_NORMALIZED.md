# MoneySweep — Normalized Road to 100

**Generated:** 2026-07-28  
**Base:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Current denominator

| Measure | Current value | Certification |
|---|---:|---|
| Registry sources | 151 | Verified from `reports/materialization_readiness.json` |
| Automatable sources | 104 | Verified |
| Automatable structurally ready | 104/104 | Verified; this is wiring readiness, not fetched data |
| Queued/excluded | 47 | Verified: 40 manual, 2 scraper, 3 semantic duplicates, 2 deferred |
| Registry digest | `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0` | Verified |
| Current overall materialization | Not certified | The available audit uses a 144-source denominator |
| Required-source materialization | 8/14 | Dated July 13 operator-corpus snapshot only |

## Normalized maturity

| Dimension | Value | Interpretation |
|---|---:|---|
| Implemented scope | 75% | Legacy engineering estimate; retained for continuity |
| CI-enforced maturity | 73% | Legacy engineering estimate; current CI remains gating |
| Automatable wiring | 100% | 104/104 producers structurally ready |
| Required materialization | 57.14% | Dated snapshot, not a current-denominator result |
| Evidence depth | D2 | Partial, dated operator corpus |
| Production gate | false | No promotion authorization |

## Path to certified coverage

1. Complete draft PR #444 and its preflight-only manual dispatch checks.
2. Execute the 104 structurally ready sources through bounded operator runs.
3. Run `scripts/audit_materialization_coverage.py` against the authoritative gitignored corpus.
4. Regenerate readiness, coverage, current status, and Road-to-100 artifacts from one commit.
5. Require source-count and registry-digest parity across every committed status surface.
6. Resolve or formally classify every required-source gap.
7. Complete downstream federation-consumer validation before any production-status change.

## Boundary

**Not certified:** structural readiness is not equivalent to materialized data coverage. No percentage based on the 144-source July snapshot may be presented as current coverage for the 151-source registry.
