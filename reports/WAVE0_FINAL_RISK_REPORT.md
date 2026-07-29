# MoneySweep Wave 0 — Final Risk Report

**Date:** 2026-07-29  
**Assessment boundary:** Repository control plane plus the certified offline operator-corpus bundle. External-source freshness and universe completeness remain outside this certification.

| Risk | Severity | Current control | Residual action |
|---|---|---|---|
| Live-fetch workflows execute through weak confirmation gates | Critical → controlled | Draft PR #444 uses exact tokens, explicit preflight/fetch separation, bounded inputs, and a shared validator. All three hosted preflight runs passed and every live job was skipped. | Keep PR draft until authorized review; retain environment protection and operator receipts for any future live run. |
| Credentialed producers run unintentionally | High → controlled | Preflight is the default; credentials are scoped to live jobs; live jobs depend on validated fetch-mode inputs. | Review repository/environment permissions before first authorized live execution. |
| Materialization status uses incompatible denominators | High → controlled | The authoritative operator audit now uses the current 151-source registry and matching digest. The dated 144-source evidence is retained only as historical evidence. | Require denominator and digest parity on every future status regeneration. |
| Required sources remain incomplete | High | Current operator corpus certifies 10/14 required sources as fully materialized. | Resolve or formally classify `cor3`, `hud_drgr_authorized`, `pr_cabilderos`, and `prasa`. |
| Registry does not own all processed outputs | High | Audit separates 849,898 registry-accounted rows, 212,930 orphan rows, and 120,737 intermediate rows. | Adjudicate six orphan files; prioritize the two 104,280-row entity outputs and prevent double counting. |
| Local materialization is mistaken for external-universe completeness | High | Audit ran offline with `probe_ran=false`; current status explicitly separates local presence from external completeness. | Perform bounded, source-specific freshness and universe assessments under separate authorization. |
| Dependency updates alter data semantics | High | Draft PR #446 is reconstructed on current main and its CI passed. No data promotion occurred. | Verify PyArrow schema, timestamps, decimals, nullability, and round trips before production export. |
| pywebview 6 drifts from federation templates | High | Excluded from #446 after the template-drift gate identified the ownership boundary. | Use a federation-wide TheHub template migration and validate all consumers. |
| Status rewrite erases dated evidence | Medium | Prior status remains addressable by immutable blob `b175df73deb6ecf5bbf0d0040b89ca75f5d1e10c`; the 144-source audit is explicitly historical. | Preserve immutable references and append new evidence rather than rewriting provenance. |
| Connector-side write contaminates certified branch history | Medium → controlled | #447 was closed unmerged after the restored placeholder write; clean #448 starts from certified pre-write head `1dc7268`. | Do not force-push or rewrite history; keep the supersession record visible. |
| Epic state implies code readiness equals data coverage | Medium | #271 and current status separately report 104/104 structural readiness and 67/151 full local materialization. | Close child tasks only from source-specific evidence and acceptance gates. |
| Main advances during review | Medium | Wave 0 successor branches share main anchor `34ef3b9`; #448 identifies its certified audit input head. | Recheck ancestry, overlap, and current main before review transition or merge authorization. |
| Local-only work conflicts with GitHub state | Medium | Detached-worktree audit preserved the operator checkout's four pre-existing modifications. | Review local modifications and remove the detached worktree only after evidence retention is confirmed. |

## Certification state

Wave 0 now certifies control-plane safeguards and the **current 151-source offline operator-corpus accounting**. It is **not production certification**. Production status remains `NON_PRODUCTION_DIAGNOSTIC` until:

1. The four required-source gaps are resolved or formally classified.
2. The six orphan files are reconciled to registry ownership, derived-output status, or explicit exclusion.
3. PR2.5/PR2.6 reconciliation and PR3 deduplication pass.
4. Source freshness and external-universe completeness are assessed without conflating them with local file presence.
5. Production export and downstream federation-consumer validation pass.
6. The refreshed PR #448 head passes full CI and receives explicit review authorization.

## Confidence

- Workflow root-cause and remediation: **high**.
- Registry denominator and digest: **high**.
- Current offline operator-corpus materialization: **high**.
- Original-worktree preservation: **high from same-shell comparison; not independently proven by the ZIP alone**.
- External-universe completeness and freshness: **not assessed**.
- Dependency compatibility: **medium-high pending production-format validation**.
- Production readiness: **low; gate remains false**.
