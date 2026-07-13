# Production Certification Status

This document records, honestly and precisely, where `moneysweep-pr` stands relative to a
production-certified (`production_status = PRODUCTION_VALIDATED`) release, and exactly what would have
to happen to get there. It is descriptive, not an action: **certification is a deliberate maintainer
"release cut," not a status-file edit**, and this document does not change any gate, CI assertion, or
status file.

## Current status

- `federation.json` → `production_status: "NON_PRODUCTION_DIAGNOSTIC"`, `pause_lock_required: true`.
- `data/exports/production_status.json` → runtime-computed `NON_PRODUCTION_DIAGNOSTIC`, `blocker_count: 3`.
- `data/exports/rebuild_status.json` → `phase_7_8_blocked: true` (paired phase lock).

This is the intended state. The status is held down by three independent layers, each of which must be
satisfied — and the flip performed deliberately — before it can change.

## The three layers that gate certification

### 1. CI lock — `.github/workflows/production-status-gate.yml`
Runs on every push/PR and **asserts the diagnostic state cannot silently change**: the build fails if
`production_status != "NON_PRODUCTION_DIAGNOSTIC"` or `phase_7_8_blocked != true`, and the repo-quality
pause-locks re-assert `downloads_executed = False`, `rows_ingested = 0`, `production_inputs_staged = 0`.
Any PR that flips the status must therefore also, in the same PR, rewrite these assertions — by design,
so a flip is a conscious, reviewable act rather than an accident.

### 2. Runtime gate — `moneysweep/validation/production_status.py`
`run_production_status_gate.py` → `evaluate_production_status()` computes the status from local
diagnostic summaries (`data/reports/pr_report_summary.json`, `pr_power_network_summary.json`,
`pr_prime_sub_summary.json`, `entity_master.csv`, `output_validation_audit.json`). Hard blockers that
force `NON_PRODUCTION_DIAGNOSTIC`:

| Blocker | Threshold | Current |
|---|---|---|
| `data_layers_populated` | must be ≥ 8 | **3** |
| `unique_entities` | must be ≥ 100 | **18** |
| `fixture_or_synthetic_data_detected` | must be `false` | **true** (the "exactly 18" heuristic) |

In CI these always read the empty/bootstrap state, because the processed masters
(`data/staging/processed/pr_*.csv`) are gitignored and absent from a clean checkout. That is captured in
`reports/materialization_coverage_audit.json`: `committed_ci_view.fully_materialized = 10`,
`coverage_rate ≈ 0.069` (up from 8 / 0.056 — `lda` and `sam_entities` now reproduce as materialized in a
clean checkout via their row-count entries in the committed `data/manifests/staging_masters.json`, which
is the designed committed proxy for the gitignored masters) — versus
`local_truth_summary.materialized_any_data = 15` after a keyed local run. The reproducible per-source
status snapshot (`reports/source_registry_status.csv`, `reports/completeness_matrix.*`,
`reports/gap_analysis_report.*`) is regenerated from the registry + manifest and is byte-identical to a
fresh-clone regeneration; the richer data-present counts live only in `local_truth_summary` and this prose.

### 3. Coverage gate — `moneysweep/runtime/validation_gates.py`
Required-source coverage must be ≥ 0.85. The denominator is only the **`required: true`** sources
(14 of them), not all 99 automatable sources. Currently ≈ **0.57** (8 of 14 fully materialized), up
from 0.43 (6 of 14) after the reachable-producer materialization pass documented below. The
14 required sources now bucket as:

- **Fully materialized (8):** `emma_bonds`, `fec`, `fema_pa_openfema_v2`, `fsrs_subawards`,
  `hud_cdbg_dr_public`, `usaspending_subawards`, **`lda`** (all 14 LDA.gov tables materialized live),
  **`sam_entities`** (SAM UEI enrichment index + resolved entities).
- **Partial (1):** `usaspending_prime` — `pr_contracts_master.csv` is materialized (5,147 rows), but
  the second declared output `pr_all_awards_master.csv` is the cross-source *unified* master, whose
  fail-closed builder (`scripts/build_unified_master.py`) requires ~15 upstream masters — most of them
  out-of-scope sources (`pr_doe_master`, `pr_dot_master`, `pr_epa_master`, `pr_grants_master`,
  `pr_sba_loans_master`, `pr_sbir_master`, `pr_slfrf_master`, `pr_usace_civil_master`, `pr_usda_master`,
  `pr_research_master`, `pr_wioa_grants`, …) that were never materialized in this project state. It is
  honestly blocked, not faked — no partial "all-awards" aggregate is fabricated to flip the bit.
- **Portal / manual / JS-gated, no public API (5):** `cor3`, `oficina_contralor`, `prasa`,
  `pr_cabilderos`, `hud_drgr_authorized`. These require manual acquisition; no API key unlocks them.

