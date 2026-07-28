
# MoneySweep Federation Design System Pilot — Rollback Plan v0.1

## Trigger conditions

Rollback if the pilot introduces a route/data regression, offline-export failure, package-integrity mismatch, serious or critical accessibility finding, keyboard regression, or horizontal overflow at a certified viewport.

## Atomic rollback

1. Revert the pilot commit(s) on the draft branch or resulting PR.
2. Restore `@pr-federation/react` to the prior v0.3.0 release URL in both package files.
3. Restore local `QueryBoundary`, `StatsBar`, and filtered-empty rows from `main@9cbf0bffa89424bca0f261ff45cf06df6e5c1401`.
4. Remove the pilot-only visual harness, tests, styles, workflow, evidence, and ledgers.
5. Run `npm ci`, `npm run lint`, `npm run build`, and the existing offline export build before considering any replacement.

No backend, API, data, or offline-export file requires data migration or rollback because those surfaces are not modified.
