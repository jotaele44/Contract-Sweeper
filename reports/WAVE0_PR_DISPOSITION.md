# MoneySweep Wave 0 — Pull Request Disposition Ledger

**Date:** 2026-07-28  
**No PR was merged or auto-merged.**

| Original PR | Finding | Replacement/disposition |
|---|---|---|
| #329 — LegislaPR registry | Branch drifted to 1,382 files, but the intended registry overlay, schema extension, discovery documentation, probes, ingestion code, and canonical crosswalk are already present on current `main`. | **No-code supersession.** Close as obsolete after documenting the current-main paths; do not create a duplicate replacement. |
| #346 — offline Federation operator scaffold | Branch drifted to 1,443 files. The generic scaffold would duplicate MoneySweep's existing dashboard offline export and federation-export workflow and reports placeholder readiness rather than native evidence. | **No-code supersession.** Close as obsolete; any future operator work must extend the native export contract in a fresh scoped PR. |
| #350 — openpyxl | Stale dependency branch; current lock already selects `openpyxl==3.1.5`. | **Replaced by draft PR #431**, which aligns the declared minimum on current `main`. |
| #377 — Ruff | Stale dependency branch. | **Replaced by draft PR #431** with synchronized pre-commit revision. |
| #378 — mypy | Stale dependency branch and major tooling change. | **Replaced by draft PR #431**; remains gated on full mypy/pre-commit evidence. |
| #382 — PyArrow | Stale dependency branch and major data-format/runtime change. | **Replaced by draft PR #431**; requires lock regeneration and Parquet compatibility tests. |
| #383 — pywebview | Stale dependency branch and major desktop runtime change. | **Replaced by draft PR #431**; requires macOS and Windows smoke evidence. |
| #413 — normalized ROAD_TO_100 metrics | Documentation was based on stale/mixed denominators. | **Superseded by the Wave 0 status-reconciliation draft**, which separates 151-source readiness from the dated 144-source coverage snapshot. |

## New draft PRs

- **#430 — workflow repair:** restores compilation, bounded preflight/fetch separation, input validation, and workflow static checks.
- **#431 — dependency refresh:** reconstructs five stale dependency intentions from current `main` with six reviewable files.
- **Wave 0 status-reconciliation draft:** archives the old status ledger, regenerates current status, adds normalized ROAD_TO_100 metrics, and records issue/PR/risk ledgers.

## Preservation record

- No force push.
- No history rewrite.
- No merge or auto-merge.
- No data promotion.
- No secret value read or disclosed.
- Stale intent was either reconstructed from current `main` or formally superseded; no 1,000-file legacy branch was rebased wholesale.
