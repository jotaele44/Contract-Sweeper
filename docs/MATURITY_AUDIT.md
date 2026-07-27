# moneysweep-pr — Professional Maturity Audit

**Date:** 2026-07-26 · **Method:** static review **plus execution** — every number below came
from running the code in a clean container (**Python 3.11.15**, Node v22.22.2), using the
install and test invocation from `.github/workflows/tests.yml`. Note the interpreter
difference: that workflow pins **Python 3.13**, so these are 3.11 measurements, not a
CI-identical baseline. Collection, skips and coverage can shift between interpreters.

Scope: this repository only. Cross-repo comparisons live in
[`thehub-pr/docs/FEDERATION_MATURITY_AUDIT.md`](https://github.com/jotaele44/thehub-pr/blob/main/docs/FEDERATION_MATURITY_AUDIT.md).

---

## Scorecard

| Dim | Area | Score | Evidence |
|---|---|---|---|
| D1 | Functional completeness | **4** | 145.9k LOC, 11 subsystems, 34 CI workflows, real source-materialization pipeline |
| D2 | Data reality | **3** | 431 data files / 17 MB; 9 of 14 required sources live-materialized; blockers named precisely in `federation.json` |
| D3 | UI craft | **2** | **One page**, 1,296 LOC, for 145.9k LOC of backend. 1 `aria-*` usage. State handling is actually good where it exists: `components/QueryBoundary.jsx` gives a shared loading/error-with-retry/empty split, used by `ContractsTable`, `EntitiesTable`, `RelationshipGraph` and `MunicipalityAggregates`. |
| D4 | Test coverage | **4** | **`2394 passed, 8 skipped`** in 120.6s, **51.74% coverage** against a 44% gate. Largest suite in the federation by 2.4×. |
| D5 | Engineering hygiene | **4** | The federation's reference standard: `ruff check .` + `ruff format --check` + mypy + pre-commit + `pip-audit` + lockfile + size-guard + promotion-guard, all clean |
| D6 | Doc accuracy | **3** | 167 markdown files; `STATUS.md` test baseline was ~10 weeks and ~1,900 tests stale (fixed below) |

**Overall: the most professionally engineered backend in the federation, with the least
developed user interface.** Nothing here is fake. The gap is that a 145.9k-LOC public-money
intelligence system surfaces through a single dashboard page.

---

## What is fully developed vs. what is not

**PRODUCTION**

| Module | Evidence |
|---|---|
| `moneysweep/` (122 files, 25,708 LOC) | 11 subsystems: `domains`, `entity_resolution`, `federation`, `fusion`, `modules`, `orchestrator`, `pipeline`, `query`, `runtime`, `update_controller`, `validation` |
| Source materialization | 13 of 15 PR-gov sources promoted to `api_producer`; freshness workflows on weekly/monthly/quarterly/yearly cadences |
| Federation export | `federation-export.yml`, canonical `canonical_v1_federation` bridge streams, hub-validated |
| Centinelas intake | `scripts/ingest_centinelas_signals.py` — consumes pre-official located-finance candidates |
| Contract-finance bundle | `scripts/build_contract_finance_bundle.py` — the artifact `spiderweb-pr` scores |
| CI quality gates | 34 workflows including `mypy.yml`, `pip-audit.yml`, `lockfile.yml`, `repro.yml`, `size-guard.yml`, `promotion-guard.yml`, `production-status-gate.yml` |
| Governance docs | `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md` — **the only repo in the federation with all four** |

**FUNCTIONAL**

| Module | Gap |
|---|---|
| `server/backend/main.py` (275 LOC) | 10 routes (`/contracts`, `/entities`, `/edges`, `/municipalities`, `/stats`, …). **Zero mutating routes** — read-only by construction, which is the right call here. |
| `dashboard/` (1 page, 1,296 LOC) | builds and lints clean; shares state handling through `QueryBoundary`. The one page is the gap, not the craft. |

**SCAFFOLD** — the repo's own inventory says so. `reports/module_inventory.csv`, 231 modules:

| Classification | Count |
|---|---|
| KEEP — unique logic, active imports, or tested | 153 |
| **"Structurally identical to merge-target siblings; consolidate under one module"** | **60** |
| "No active test coverage; not wired into `run_all`; dev-only or one-time artifact" | 7 |
| "Micro-module (<75 lines); logic trivially inlinable into parent" | 6 |
| Already archived (PR-G, PR-I) | 4 |

Roughly 30% of modules are flagged by the project itself as consolidation candidates. That
self-awareness is a maturity signal in its own right — the inventory exists, is current, and
is honest. It is also two months old and unactioned.

**DEAD** — none found. This repo ships no auth UI and no placeholder pages. Its
`federation.json` blockers are specific and verifiable:
Tranche-B manual exports, the JS-gated cor3 portal, and a missing `PROPUBLICA_API_KEY`.

---

## UI feature matrix

| Page | Backing data | States handled | Verdict |
|---|---|---|---|
| `Dashboard.jsx` | `lib/api.js` → `/contracts`, `/entities`, `/edges`, `/municipalities`, `/stats` | loading, error-with-retry and empty, via the shared `QueryBoundary` | **Functional but minimal** |

The API client is well built — `API_BASE` indirection, `AbortSignal.timeout(8000)`, an
offline snapshot path — and `QueryBoundary` handles the three async states in one shared
place. There is simply almost no UI on top of it, and accessibility is thin at 1 `aria-*`
usage across the dashboard.

For comparison inside the same federation: `thehub-pr` has 28 pages over 15.9k LOC of Python;
this repo has 1 page over 145.9k.

---

## Architecture note: the code lives in `scripts/`

| Location | Files | LOC |
|---|---|---|
| `scripts/` | 312 | **81,709** |
| `tests/` | 235 | 34,954 |
| `moneysweep/` (the importable package) | 122 | 25,708 |

Three times as much code sits in loose scripts as in the package. Script-resident logic is
harder to import, reuse, and type-check, and it is the structural reason 60 modules ended up
"structurally identical to merge-target siblings" — duplication is the path of least
resistance when there is no package boundary to put shared code behind. The 51.74% coverage
figure should be read in that light.

---

## Fix applied in this PR

**`STATUS.md` test baseline refreshed.** The header claimed:

> **Date:** 2026-05-18 · **Latest test baseline:** 481 passed · 1 skipped · 0 failed

Measured today with this repo's own CI install and invocation, on Python 3.11.15:
**2394 passed · 8 skipped · 0 failed · 51.74% coverage**. The line was ~10 weeks and ~1,900
tests stale — understating the suite by roughly 5×, which sells the repo short. Updated,
with the measurement command, the interpreter, and the fact that CI pins Python 3.13 all
recorded inline, plus a note not to carry the row forward by hand.

No code changed. `pytest` re-run after the edit: `2394 passed, 8 skipped` — unchanged.

---

## Backlog, ranked

| # | Item | Effort | Why it matters |
|---|---|---|---|
| 1 | Build out the dashboard | **L** | The widest gap in the federation: 145.9k LOC of backend, 1 UI page. `skywatcher-pr/frontend` (15 pages) and `thehub-pr/server/frontend` (28 pages) are in-house patterns to copy. |
| 2 | Action the 60 consolidation candidates in `reports/module_inventory.csv` | **L** | The plan exists (`docs/MODULE_CONSOLIDATION_SCOPE.md`, `MODULE_REDUCTION_PLAN.md`) and has been merged since May. Executing it removes ~26% of modules. |
| 3 | Migrate reusable `scripts/` logic into `moneysweep/` | **L** | 81.7k LOC in scripts vs 25.7k in the package. This is the root cause of item 2, not just a sibling of it. |
| 4 | Add a frontend test runner | **S** | Small here precisely because there is only one page — cheapest moment to establish the harness is before the dashboard grows. |
| 5 | Raise dashboard accessibility coverage | **S** | 1 `aria-*` usage across the dashboard. |
| 6 | Automate the `STATUS.md` baseline row | **S** | It went stale once and will again. Emit it from the test job (on CI's Python 3.13) rather than editing by hand. |
| 7 | Clear the 7 untested / unwired modules | **S** | Named in the inventory; either wire them into `run_all` or archive them. |

**Recorded so it is not re-raised:** `pyproject.toml` here contains only `[tool.mypy]` and
`[tool.ruff]` — no `[project]` or `[build-system]` table. `pip install -e .` therefore fails.
That is correct: this repo is not a distributable package, and its documented setup is
`python3 run_all.py --only-setup`. Not a defect.

---

## Maturity score — 73%

Measured 2026-07-27 against 20 explicit criteria (5 points each, 100 total). Every
lost point is a specific, verifiable work item, so this doubles as the roadmap.

| Dimension | Score | Criteria (5 pts each) |
|---|---|---|
| Functional completeness | **17/20** | backend serves domain · no dead UI · entrypoints work · modules wired, no duplicate mass |
| Data reality | **15/20** | real non-synthetic dataset · refresh automated · offline bundle populated · live-exec gate open |
| UI craft | **8/20** | pages proportionate to backend · loading+empty+error everywhere · a11y markup **and** automated gate · single consolidated frontend |
| Tests | **10/15** | suite green · coverage gate enforced · frontend tests run in CI |
| Hygiene | **12.5/15** | linters gated in CI · type checking gated in CI · write surface secured *and* client can use it |
| Docs | **10/10** | docs match code · declared status matches observed maturity |
| **Total** | **72.5/100** | |

### How the score is computed

20 criteria, 5 points each, 100 total. **Partial credit is allowed** where a criterion
splits cleanly into independent halves — for example "linters gated in CI" scores 2.5 for
Python and 2.5 for JavaScript, so a repo that gates one and not the other scores 2.5. That
is why dimension totals are not always multiples of five.

Components here sum to **72.5** (17 + 15 + 8 + 10 + 12.5 + 10), reported as **73%**. Half-points are
rounded **half up** to the nearest whole percent for the cross-repo table; the exact figure is the one
above.

The earlier 0–4 per-dimension scorecard above is retained for cross-repo comparison,
but it saturates — `aguayluz-pr` scored 24/24 on it while still having no frontend
tests. This finer model is the one to plan against.
