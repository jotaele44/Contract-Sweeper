# MoneySweep Wave 0 — Issue Reconciliation Ledger

**Date:** 2026-07-28  
**Repository anchor:** `c977eb3c3b1174b091f8bc84eecb6e05fb1e3900`

| Issue | Prior state | Wave 0 disposition | Evidence/action |
|---|---|---|---|
| #271 | Open epic with stale counts and #258 shown as active | **Open, reconciled** | Body rewritten around 151 total sources, 104/104 automatable readiness, 47 queued-excluded, current registry digest, #430 workflow dependency, and explicit #272–#307 child inventory. |
| #258 | Closed/completed | **Closed/completed preserved** | Added reconciliation comment; #271 now marks it completed on 2026-06-16. |
| #87 | Open deferred legacy concept | **Closed — not planned/superseded** | Scope is covered by #271, #286–#290, and the current registry; closure discards no source task. |
| #257 | Open | **Open, priority retained** | Required-source materialization remains an operational gate. |
| #259 | Open | **Open, denominator clarified** | Historical “56 unrun” title retained, but #271 now records 104 current automatable sources and separates structural readiness from execution. |
| #272–#307 | Open child tree | **Open unless individually adjudicated** | Epic now lists every child explicitly and requires API/overlap review before independent implementation. |

## Contradictions resolved

1. #258 is no longer represented as an active dependency.
2. The epic no longer uses the historical 133-source funnel as current truth.
3. Structural readiness (`104/104`) is no longer described as materialization completion.
4. The July 13 coverage snapshot is explicitly marked non-comparable to the current 151-source denominator.
5. Workflow repair PR #430 is now the first operational dependency for live materialization.

## Remaining issue-level risk

- Child issues may contain stale acquisition assumptions or branches even though their high-level scope remains valid.
- #257 and #259 titles preserve historical denominators; their bodies should be refreshed after a current-corpus materialization run rather than renamed speculatively now.
- No child issue closure was inferred solely from code existence; evidence and operator output remain required.