The reachable ceiling with the 5 portal sources unmovable is **9/14 ≈ 0.64** (only `usaspending_prime`
remains among the reachable set); the 0.85 gate is not attainable from reachable sources alone and is
not force-flipped here.

So completing this gate requires **both** the portal/manual acquisitions **and** finishing the unified
`usaspending_prime` master once its upstream source masters exist.

## What the keyed live run did — and did not — do

The keyed materialization run (documented in `docs/ROAD_TO_100.md`) materialized **FRED (2,138 rows),
EIA (620), FAC municipal single audits (785), FEC committees (86)** — real data against live APIs —
raising `materialized_any_data` from 11 → 15. This is genuine progress, but it does **not** move the
production gate, because none of those four is one of the unmet *required* sources in the coverage
denominator.

The follow-up **reachable-source materialization pass** did move two required sources
(`required_fully_materialized` 6 → **8**, required coverage 0.43 → **0.57**):

- **`lda`** — `scripts/sources/fetch_lda_gov.py --live` materialized all 14 LDA.gov tables (registrants,
  clients, lobbyists, filings, contributions, and the 8 `constants/*` reference tables) against the live
  Senate LDA Open Data API (anonymous access). A producer fix makes pagination resilient: the very large
  unfiltered `filings`/`contributions` tables (~2 M rows) reject `page>=2` with HTTP 400, and the adapter
  now retains page-1 records instead of discarding the whole endpoint.
- **`sam_entities`** — `scripts/sam_enrichment.py` produced `enrichment/vendor_uei_index.csv` (real PR
  federal-contract vendors) against the live SAM Entity-Information API. The API key authenticates and
  returns data (verified: 18,101 PR-domiciled entities on a `physicalAddressProvinceOrStateCode=PR`
  probe; individual vendor UEIs resolve, e.g. `WSP USA SOLUTIONS INC → E1VGFJ7WCW79`). In the bounded
  batch run SAM's per-key rate limit (HTTP 429) throttled live lookups, so the committed index records
  the vendor set with honest per-row resolution status rather than fabricated UEIs — the earlier
  "429/403 entitlement" theory is disproved: the key is entitled, the limit is rate, not access.
- **`legislative_canonical_sources`** (`required: false`) — the OpenStates v3 chain
  (`fetch_legislative_canonical_sources.py`, `OPENSTATES_API_KEY`) cross-confirmed 2 PR measures
  (PS 782, RCS 14) to real OpenStates bill IDs (session 2025-2028). `legislapr_discovery` itself stays
  unmaterialized: `legislapr.com` is a JS-rendered SPA, so the HTML probe yields page-shell noise, not
  measure data — it is portal/JS-gated exactly as the out-of-scope set is.

Tracked evidence is `reports/materialization_coverage_audit.{json,csv}` and the row-count entries added
to `data/manifests/staging_masters.json`; the raw CSVs stay gitignored under `data/**`.

## `CENSUS` / `PROPUBLICA` are not the blockers

`census_gov_finances` is `required: false`, and ProPublica/`nonprofits_irs990` is `required: false`
(ProPublica is not even a keyed source). Neither is in the 14-source coverage denominator. They appear
in `federation.json` `runtime_required_keys` / `automatable_required_keys`, which gate *automatable
readiness*, not the *production coverage* gate. **Supplying the CENSUS and PROPUBLICA keys would not
flip certification.**

## The path to certification (maintainer release-cut)

Per `docs/RESUMPTION_CHECKLIST.md`, the flip is an explicit manual action. All of the following must
hold, after which the maintainer edits the status files **and the CI assertions in the same PR**:

1. Structural preflight green (`run_all.py --only-setup --strict-preflight` exit 0).
2. `moneysweep.runtime.validation_gates` shows `source_coverage_rate ≥ 0.85` with the required sources
   materialized — which requires materializing `cor3`, `hud_drgr_authorized`, `oficina_contralor`
   (portal/manual acquisition) and completing the partials.
3. R5 validation gates pass on real data without `--allow-failed`.
4. Risk-signal gates exit 0.
5. Federation conformance fixture fresh.
6. Full test suite green at the coverage floor.
7. size-guard green / history purge done.
8. Lineage + provenance complete for every promoted master.

Then, and only then, the runtime gate's `unique_entities ≥ 100` / `data_layers ≥ 8` / no-fixture
conditions will also be satisfied by the real data, and the status can be cut to
`PARTIAL_PRODUCTION` → `PRODUCTION_VALIDATED`.

## Scope note

This document is descriptive. It intentionally does **not** modify the CI production lock, the gate
code, or the status files. Performing the actual release-cut is a separate, explicitly-authorized
maintainer action — not something an automated change should do on its own.
