# MoneySweep Federation Design System Pilot — Visual State Atlas v0.1

## Deterministic reviewed runtime matrix

Each screenshot is produced by the real MoneySweep `QueryBoundary`. The matrix exercises loading, error, empty, filtered-empty, stale-with-cached-data, and initial-offline states with shared buttons, panels, stat cards, long labels, and semantic operational badges.

| Viewport | Size | Screenshot | SHA-256 |
|---|---:|---|---|
| mobile-compact | 390×844 | `mobile-compact.png` | `88c6a9d1b9cbcca03144e8401553732d1f3eb1a8b0250b4279eb16cc556b0888` |
| mobile-wide | 430×932 | `mobile-wide.png` | `9628a9eb32f8a653bf729b45f3b2ef31e03f5d9fdb2e18cdab4a3863d01882c2` |
| tablet | 768×1024 | `tablet.png` | `84b8f7578f732c9467c5e80dd2c47ec40b1f5395abf2b1de99fdcbbfe6d56b9b` |
| desktop | 1280×800 | `desktop.png` | `7d60239d9283c911be951c0cea809ed11e583b37d5a118534a0faca2b285ba49` |
| desktop-wide | 1440×900 | `desktop-wide.png` | `b081fa5249b7b74d91a5f158984dbe491706a63d8378bfed2a235e6a06edf6b2` |
| wide | 1920×1080 | `wide.png` | `541e67466eb87b23ee582b3344b1fd3bcc40115642df403e9c9f0be0e4eed41a` |

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

## Two-run reproducibility certificate

- Exact code head: `62758c3beb8db55bb9c7f52cb034d4952bfd59cb`
- Workflow run: `30377448213`
- Attempt 1 artifact: `8695575081`; ZIP SHA-256 `646891f94f495a5cc7604cdebd96dc6427341c9473397e2a493f1db8ff7aa04b`
- Attempt 2 artifact: `8695693133`; ZIP SHA-256 `569b69011471b75b24842738ce3bf8a60ce54a4eb29a31367d4b63ca0e6f969a`
- ZIP containers differ only in archive metadata; **all six PNGs and the JSON report are byte-identical**
- Report SHA-256 in both attempts: `7ff5648ed7d5fd21fbd65a4cc9eee3d56d741e1249f79ff430d5ed8a98863f9a`

Evidence directory: `docs/evidence/moneysweep-federation-design-pilot-v0-1/`.
