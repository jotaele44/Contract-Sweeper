# MoneySweep Wave 0 — Final Risk Report

**Date:** 2026-07-28  
**Assessment boundary:** GitHub repository state. Local worktrees, stashes, ignored corpora, and unpushed branches are outside connector visibility.

| Risk | Severity | Current control | Residual action |
|---|---|---|---|
| Live-fetch workflows can execute through weak confirmation gates | Critical | Draft PR #444 adds exact tokens, explicit preflight/fetch separation, bounded inputs, and a shared validator. | Full CI plus three manual preflight-only dispatches. |
| Credentialed producer runs execute unintentionally | High | Preflight is the default; credentials are scoped only to live jobs; live jobs depend on validated inputs. | Review environment protections and retain operator receipts for live runs. |
| Materialization percentages use incompatible denominators | High | Current status records 151-source truth and formally noncertifies the 144-source audit as current coverage. | Rerun against the authoritative operator corpus and regenerate all surfaces from one commit. |
| Dependency updates import obsolete branch history | High | Draft PR #446 was reconstructed from current main with five changed files. | Require lock parity, full CI, and PyArrow compatibility tests. |
| PyArrow 25 changes data semantics | High | Draft-only; no data promotion. | Verify Parquet schema, timestamps, decimals, nullability, and round trips. |
| pywebview 6 drifts from federation templates | High | Excluded from #446 after the template-drift gate identified the ownership boundary. | Start a separate TheHub federation-template migration and validate all consumers. |
| Status rewrite erases dated evidence | Medium | The prior status remains addressable by immutable blob `b175df73deb6ecf5bbf0d0040b89ca75f5d1e10c`. | Retain the blob reference and do not treat its dated operational claims as current truth. |
| Epic state implies code readiness equals data coverage | Medium | #271 and current status explicitly separate 104/104 structural readiness from execution/materialization. | Refresh #257/#259 only after a current-corpus run. |
| Main advances during review | Medium | All current Wave 0 successor branches start at `34ef3b9`. | Recheck ancestry and overlap before any further edit or review transition. |
| New mainline data changes alter production semantics | High | Wave 0 does not modify production data or change the production gate. | Audit those mainline changes independently; do not attribute them to Wave 0. |
| Local-only work conflicts with GitHub state | Unknown | No connector-side control is possible. | Operator runs `git status -sb`, reviews ignored data, and compares local branch SHAs before cleanup. |

## Certification state

Wave 0 restores control-plane integrity and denominator honesty. It is **not production certification**. Production status remains `NON_PRODUCTION_DIAGNOSTIC` until:

1. #444 is green and three preflight-only manual dispatches succeed.
2. #446 is green, including lockfile parity and data-format compatibility.
3. A 151-source coverage audit runs against the authoritative operator corpus.
4. Required-source gaps are resolved or formally classified.
5. PR2.5/PR2.6 reconciliation and PR3 deduplication pass.
6. Production export and downstream federation-consumer validation pass.

## Confidence

- Workflow root-cause and remediation: **high**.
- Registry denominator and digest: **high**.
- Dated materialization snapshot: **high as historical evidence; low as current coverage**.
- Dependency compatibility: **medium pending successor CI**.
- Local worktree completeness: **unknown**.
