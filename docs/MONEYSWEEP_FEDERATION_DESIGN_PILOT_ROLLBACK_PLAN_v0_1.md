# MoneySweep Federation Design System Pilot — Rollback Plan v0.1

## Trigger conditions

Roll back for a route/API/data/offline-export regression; package-integrity mismatch; serious accessibility, keyboard, target-size, or overflow finding; initial offline resolving to loading; cached data disappearing during offline/degraded/stale states; connectivity or stale deadlines failing to update without another rerender; or filtered-empty content suppressing an active status banner.

## Atomic rollback

1. Revert the pilot and review-remediation commits.
2. Restore the prior v0.3.0 package URL in both package files.
3. Restore `QueryBoundary`, `StatsBar`, and filtered-empty rows from `main@9cbf0bffa89424bca0f261ff45cf06df6e5c1401`.
4. Remove pilot-only harnesses, tests, styles, workflow, evidence, and ledgers.
5. Run `npm ci`, lint, production build, offline export, and repository-wide CI.

No backend, API, data, schema, route, or offline-export data migration is required.
