# MoneySweep Federation Design System Pilot — Implementation Ledger v0.1

## Identity

- Repository: `jotaele44/moneysweep-pr`
- Audit baseline: `main@9cbf0bffa89424bca0f261ff45cf06df6e5c1401`
- PR base: `main@7c8267cb9ee2af2382aec940edcc7b0becab4bd4`
- Immutable release *as originally reviewed*: `federation-design-v0.4.0-rc.1`
- Tarball SHA-256 *as originally reviewed*: `4c68f03c8fc7ed0d1e62af7997e02bfca9b6c95ee1740376ebaf7a3a9752ee5b`
- **Current pin: `federation-design-v0.4.1`** — see the amendment at the end of this ledger.

This block records the baseline the pilot was *reviewed against* and is deliberately not
rewritten when the pin moves; the evidence below (run IDs, capture hashes) was produced
against it.

## Implemented and reviewed scope

- Exact immutable package pin; shared async states, buttons, panels, stat cards, and semantic badges.
- Filtered-empty delegation for contracts, entities, and relationships.
- Reactive browser connectivity and stale-deadline updates.
- Initial offline state precedes loading; cached status banners survive filtered-empty rendering.
- Real-`QueryBoundary` six-viewport runtime matrix.
- Consumer panel reset removes inherited nested chrome.
- Deterministic screenshot capture disables animation phase and caret variance.

## Review findings remediated

1. Initial `pending + paused + no data` precedence.
2. Non-reactive connectivity and stale transitions.
3. Direct-primitive atlas coverage gap.
4. Nested state-panel border.
5. Animation-phase screenshot hash drift.

## Verification

- Release manifest source hashes: **11/11**; API snapshot: **35 exports, zero removals**
- Token version: **2.0.0**; mutable references: **false**
- Unit/runtime contracts, ESLint, production build, and offline export: **passed**
- Axe critical/serious: **0**; horizontal overflow: **0 of 12**
- Keyboard and 44 px target checks: **passed**
- Two clean captures at the same code SHA: **7 of 7 internal evidence files byte-identical**
- Deterministic run/artifacts: `30377448213`, `8695575081`, `8695693133`

## Preservation

No route, backend, API, schema, data contract, source dataset, generated export, or offline-export semantic change. No other Federation consumer is bumped.

## Amendment — pin moved to `federation-design-v0.4.1`

The pilot was pinned to `federation-design-v0.4.0-rc.1`, a **prerelease** cut before the
design-system lines converged. The first scope line of the consumer pilot plan calls for
pinning the immutable v0.4 release once release authorization exists; it now does, so this
repo moves straight to `v0.4.1` rather than stepping through `v0.4.0`.

- Release: `federation-design-v0.4.1`
- Tarball SHA-256: `a609b6e88103e6bdfc4af8305e8997843f6e2c1e60ae386ef17ae3f211272f45`
- Unchanged across the bump: release-manifest source hashes **11/11**, API snapshot **35
  exports / zero removals**, token version **2.0.0**, mutable references **false**, harness
  viewports **6**. `loading` and `accent` are new *props*, not new exports, so the API
  surface genuinely does not move.

### Rendering change this bump introduces

`rc.1` predates the convergence commit, so two changes land here for the first time:

1. **Monospace stat values** — `font-family: var(--fd-font-mono)` with
   `letter-spacing: -.02em`. Verified as *computed*, not merely present in the stylesheet:
   the atlas resolves `"JetBrains Mono", ui-monospace, …` at `-0.48px` tracking.
2. **`.fd-stat-card { position: relative; overflow: hidden }`** — added for the v0.4.1 accent
   bar, and incidentally a clip for over-long values.

Wider digits put the horizontal-overflow requirement at risk, so it was measured rather than
assumed. Worst case is the atlas stress value `$128,450,000` at `mobile-compact` (390 px),
where the grid is single-column: value `scrollWidth` **324 px** inside a **356 px** card —
32 px of headroom, fitting without relying on the clip. `StatsBar` is unaffected regardless,
since it scrolls inside `overflow-x-auto` with `shrink-0` children and so never propagates
`scrollWidth` to the document.

### Re-verification evidence

- `verify:federation-design` — re-downloads the tarball and recomputes the SHA-256: match.
- `verify:pilot` — package verify, 8/8 runtime contracts, ESLint, production build: passed.
- `test:visual` — run separately from `verify:pilot`, because the CI job of the same name
  covers both: **12/12** viewport×theme combinations with `horizontalOverflow: false` and
  `axeCriticalSerious: 0` across all six viewports in dark and light.
