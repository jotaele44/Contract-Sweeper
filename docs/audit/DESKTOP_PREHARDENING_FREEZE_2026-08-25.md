# MoneySweep Desktop Pre-Hardening Freeze — 2026-08-25

## Certification state

**PASS — SOURCE_MANIFESTATION freeze**  
**OPEN — pre-hardening standalone binary BYTE identity**

This ledger freezes the exact repository manifestation that existed before the
self-contained desktop/data-plane hardening branch. It does **not** claim that a
standalone desktop ZIP/DMG existed at this point: the repository had no desktop
software release, so no final distributed binary bytes were available to hash.

## Frozen source manifestation

- Repository: `jotaele44/moneysweep-pr`
- Branch observed: `main`
- Frozen commit: `aa39052cc99d5331fe875196d5853c9d10d0730e`
- Retrieval UTC: `2026-08-25T21:39:28Z`
- Hardening branch created from exactly this commit:
  `agent/desktop-self-contained-data-plane-v1`

The commit SHA binds the Git source manifestation. Git blob SHAs below bind Git
objects; they are **not** SHA-256 digests of distributed file bytes.

## Critical pre-hardening Git object identities

| Surface | Git blob SHA | Meaning |
|---|---|---|
| committed macOS wrapper executable | `f8cdeae6ef9a54ba77a1c99a05e369804464120d` | repo wrapper, not self-contained distribution |
| `desktop/README.md` | `05142c3185810d373fe33b2805509e8f38ee4125` | documented first-run external prerequisites |
| `desktop/pyinstaller.spec` | `4eb92a4e9c0331a48d2ae6b5d078a0f5f51f51c2` | standalone freeze recipe |
| `.github/workflows/desktop-build.yml` | `782fe98980662b1675ee66bddbeb60f8aa76cadb` | standalone build/release workflow |
| `requirements-desktop.txt` | `0ae3da506ec339cb727fe16763929f5795c6ee64` | desktop wrapper dependencies |
| `server/backend/requirements.txt` | `f6e9a2f6faea7b05eaa00d9d90ccc5fdb6261530` | dashboard backend dependencies |
| `reports/materialization_readiness.json` | `c55153af1c92b5c856535a1daa62705a0a590e1e` | generated source-readiness denominator |
| `data/exports/production_status.json` | `1b7b600cef8a72d2b5833d9d0bf2cf47c648c104` | production-status gate |

## Logical/source-denominator identity

The generated readiness artifact at the frozen commit declares:

- registered sources: **158**
- automatable sources: **109**
- automatable structurally ready: **109**
- queued/excluded: **49**
- manual-export sources: **42**
- source-ID-set SHA-256:
  `673659d9c53e8428e21052d95819ff35023e90142756686e73a9c9f1b326bbf2`

That source-ID hash is a LOGICAL denominator binding. It does not establish
BYTE identity for any app archive.

## Pre-hardening factual baseline

### Committed `PRII-MONEYSWEEP.app`

Classification: **NONCANONICAL distribution wrapper**.

The wrapper required the repository beside it and, on a first run, an internet
connection plus externally installed Python/Node tooling. It therefore did not
meet `DOWNLOAD -> DOUBLE-CLICK -> READY` on a clean Mac.

### PyInstaller standalone path

Classification: **CANDIDATE_NOT_IDENTITY**.

The standalone workflow could freeze Python and produce a macOS `.app`/DMG,
but its pre-hardening spec bundled only the dashboard build and
`data/canonical_v1`. The dashboard backend was a thin read-only CSV API and the
workflow did not install/freeze the complete MoneySweep/Contract-Forensics
runtime (`duckdb`, `pyarrow`, registry-driven producers, etc.). A passing health
smoke therefore did not prove full MoneySweep boot.

### Data state

Classification: **NON_PRODUCTION_DIAGNOSTIC**.

The frozen production-status artifact reports three blockers:

1. populated report layers = 3, required >= 8;
2. unique entities = 18, required >= 100;
3. fixture/synthetic signatures detected = true, required false.

Therefore packaging certification and production-data certification remain
separate gates.

## Contradiction ledger

| Class | Observation A | Observation B | Adjudication |
|---|---|---|---|
| TIME / DOCUMENTATION | `docs/MATERIALIZATION_RUNBOOK.md` prose lists historical 144/99/45 counts | generated readiness artifact lists 158/109/49 | generated artifact **SUPERSEDES** prose counts |
| DEPLOYMENT | committed `.app` is described as double-clickable | first run still requires external runtime/tooling | double-click wrapper != self-contained distribution |
| RUNTIME | standalone PyInstaller path exists | historical Contract-Forensics runtime was held on real DuckDB/PyArrow | exact frozen release must import/test real dependencies; existence of build recipe is insufficient |

## Preservation rule

This base commit and the object identities above are immutable comparison
anchors. Hardening work must not rewrite this ledger to make the historical
state appear stronger. A future release certificate must instead record the
new source commit and exact ZIP/DMG SHA-256 values emitted by the build.

## Final binary certification contract

A distributed macOS artifact becomes **CERTIFIED** only when the exact packaged
bytes satisfy all of the following:

- source commit and source-ID denominator are recorded;
- complete frozen runtime self-test passes, including real DuckDB/PyArrow;
- writable workspace is outside the `.app` bundle;
- offline seed boot succeeds without network, Python, Node, Homebrew, Conda,
  pip, npm, git, or Terminal;
- signed code passes strict `codesign` verification;
- notarization ticket is stapled and validates;
- Gatekeeper `spctl --assess` passes;
- package ZIP/DMG SHA-256 is emitted in `DESKTOP_RELEASE_MANIFEST.json`;
- production release is blocked unless `production_status == PRODUCTION_VALIDATED`.

Until the exact final artifact executes these gates, desktop distribution state
is **PROVISIONAL**, not CERTIFIED.
