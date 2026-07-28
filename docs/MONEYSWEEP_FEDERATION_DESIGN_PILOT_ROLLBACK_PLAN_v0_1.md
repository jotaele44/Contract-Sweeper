# MoneySweep Federation Design System Pilot — Rollback Plan v0.1

## Trigger conditions

Roll back for route/API/data/offline-export regression; package mismatch; accessibility, keyboard, target, or overflow failure; incorrect initial-offline precedence; lost cached data/status banners; non-reactive connectivity/stale transitions; or nondeterministic evidence after animation-independent capture.

## Atomic rollback

1. Revert the pilot and review-remediation commits.
2. Restore the prior v0.3.0 package URL in both package files.
3. Restore `QueryBoundary`, `StatsBar`, and filtered-empty rows from `main@9cbf0bffa89424bca0f261ff45cf06df6e5c1401`.
4. Remove pilot-only harnesses, tests, styles, workflow, evidence, and ledgers.
5. Run dependency install, lint, production build, offline export, deterministic double-run evidence, and repository-wide CI.

No backend, API, data, schema, route, or offline-export data migration is required.
