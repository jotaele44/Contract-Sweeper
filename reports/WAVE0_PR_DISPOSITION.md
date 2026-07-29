# MoneySweep Wave 0 — Pull Request Disposition Ledger

**Date:** 2026-07-29  
**Current-main anchor:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`  
**Certified audit input:** `1dc726893a3a15879fe828aeeeb46ddd8807c870`  
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
| #413 — Road-to-100 normalization | Used stale and mixed denominators. | Closed; status scope moved through #447 and is now maintained by clean successor #448. |
| #430 — workflow repair v0.1 | Functionally validated, then diverged by 51 mainline commits. | Closed; superseded by fresh-current-main draft PR #444. |
| #431 — dependency refresh v0.1 | Fully green, then diverged from current main. | Closed; superseded by fresh-current-main draft PR #446. |
| #432 — status reconciliation v0.1 | Fully green, then diverged from current main and contained outdated PR references. | Closed; superseded by #447 and then clean successor #448. |
| #447 — status reconciliation v0.2 | Certified head was followed by a connector-side placeholder write and immediate restoration, creating two non-substantive commits. | Closed unmerged; clean #448 starts at exact pre-write certified head `1dc726893a3a15879fe828aeeeb46ddd8807c870`. |

## Current draft set

- **#444** — bounded live-fetch workflow controls; full CI and three hosted preflight-only dispatches passed, with all live jobs skipped.
- **#446** — Python tooling and PyArrow/openpyxl dependency reconstruction; full CI passed.
- **#448** — current status, certified 151-source operator-corpus accounting, normalized Road-to-100, issue reconciliation, PR disposition, and risk report.

## Certified evidence recorded on #448

- Registry: **151 total / 104 automatable / 104 ready / 47 queued-excluded**.
- Materialization: **67 fully / 11 partially / 73 not materialized**.
- Required sources: **10/14 fully materialized**.
- Registry drift: **212,930 orphan rows / 120,737 intermediate rows**.
- Operator evidence bundle SHA-256: `2a37bf4c49f5e4d267ca4cbdc8366c718efc1738de607cdbe3cbbbd3ec8b9f85`.
- Audit boundary: `probe_ran=false`; no live fetch, universe probe, or data promotion.

## Preservation record

- No force push or history rewrite.
- No merge or auto-merge.
- No live fetch or public-universe probe.
- No data promotion by Wave 0 changes.
- No credential value read or disclosed.
- No contaminated legacy branch was rebased wholesale.
- PR #448 remains draft and `NON_PRODUCTION_DIAGNOSTIC` remains unchanged.
