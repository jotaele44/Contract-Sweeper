# MoneySweep Federation Design System Pilot — Visual State Atlas v0.1

## Deterministic reviewed runtime matrix

Each screenshot is produced by the real MoneySweep `QueryBoundary`. The matrix exercises loading, error, empty, filtered-empty, stale-with-cached-data, and initial-offline states with shared buttons, panels, stat cards, long labels, and semantic operational badges.

| Viewport | Size | Screenshot | SHA-256 |
|---|---:|---|---|
Captured against `federation-design-v0.4.1`. The v0.4.0-rc.1 capture this atlas originally
certified is superseded — see "Supersedes" below for why every hash moved.

| Viewport | Size | Screenshot | SHA-256 |
|---|---:|---|---|
| mobile-compact | 390×844 | `mobile-compact.png` | `9cd8797023abcdbe03e1d5b1636a917d3f51b0f41d8d7928e6c81f2b76edafd2` |
| mobile-wide | 430×932 | `mobile-wide.png` | `55592bf92716140cb6fe177535654007b361008a33913a4cc773f8012ab316d2` |
| tablet | 768×1024 | `tablet.png` | `c6f75dd1af426461abf49b9d14f3804f870f469c1a548f9573484b6483a2bb35` |
| desktop | 1280×800 | `desktop.png` | `d897fdf00c7b75b10109dd6774349f49d4d5a05927d5a70fb668ee7d8efc97c4` |
| desktop-wide | 1440×900 | `desktop-wide.png` | `b6cc9065d9bf1d28f6f3d1efbe3df3ae9535da7f53d680939d2706cf0b38b701` |
| wide | 1920×1080 | `wide.png` | `dba5018d82567ea0ce32936e58471470df0b376469d13e83334a62cdb0b4f3e2` |

## Automated checks

- Evidence schema: **1.2.0**
- Runtime state identities: **loading, error, empty, filtered-empty, stale, offline**
- Initial offline precedence, cached offline data, and filtered-empty banner composition: **passed**
- Critical/serious axe findings: **0**
- Horizontal overflow: **0 of 12 viewport/theme runs**
- Minimum interactive target: **44 CSS px**
- Keyboard traversal: **passed at all six viewports**
- Deterministic capture: reduced motion, animations disabled, caret hidden
- Manual visual review: **passed all six screenshots**

## Supersedes — why every hash moved

The pin moved from the `federation-design-v0.4.0-rc.1` prerelease to `federation-design-v0.4.1`.
rc.1 was cut before the design-system lines converged, so two rendering changes reached this
repo for the first time and changed every capture:

1. **Monospace stat values** — `font-family: var(--fd-font-mono)` with `letter-spacing:-.02em`.
   Verified as *computed*, not merely present in the stylesheet: the atlas resolves
   `"JetBrains Mono", ui-monospace, …` at `-0.48px`. rc.1 shipped no `font-family` on the
   value at all.
2. **`.fd-stat-card { position: relative; overflow: hidden }`** — added for the v0.4.1 accent bar.

The atlas kicker also changed from `immutable RC` to `immutable release`, which the pin move
falsified.

Wider digits put the horizontal-overflow requirement at risk, so it was measured rather than
assumed. Worst case is the stress value `$128,450,000` at `mobile-compact`, where the grid is
single-column: the value measures **324 px** inside a **356 px** card — 32 px of headroom,
fitting without relying on the clip.

## Two-run reproducibility certificate

- Source tree: the capture in `1cc25ec` (only this documentation changed afterward, which does
  not affect rendering)
- Two independent consecutive captures of that tree produced **all six PNGs and the JSON report
  byte-identical**
- Report SHA-256 in both attempts: `4e0b053fdd81dd47043eb6d4f556239d4338d8b2770a1781148e138762256bd0`

This certificate is a **local** double-run, unlike the one it replaces, which was a CI
double-run (workflow `30377448213`, artifacts `8695575081` / `8695693133`) against the rc.1
capture. Those artifact identifiers belong to superseded evidence and are recorded here only
so the earlier certificate remains traceable — they do not authenticate the files above.

Evidence directory: `docs/evidence/moneysweep-federation-design-pilot-v0-1/`.
