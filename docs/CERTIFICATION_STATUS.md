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
`reports/materialization_coverage_audit.json`: `committed_ci_view.fully_materialized = 8`,
`coverage_rate ≈ 0.056` — versus `local_truth_summary.materialized_any_data = 15` after a keyed local run.

### 3. Coverage gate — `moneysweep/runtime/validation_gates.py`
Required-source coverage must be ≥ 0.85. The denominator is only the **`required: true`** sources
(14 of them), not all 99 automatable sources. Currently `required_fully_materialized = 6 / 14 ≈ 0.43`.
The specific unmet required sources are **`cor3`, `hud_drgr_authorized`, `oficina_contralor`** (all
`not_materialized`), plus partials (`usaspending_prime`, `sam_entities`, `lda`). These are
portal/manual/JS-gated — they are **not** API-key sources, so no key unlocks them.

## What the keyed live run did — and did not — do

The keyed materialization run (documented in `docs/ROAD_TO_100.md`) materialized **FRED (2,138 rows),
EIA (620), FAC municipal single audits (785), FEC committees (86)** — real data against live APIs —
raising `materialized_any_data` from 11 → 15. This is genuine progress, but it does **not** move the
production gate, because none of those four is one of the unmet *required* sources in the coverage
denominator.

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
