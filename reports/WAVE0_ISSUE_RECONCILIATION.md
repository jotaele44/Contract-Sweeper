# MoneySweep Wave 0 — Issue Reconciliation Ledger

**Reconciled:** 2026-07-30  
**Current base incorporated:** `bd337fb092eb639cdb24b490bc90a8b07e9e51c4`  
**Status PR:** #448, draft and unmerged  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

| Issue | State | Reconciliation |
|---|---|---|
| #271 | Open | P0 corpus accounting and access-route evidence are complete. Required exports, entity comparison, staging lineage, freshness, export, and downstream gates remain. |
| #258 | Closed — completed | Preserved as completed; not an active blocker. |
| #87 | Closed — superseded | Covered by #271, child source tasks, and the current registry. |
| #272–#307 | Open unless separately closed | Reprioritize from source-specific evidence; epic inclusion does not authorize execution. |

## Current truth

- Registry: **151 total / 104 automatable / 104 ready / 47 queued-excluded**.
- Materialization: **67 full / 11 partial / 73 absent**.
- Required sources: **10/14 fully materialized**.
- Row ownership: **849,898 registry / 212,930 derived / 120,737 intermediate / 0 unadjudicated orphan**.
- One derived artifact, `entity_master.csv` (**104,280 rows**), has unresolved staging lineage.
- Live universe probe: **not run**.

No issue-state update authorizes merge, promotion, live fetch, credential disclosure, force push, or automatic child closure.
