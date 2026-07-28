# MoneySweep Federation Design System Pilot — Visual State Atlas v0.1

## Reviewed runtime matrix

Each screenshot is produced by the real MoneySweep `QueryBoundary`, not by direct state-component examples. The matrix exercises loading, error, empty, filtered-empty, stale-with-cached-data, and initial-offline states together with shared buttons, panels, stat cards, long labels, and semantic operational badges.

| Viewport | Size | Screenshot | SHA-256 |
|---|---:|---|---|
| mobile-compact | 390×844 | `mobile-compact.png` | `fab04c5a32a2b3edfa1dc16c952e02d0f98dfb12c63a9796a5c0d09d7a335f41` |
| mobile-wide | 430×932 | `mobile-wide.png` | `0a0f7bd62835738d4e31c0d5d43c619cdc054f8b2c0c3e40f459f66e1f7a690d` |
| tablet | 768×1024 | `tablet.png` | `51995db7fe2dd4ab07503b74884bcd6d0b169a75888f9697594cdadf6d2e81d1` |
| desktop | 1280×800 | `desktop.png` | `720e9d92ca5812517190ae161ca76bbff6d67efe424befbac98ff58129905a3e` |
| desktop-wide | 1440×900 | `desktop-wide.png` | `a2284e1ca2a6c3326b3a6cae3deaee1fb3b7473a84f50b41b671493b0264cb08` |
| wide | 1920×1080 | `wide.png` | `0ddf92c45af8eda387e57ff616cc9c4b517b745db4cc5ebaa36134408e56eab0` |

## Automated checks

- Evidence schema: **1.1.0**
- Themes audited: **dark and light**
- Runtime state identities: **loading, error, empty, filtered-empty, stale, offline**
- Initial offline precedence over loading: **passed**
- Cached data remains visible with the offline banner: **passed**
- Filtered-empty preserves offline/degraded/stale status banners: **passed**
- Critical/serious axe findings: **0**
- Horizontal overflow: **0 of 12 viewport/theme runs**
- Minimum interactive target: **44 CSS px**
- Keyboard traversal: a shared button was reachable at all six viewports
- Manual visual review: **passed all six screenshots**

## Evidence identity

- Permanent verifier run: `30376207971`
- GitHub artifact: `8695093341`
- Artifact ZIP SHA-256: `2f325547ea79d594036924a08cd05a85d4a4034370be25859a5b2ed2cb52bf04`
- Report SHA-256: `ecab4a585379a7c4d8e4178cb2e9e42bde3e07faf836805bef0d9f6ef08e82d9`

Evidence directory: `docs/evidence/moneysweep-federation-design-pilot-v0-1/`.
