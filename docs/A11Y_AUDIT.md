# Accessibility Audit — moneysweep-pr Dashboard

Audit date: 2026-08-24
Scope: `dashboard/` (React/Vite SPA), the same surface covered by
`docs/GUI_AUDIT.md`. This pass is a follow-up focused on WCAG-relevant
findings and design-system-usage data collection (`docs/design-system-usage.json`),
not a re-review of feature completeness.

## Overview

moneysweep-pr's dashboard has exactly one real route (`/`) with six in-page
tab states (Contracts, Entities, Gov Changes, Relationships, Municipios,
Campaign Finance) switched via a Radix `Tabs` component — there is no
per-tab URL to scan independently. The app is hard-coded to a single dark
theme (`main.jsx` sets `document.documentElement.dataset.theme = 'dark'`
unconditionally); there is no light theme and no theme toggle anywhere in
the shipped UI, despite the `@pr-federation/react` package exporting
`FederationThemeProvider`/`useFederationTheme` for exactly this purpose (see
`docs/design-system-usage.json` for the full parity findings).

Backend: FastAPI (`server/backend/main.py`), read-only over the frozen
`data/canonical_v1/*.csv` corpus, CORS allow-list configurable via
`MONEYSWEEP_CORS_ORIGINS` (no code change was needed to point it at this
audit's port).

## Method

The shared a11y runner at `/home/user/.a11y-runner` (pinned Playwright
1.62.1 + axe-core 4.12.1 via `@axe-core/playwright`, Chromium launched with
an explicit `executablePath` at a provisioned revision, and a fixed
networkidle+800ms settle wait to avoid the hydration-race false-passes it
previously had) is built to scan one URL per test file — it has no concept
of clicking an in-page tab. Because this app has a single route with six
tab *states* rather than six routes, a throwaway script
(`tmp-moneysweep-tab-audit.mjs`, run from inside `.a11y-runner` against its
own pinned `node_modules` and Chromium `executablePath`, then deleted —
the shared directory's checked-in files were not modified) drove the same
three checks the shared runner's spec file uses, plus an axe scan, against
each tab:

1. Load `/`, wait for networkidle + 800ms settle (matching the shared
   runner's fixed hydration wait).
2. For each of the 6 tabs: click it by accessible name (`role=tab`), wait
   800ms again, then run:
   - a full `axe-core` scan, filtered to `critical`/`serious` impact for the
     headline table, with the full violation-id summary also recorded;
   - a horizontal-overflow check (`scrollWidth > clientWidth`);
   - a touch-target sweep over all visible `button`/`[role=tab]` elements,
     flagging anything under 44px in either dimension;
   - a keyboard-focus-visible check (Tab once from a reset focus, assert a
     non-`none` outline or box-shadow on the focused element).
3. Repeat the whole pass at both required viewports: 390×844 (mobile) and
   1280×800 (desktop).

**Scope limitations (explicit, not incidental):**
- **Two viewports only** (390×844, 1280×800), per the audit's assigned
  scope — not the federation package's own 6-viewport contract (see below).
- **Dark theme only.** Not a scoping choice on this audit's part — the app
  has no light theme to test. See Finding 6.
- Only `button`/`[role="tab"]` elements were swept for touch-target size;
  the shadcn `Select` trigger (a `<button>` under Radix) and `<input>`
  filter fields were not separately dimension-checked beyond axe's own
  rules.
- axe was run with its default rule set (not restricted to WCAG tags); the
  per-tab table below reports the `critical`/`serious` subset as the
  blocking signal, consistent with the shared runner's own pass/fail bar.
- This is a single-session automated pass, not a manual screen-reader
  walkthrough.

## Per-tab results (axe critical/serious violations, both viewports)

| Tab | Mobile (390×844) | Desktop (1280×800) | Horizontal overflow (mobile) | Touch targets <44px |
|---|---|---|---|---|
| Contracts | 2 (`color-contrast`, `scrollable-region-focusable`) | 1 (`color-contrast`) | yes | 6 (all tab triggers, 24px tall) |
| Entities | 3 (`button-name`, `color-contrast`, `scrollable-region-focusable`) | 2 (`button-name`, `color-contrast`) | yes | 7 (tab triggers + type-filter select) |
| Gov Changes | 2 (`color-contrast`, `scrollable-region-focusable`) | 2 (`color-contrast`, `scrollable-region-focusable`) | yes | 6 (tab triggers) |
| Relationships | 3 (`button-name`, `color-contrast`, `scrollable-region-focusable`) | 3 (`button-name`, `color-contrast`, `scrollable-region-focusable`) | yes | 7 (tab triggers + type-filter select) |
| Municipios | 2 (`color-contrast`, `scrollable-region-focusable`) | 1 (`color-contrast`) | yes | 6 (tab triggers) |
| Campaign Finance | 2 (`color-contrast`, `scrollable-region-focusable`) | 1 (`color-contrast`) | yes | 6 (tab triggers) |

Additional non-blocking (`moderate`) axe findings present on every tab at
both viewports: `landmark-one-main` (no `<main>` landmark) and `region` (11
instances — most page content sits outside any landmark region).
`heading-order` fires once, on Municipios only.

Keyboard focus visibility: **pass on every tab, both viewports.** The first
Tab press always lands on a visibly-focused element (Radix's default focus
ring — a two-layer box-shadow in cyan/dark — or, on the desktop Contracts
tab specifically, a fainter shadow-only variant). This is a genuine pass,
not a hydration-race false positive, per the shared runner's fixed settle
wait.

## Findings (prioritized)

1. **[Serious/Critical, all tabs] `color-contrast` fires on every tab, at
   both viewports.** The most consistent target across tabs is the inactive
   `TabsTrigger` elements (`#radix-_r_0_-trigger-*`) plus assorted
   `text-muted-foreground`/`text-[10-11px]` micro-copy (filter-bar counts,
   table sub-labels, stat-card units). This is the single largest
   contributor to the violation counts above (9-36 individual nodes per
   tab) and is almost certainly one root cause (muted-foreground token
   against the dark card background) repeated across every screen, not six
   independent bugs.

2. **[Critical] `button-name` on Entities and Relationships (both
   viewports): the type-filter dropdown has no accessible name.**
   `TypeFilterSelect.jsx` renders a bare shadcn/Radix `Select` (`<SelectTrigger><SelectValue /></SelectTrigger>`,
   `dashboard/src/components/ui/select.jsx`) with no `aria-label` and no
   associated visible `<label>` — axe reports the trigger button as
   unnamed. Evidence:
   `docs/a11y-evidence/entities-select-button-name-desktop-1280x800.png`.
   Recommended fix: an `aria-label` (e.g. "Filter by entity type" /
   "Filter by edge type") on each `TypeFilterSelect` call site, or a visible
   `<label>` wired via `htmlFor`.

3. **[Serious] `scrollable-region-focusable`: horizontally-scrolling table
   regions (`.overflow-x-auto` / `.ms-scroll-region`) are not keyboard-
   reachable**, on 5 of 6 tabs at mobile and 3 of 6 at desktop (inconsistent
   presence suggests it depends on whether that tab's table is actually
   wide enough to scroll on a given viewport, not a uniform component gap
   — but every scrollable table container should carry `tabindex="0"` plus
   an accessible name regardless).

4. **[Serious, mobile only] Every tab overflows horizontally at 390px, and
   the primary tab bar is unreadable at that width.** `TabsList` is a fixed
   `grid-cols-6` (`dashboard/src/pages/Dashboard.jsx`); at 390px the six
   labels ("Contracts", "Entities", "Gov Changes", "Relationships",
   "Municipios", "Campaign Finance") don't wrap or truncate, so adjacent
   labels visually overlap and become illegible — see
   `docs/a11y-evidence/tabbar-overflow-mobile-390x844.png` and the existing
   `badge-contracts-mobile-390x844.png` / `button-clearfilters-mobile-390x844.png`.
   Tables also run wider than the viewport on mobile with no visible
   scroll affordance (the Status column is pushed fully off-screen in
   `badge-contracts-mobile-390x844.png`).

5. **[Serious, all tabs, both viewports] All six tab triggers measure 24px
   tall** (60px wide at mobile, 208px wide at desktop) — below the 44px
   minimum touch target on every tab, at every viewport. This is the
   primary navigation control for the entire app, so it's the single
   highest-value touch-target fix available. The type-filter `Select`
   trigger (Entities/Relationships) is also under 44px tall (28px).

6. **[Design-system parity, informational] The app is dark-only with no
   theme toggle, while `@pr-federation/react` exports a theme provider
   built for exactly this.** `FederationThemeProvider`/`useFederationTheme`
   are never imported anywhere in `dashboard/src`. `main.jsx` hardcodes the
   theme attribute. A light theme therefore could not be captured for this
   audit's evidence set because none exists in the shipped app — see
   `docs/design-system-usage.json` (`themeSupport`) for detail, including
   the separate, non-shipped visual-test fixture that *does* render both
   themes for the pilot's own tooling only.

7. **[Informational] The federation package's own test-harness contract
   (`node_modules/@pr-federation/react/dist/test-harness.contract.json`)
   requires zero critical/serious axe violations, no touch target under
   44px, and no horizontal overflow — the app currently fails all three of
   its own dependency's stated requirements.** See
   `docs/design-system-usage.json` → `federationPackage.pilotTooling` for
   the full pilot-script results, including that this repo's own dedicated
   6-viewport/2-theme visual-regression script (`npm run test:visual`) is
   currently non-functional in this environment (missing browser
   executable, not fixed as part of this audit — see that file for why).

## Evidence

All screenshots live under `docs/a11y-evidence/` (six carried over from the
prior attempt at this audit, confirmed still accurate and reused as-is;
two new ones added for the tab-bar overflow and button-name findings
above):

- `badge-contracts-desktop-1280x800.png`, `badge-contracts-mobile-390x844.png`
- `button-clearfilters-desktop-1280x800.png`, `button-clearfilters-mobile-390x844.png`
- `dialog-contract-sheet-desktop-1280x800.png`, `dialog-contract-sheet-mobile-390x844.png`
- `tabbar-overflow-mobile-390x844.png` (new)
- `entities-select-button-name-desktop-1280x800.png` (new)

Note on the contract-sheet screenshots: the subtitle line
(`contract_puerto_rico_highways_and_transportation_authorit…`) is truncated
mid-word with no ellipsis or `title`/tooltip affordance at either viewport
— worth a follow-up look even though axe does not have a rule that catches
silently-truncated text.

## Scope limitations (recap)

- 2 viewports (390×844, 1280×800), dark theme only (no light theme exists
  to test), single automated session, default axe rule set, `button`/
  `[role=tab]` touch-target sweep only. See "Method" above for the full
  list and why each applies.
