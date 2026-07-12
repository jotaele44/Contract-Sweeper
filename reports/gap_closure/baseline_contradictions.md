# Gap-Closure Baseline — Contradiction Ledger

Baseline commit: `d186e518f8ebb55d6151b791ef1327f40ea428ed`. Live registry truth at this commit:
**144 sources** (`source_ids_sha256 6c881d36265875cc…`).
Each finding cites the committed evidence. Resolution targets reference the
gap-closure commit sequence; open items live in `unresolved_gap_ledger.csv`.

## 1. Four committed source counts disagree (143/141/136/144)

| Surface | Total sources | Automatable |
| --- | ---: | ---: |
| live registry / `reports/materialization_readiness.json` | 144 | 99 |
| `federation.json` → `source_truth` | 143 | 98 |
| `reports/federation_source_status_reconciliation.json` | 141 | 95 |
| `reports/current_status.json` → `materialization_readiness_truth` | 136 | — |

`reports/current_status.json` contradicts itself: `source_registry_current`
says 144 while `materialization_readiness_truth` says
136. Only `materialization_readiness.json` and the
`source_registry_current` block are test-pinned; the other three surfaces are
frozen snapshots with no gate. **Resolved by phase1a** (values + drift gate).

## 2. "6 fully materialized" vs "58 fully materialized" — both committed

`reports/gap_analysis_report.json` (2026-07-10) reports
**6 fully materialized of 144**
(coverage 0.0417), computed against a clean checkout plus the
committed staging manifest. `reports/materialization_coverage_audit.json`
(2026-06-17T19:52:11.085000+00:00) reports **58 of
136** — computed against the operator's working tree,
where the gitignored masters exist, and against an older 136-source registry.
Different filesystem truth AND different denominator, presented side by side
with no reconciliation note. **Addressed by phase1c** (regeneration at this
commit + explicit view labels).

## 3. The coverage audit is not reproducible from this repo

`reports/materialization_coverage_audit.json` records
`root: /Users/jotaele/Developer/Contract-Sweeper` — an operator-machine path. None of its
`local_rows` figures can be recomputed from this clone. **Addressed by
phase1c** (regenerate against the repo tree; local view separated from
operator view).

## 4. 104,280 orphan rows invisible to the registry

The same audit records `orphan_rows: 104280` — `pr_grants_master.csv` rows on
the operator disk claimed by **no** registry source (`inventory_processed_files`
docstring documents the drift class). Real data, structurally invisible to
registry-driven accounting. **Open: GAP-011.**

## 5. current_status says Donaciones/Cabilderos were "placed" — not in git

`reports/current_status.json` (2026-07-09 pass) records
`data/raw/Donaciones/Donaciones_20260320.csv` (4,686 rows) and
`data/raw/Cabilderos/pr_cabilderos_roster_2025-03-26.csv` (1,175 rows) as
placed and validated — but the same file's blocked-items note admits those
directories are **not covered by .gitignore's allow-list**, so the files were
never tracked and are absent in this clone. Acquisition happened; preservation
did not. **Open: GAP-001, GAP-002 (dropzones scaffolded by wave2b).**

## 6. Governance: ingestion is both forbidden and the declared next step

`docs/BLOCKED_PHASES_AND_UNFREEZE_RULES.md` (R4.9Z era) lists "source
ingestion" as forbidden while paused; `reports/current_status.json` sets
`next_command: TRANCHE_B_MANUAL_SOURCE_INGESTION` and
`docs/TRANCHE_B_MANUAL_SOURCE_INGESTION_PREP.md` scopes ACT/ACUDEN as its P0.
Resolution adopted here: the gap-closure program executes the sanctioned
Tranche-B *diagnostic* path — offline materialization of operator-delivered,
already-committed files, no downloads, no production promotion;
`production_status=NON_PRODUCTION_DIAGNOSTIC` and `phase_7_8_blocked=True`
are untouched.

## 7. ACT/ACUDEN declared intake paths do not exist

`registries/source_registry.yaml` declares `manual_drop_dir:
data/manual/act_transition/` and `data/manual/acuden_2024/`;
`registries/manual_export_registry.yaml` mirrors them. Neither directory
exists; the acquired files actually live in `data/raw/act_transition/` and
`data/raw/Vigentes al Momento de Transición/`. Only the producer's committed-
extract fallback tier works. **Resolved by wave2a.**

## 8. Tranche-B intake script points at phantom dropzones

`scripts/source_intake_tranche_b.py` SOURCE_SPECS reference dropzones like
`data/raw/ACT Transition Contracts` that match nothing on disk and disagree
with `manual_export_registry.yaml`. **Resolved by wave2a/wave2b.**

## 9. Runbook quotes a registry three generations old

`docs/MATERIALIZATION_RUNBOOK.md` states 124 total / 68 automatable / 56
queued; live truth is 144 / 99 / 45. **Resolved by phase1a**
(replace frozen figures with a pointer to the generated report).

## 10. Manual-export policy inference reads the wrong key

`moneysweep/update_controller/policy.py::_manual_export_ids` looks for
`sources|manual_sources|entries` in `manual_export_registry.json`, whose real
top-level key is `manual_exports` — the function always returns empty, so
manual-export sources get no policy inference. **Resolved by wave2b.**

## 11. Queued-source breakdowns disagree by one

`reports/federation_source_status_reconciliation.json` records
`queued_excluded_total: 46` (manual_export 39);
`reports/materialization_readiness.json` records
`45` (manual_export 38). Same registry, different
snapshots. **Resolved by phase1a.**
