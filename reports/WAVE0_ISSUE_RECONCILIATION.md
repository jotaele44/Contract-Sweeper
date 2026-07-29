# MoneySweep Wave 0 — Issue Reconciliation Ledger

**Date:** 2026-07-29  
**Base:** `34ef3b9352493d0b6ba4eb821d7ea544bec0933b`  
**Certified audit input:** `1dc726893a3a15879fe828aeeeb46ddd8807c870`  
**Status PR:** #448, clean successor to closed/unmerged #447  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

| Issue | State | Reconciliation |
|---|---|---|
| #271 | Open — P0 corpus gate complete | Current truth is 151 sources, 104/104 automatable wiring, 67 fully materialized, 11 partially materialized, 73 not materialized, and 10/14 required sources fully materialized. The epic remains open for required-source, orphan, freshness, export, and downstream-consumer work. |
| #258 | Closed — completed | Preserved as completed on 2026-06-16. It is not an active blocker and must not be reopened through epic checkbox drift. |
| #87 | Closed — not planned/superseded | Closed on 2026-07-28 because the salvaged Tier-0 fetcher concept is covered by #271, its child source tasks, and the current source registry. |
| #272–#307 | Open unless separately closed | Remain candidate child tasks. Reprioritize against the certified corpus, required gaps, overlap, API feasibility, and evidence value. Epic inclusion does not prove missing code or authorize execution. |

## Current source truth

- Total sources: **151**
- Automatable: **104**
- Structurally ready: **104/104**
- Queued/excluded: **47**
- Fully materialized: **67**
- Partially materialized: **11**
- Not materialized: **73**
- Required fully materialized: **10/14**
- Registry digest: `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0`
- Operator bundle SHA-256: `2a37bf4c49f5e4d267ca4cbdc8366c718efc1738de607cdbe3cbbbd3ec8b9f85`
- Live universe probe: **not run**

## Required-source follow-up

| Source | Certified local status | Issue action |
|---|---|---|
| `cor3` | Partially materialized; zero positive rows in declared output accounting | Verify expected output, source access, schema, provenance, and blocker ownership. |
| `hud_drgr_authorized` | Not materialized | Establish authoritative delivery path and acceptance test. |
| `pr_cabilderos` | Partially materialized; zero positive rows in declared output accounting | Reconcile producer/output path and evidence provenance. |
| `prasa` | Partially materialized; zero positive rows in declared output accounting | Reconcile expected output with current PRASA corpus and parser coverage. |

## Registry-drift follow-up

Six orphan files contain **212,930** rows. Child work must assign each file to a registry source, classify it as a derived output, or explicitly exclude it. Eleven intermediate files containing **120,737** rows remain correctly separated from terminal source-output accounting.

## Interpretation

`104/104 ready` means producer wiring passes structural readiness checks. `67/151 fully materialized` means declared local outputs satisfy the audit's presence/status rules. Neither metric certifies freshness, external-universe completeness, production export, or downstream federation behavior.

No issue-state reconciliation authorizes a merge, production promotion, live fetch, credential disclosure, or automatic closure of child tasks.
