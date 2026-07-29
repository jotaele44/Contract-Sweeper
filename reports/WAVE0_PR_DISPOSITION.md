# MoneySweep Wave 0 — Pull Request Disposition Ledger

**Date:** 2026-07-28  
**Current-main anchor:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`  
**No PR was merged or auto-merged.**

| Original PR | Finding | Final disposition |
|---|---|---|
| #329 — LegislaPR registry | Drifted to 1,382 files; intended registry, schema, probes, ingestion, and crosswalk already exist on main. | Closed as no-code supersession. |
| #346 — generic offline operator | Drifted to 1,443 files and duplicated MoneySweep-native export behavior. | Closed as no-code supersession. |
| #350 — openpyxl | Obsolete dependency branch. | Reconstructed on current main in draft PR #446. |
| #377 — Ruff | Obsolete dependency branch. | Reconstructed on current main in draft PR #446. |
| #378 — mypy | Obsolete dependency branch. | Reconstructed on current main in draft PR #446. |
| #382 — PyArrow | Obsolete dependency branch. | Reconstructed on current main in draft PR #446. |
| #383 — pywebview | Repository-only change would drift from TheHub's rendered federation template. | Closed; migration deferred to a federation-wide TheHub template vector. |
| #413 — Road-to-100 normalization | Used stale/mixed denominators. | Closed; replaced by this current-main status-reconciliation branch. |
| #430 — workflow repair v0.1 | Functionally validated, then diverged by 51 mainline commits. | Superseded by fresh-current-main draft PR #444. |
| #431 — dependency refresh v0.1 | Fully green, then diverged from current main. | Superseded by fresh-current-main draft PR #446. |
| #432 — status reconciliation v0.1 | Fully green, then diverged from current main and contained outdated PR references. | Superseded by this regenerated current-main status draft. |

## Current draft set

- **#444** — bounded live-fetch workflow controls and static validation.
- **#446** — Python tooling and PyArrow/openpyxl dependency reconstruction.
- **Current status branch** — `agent/moneysweep-wave0-status-reconciliation-v0-2`.

## Preservation record

- No force push or history rewrite.
- No merge or auto-merge.
- No live workflow dispatch.
- No data promotion by Wave 0 changes.
- No credential value read or disclosed.
- No contaminated legacy branch was rebased wholesale.
