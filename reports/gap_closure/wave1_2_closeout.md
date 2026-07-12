# Gap-Closure Waves 1–2 Closeout — Baseline vs. Post

Frozen point-in-time closeout for the gap-closure program's first tranche
(Wave 1 truthful measurement + executable Wave 2). Baseline artifacts in this
directory are the *before*; this file records the *after* and the delta.
Baseline commit: `d186e518f8ebb55d6151b791ef1327f40ea428ed` (see
`baseline_manifest.json`).

## Headline delta

| Measure | Baseline | Post wave2 | Change |
| --- | ---: | ---: | --- |
| Committed source-count surfaces agreeing on 144 | 2 of 5 | 5 of 5 | phase1a + CI drift gate |
| Fully materialized (committed manifest view) | 6 | 8 | ACT + ACUDEN (wave2a) |
| Coverage rate (row-agnostic, legacy) | 0.0417 | 0.0556 | +2 sources |
| Sources with coverage contracts | 0 | 20 | phase1b |
| `validated_complete` (contract-evidenced) | — (concept absent) | 2 | ACT + ACUDEN |
| `certified_complete` | — (concept absent) | 0 (8 provisional) | honest: no source is reconciled yet |
| Ledger gaps resolved / open | 0 / 19 | 9 / 10 | see below |
| Declared dropzones existing on disk | ~5 of 40+ | all | wave2b + consistency test |

## What "8 fully materialized" now means

Under the repaired control plane the number is **labelled, not inflated**:
of 144 sources, 133 are `empty`, 1 is `seed`, 8 are `substantial`
(bulk rows, no contract evidence), and 2 are `validated_complete`
(ACT/ACUDEN: measured universes 656/1,147, ~100% field completeness,
0–1.1% duplicate rate, monetary totals recorded — $3.66B / $252.6M).
No source is `certified_complete`, because none has monetary
reconciliation against an official reference total yet — that is Wave 3+
work, and the taxonomy now says so instead of hiding it.

## Ledger state (details in unresolved_gap_ledger.csv)

Resolved (9): GAP-009/010 (ACT/ACUDEN ingested), GAP-012/013/014 (count
drift), GAP-015 (dead intake paths), GAP-016 (policy key bug), GAP-017
(phantom dropzones), GAP-018 (stale runbook figures).

Open (10): GAP-001..008 (the eight operator-held datasets — dropzones and
runbook are ready; the files must be re-dropped), GAP-011 (orphan
`pr_grants_master.csv`), GAP-019 (the 2026-06-17 coverage audit remains
non-reproducible as a historical artifact; regenerated audits now record a
portable root).

## Rescoring the remaining work (program step 4)

Post-ingestion reality check against the program's expected readiness:

- **Wave 1 exit ("truthful measurement") — met.** Counts reconcile and are
  CI-gated; `min_rows: 1` can no longer produce a complete label; fixtures
  cannot certify; coverage denominators are explicit (18 of 20 contracts
  still need their universe measured — `authoritative_universe_total: null`
  evaluates `unverifiable`, never passing).
- **Wave 2 exit ("no acquired file remains un-ingested") — met for what this
  clone actually holds.** ACT/ACUDEN was the only acquired-not-ingested
  corpus physically present; it is ingested with committed provenance. The
  other seven datasets were *acquired on the operator machine but never
  preserved into the repo* — reclassified from "ingest" work to "re-drop"
  work (GAP-001..008, turnkey via docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
- **Biggest lever for the next tranche:** the operator re-drops (SAM bulk,
  Donaciones, Cabilderos, COR3, FPDS — hours, not days), then Wave 3
  required-source closure and the first universe probes
  (`audit_materialization_coverage.py --probe`) to fill the null
  denominators in `registries/coverage_contracts.yaml`.
