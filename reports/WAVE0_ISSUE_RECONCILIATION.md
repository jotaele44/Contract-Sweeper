# MoneySweep Wave 0 — Issue Reconciliation Ledger

**Date:** 2026-07-28  
**Base:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`

| Issue | State | Reconciliation |
|---|---|---|
| #271 | Open | Epic body rewritten around the verified 151-source denominator, 104/104 structural readiness, 47 queued/excluded sources, and the workflow-control prerequisite now represented by draft PR #444. |
| #258 | Closed — completed | Preserved as completed on 2026-06-16. It is not an active blocker and must not be reopened through epic checkbox drift. |
| #87 | Closed — not planned/superseded | Closed on 2026-07-28 because the salvaged Tier-0 fetcher concept is covered by #271, its child source tasks, and the current source registry. |
| #272–#307 | Open unless separately closed | Remain candidate child tasks. They require reprioritization by API feasibility, overlap, and evidence value; epic inclusion does not prove missing code or authorize implementation. |

## Current source truth

- Total sources: **151**
- Automatable: **104**
- Structurally ready: **104/104**
- Queued/excluded: **47**
- Registry digest: `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0`

## Interpretation

`104/104 ready` means the producer wiring passes structural readiness checks. It does not mean the sources have been executed against the authoritative operator corpus or that current materialization is complete.

No issue-state reconciliation authorizes a merge, production promotion, live fetch, credential disclosure, or automatic closure of child tasks.
