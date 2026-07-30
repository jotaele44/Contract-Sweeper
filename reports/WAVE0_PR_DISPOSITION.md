# MoneySweep Wave 0 — Pull Request Disposition Ledger

**Reconciled:** 2026-07-30  
**Current-main anchor:** `bd337fb092eb639cdb24b490bc90a8b07e9e51c4`  
**No PR was merged or auto-merged.**

## Current draft set

- **#444** — bounded live-fetch controls; full CI and three hosted preflight-only runs passed, all live jobs skipped.
- **#446** — dependency reconstruction; full CI passed.
- **#448** — certified local-corpus status, required-source evidence, output adjudication, entity comparator, and residual contract repairs.

PR #448 was synchronized to current `main` through a non-force two-parent commit. The last v0.8 head `b1f088c98c8175298b856a5df8215c77fa933877` passed all 16 triggered workflows, including Skills Validation.

## Certified evidence on #448

- **151 / 104 / 104 / 47** registry and readiness truth.
- **67 / 11 / 73** local materialization truth.
- **10/14** required sources fully materialized.
- **212,930** adjudicated derived rows and **120,737** intermediate rows.
- **0** unadjudicated orphan rows.
- **104,280** derived rows retain unresolved staging lineage.
- `probe_ran=false`; no live producer execution or data promotion.

## Preservation

No force push, history rewrite, merge, auto-merge, live fetch, data promotion, or credential disclosure occurred. PR #448 remains draft and production status remains `NON_PRODUCTION_DIAGNOSTIC`.
