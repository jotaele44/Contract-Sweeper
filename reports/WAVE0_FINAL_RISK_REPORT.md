# MoneySweep Wave 0 — Final Risk Report

**Date:** 2026-07-28  
**Assessment boundary:** repository and GitHub state only; local Mac worktrees, stashes, ignored data, and unpushed branches are outside connector visibility.

## Risk matrix

| Risk | Severity | Current control | Residual action |
|---|---|---|---|
| Live-fetch workflows fail before jobs start | **Critical** | Draft PR #430 removes unsupported expressions, moves credentials out of `if:`, and adds static validation. | Require full CI and three bounded `preflight` dispatches before any live fetch. |
| Credentialed producer runs execute unintentionally | **High** | `preflight` is the default; live mode requires exact confirmation tokens; source/family/days are bounded. | Review repository environment protections and require operator receipts for every live run. |
| Coverage percentages use incompatible denominators | **High** | Current status records 151-source truth and formally noncertifies the dated 144-source audit as current coverage. | Rerun coverage on the authoritative operator corpus and regenerate all surfaces from one commit. |
| Dependency updates import obsolete branch history | **High** | Draft PR #431 reconstructs five files directly from current main. | Regenerate the lockfile, run the full Python compatibility matrix, and split updates if failures interact. |
| PyArrow 25 changes data semantics | **High** | Draft-only; no data promotion. | Run Parquet schema, timestamp, decimal, nullability, and cross-version round-trip tests. |
| pywebview 6 changes desktop behavior | **High** | MoneySweep-only change removed after the canonical-template gate failed. | Start any migration in TheHub's federation template, then render and smoke-test every desktop consumer on macOS and Windows. |
| Status normalization erases historical evidence | **Medium** | Prior `reports/current_status.json` is archived byte-for-byte under `reports/history/`. | Keep dated snapshots immutable and exclude them from current-count assertions. |
| Issue epic implies completed code equals materialized data | **Medium** | #271 now separates 104/104 structural readiness from execution and materialization. | Refresh #257/#259 only after a current-corpus run. |
| Stale feature PRs are rebased wholesale | **High** | #329/#346 were closed as no-code supersessions; dependency intent is rebuilt or assigned to its canonical owner. | Keep the replacement ledgers and do not force-update obsolete heads. |
| Current main changes during remediation | **Medium** | PR #430 incorporated concurrent main through a true two-parent merge; #431/#432 started from the current anchor. | Recheck current-main ancestry before review or further edits. |
| Local-only uncommitted work conflicts with GitHub state | **Unknown** | None available through connector. | Operator must run `git status -sb`, inspect ignored files, and compare local branches before local checkout cleanup. |

## Certification state

Wave 0 is **not production certification**. It restores control-plane integrity and denominator honesty. Production status must remain `NON_PRODUCTION_DIAGNOSTIC` until:

1. #430 is green and bounded preflight dispatches succeed.
2. The current 151-source coverage audit is executed against the authoritative operator corpus.
3. Required-source gaps are resolved or formally classified.
4. PR2.5/PR2.6 entity branches are reconciled and PR3 deduplication passes.
5. Production export and downstream federation consumer validation pass.

## Confidence

- Workflow root-cause and remediation: **high**.
- Registry denominator and digest: **high**.
- Dated local materialization snapshot: **high as historical evidence; low as current coverage**.
- Dependency compatibility: **unverified until CI and Parquet compatibility evidence complete**.
- pywebview migration readiness: **deferred to the canonical federation template owner**.
- Local worktree completeness: **unknown**.
