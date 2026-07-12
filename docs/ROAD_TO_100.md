# Road to 100%

A leverage-ordered ledger of what stands between `moneysweep-pr` today and a
fully materialized, production-certified federation member. Counts are taken
from the authoritative live registry snapshot in
`reports/materialization_readiness.json` (schema `r5_readiness_v1`), not from
historical narrative.

## Current completion ~75%

The pipeline, federation contract, test harness, and CI are essentially
complete. The remaining 25% is dominated by **data materialization and
network-gated certification**, not by missing code. Every automatable source is
wired and ready; what is left is (a) running them against live endpoints with
credentials, (b) hand-ingesting the manual-export tranche, and (c) finishing the
entity-dedup chain.

## Live materialization — verified this session (keyed run)

With operator-supplied API keys and outbound egress via the environment proxy, the key-gated
producers were run against their **live** endpoints. Keys were used as environment variables only
and never committed — the pre-commit `scripts/scan_for_secrets.py` gate is clean (0 findings). Raw
CSVs stay gitignored under `data/**` by design; the tracked evidence is
`reports/materialization_coverage_audit.*`, which now records the materialized rows.

| Source | Producer | Result |
|---|---|---|
| FRED (PR macro time series) | `download_fred.py` | **2,138 rows**, 8/8 series — OK |
| EIA (PR power sector) | `download_eia.py` | **620 rows**, 5/5 series — OK |
| FAC (municipal single audits) | `download_fac_municipal.py` | **785 rows** — OK |
| FEC | `download_fec.py` | live (HTTP 200) but long-running; not fully captured this pass |
| SAM exclusions | `download_sam_exclusions.py` | live but long-running; not fully captured this pass |
| OpenStates (legislative canonical) | `fetch_legislative_canonical_sources.py` | ran; 0 rows (SUTRA fallback / query tuning needed) |
| LDA | `fetch_lda_gov.py` | reachable anonymously (HTTP 200); supplied token invalid, so anonymous access is used |
| HIGHERGOV | `fetch_highergov_api.py` | 403 — supplied key carries stray wrapping quotes; needs re-issue |

`materialized_any_data` in the coverage audit rose **11 → 14**. Still key-blocked (keys not supplied
or invalid): `CENSUS_API_KEY`, `PROPUBLICA_API_KEY`; the `NREL` host is blocked at the proxy. Full
production certification of all 99 automatable sources remains the larger, longer run.

## Done

- **~24K LOC of core pipeline** (registry-driven `run_all.py`, 82 wired producer
  scripts, adapters, validation, federation layer). Whole-repo Python is much
  larger (~140K LOC incl. tests, generated reports, and vendored tooling);
  `scripts/` + `moneysweep/` + `run_all.py` measure ~104K LOC.
- **Test baseline 1229 passed / 5 skipped / 0 failed** on the last full green run
  (post-#144 materialization-readiness gate). The suite defines 1888 `def test_`
  functions across `tests/`.
- **32 CI workflows** under `.github/workflows/`.
- **Complete `federation.json`** — schema, program id, active vector, source
  truth, hub-callable commands, canonical outputs, Tranche B scope, and the
  federation readiness gate are all populated.
- **144 sources in the live registry**; **99 automatable sources, all 99 ready**
  (`automatable_ready == automatable_total == 99`). The remaining 45 are queued
  and deliberately excluded: 38 manual_export, 2 scraper_needed, 2 deferred_stub,
  3 semantic_duplicate, 0 broken_producer.
- **Source-registry rewire complete** — all producer_script paths point at
  `scripts/`, 0 optional sources archived.
- **Strict preflight** classifies all sources with 0 structural errors and no
  live network or producer execution.

## Remaining — code (closed in this PR)

1. **ACT/ACUDEN dropzone reconciliation.** The `act`/`acuden` `SourceSpec`s in
   `scripts/source_intake_tranche_b.py` share one dropzone
   (`data/raw/act_transition/`) whose committed extract
   (`transition_contracts_extracted.csv`, 1803 rows = 656 `ACT_2020` + 1147
   `ACUDEN_2024`) carries **both** datasets in a `source_dataset` column. The
   dropzone path itself was already correct (fixed in #370), but the controller
   had no per-dataset partition — each spec would ingest all 1803 rows and
   mislabel the other source's rows — and the column map did not recognize the
   extract's actual headers (`contract_number`, `amount_numeric`, `transition_year`,
   `start_date_raw`, `service_type`, …). This PR adds a `dataset_filter` to
   `SourceSpec` (ACT→`ACT_2020` → 656 rows, ACUDEN→`ACUDEN_2024` → 1147 rows) and
   extends `LOCAL_CONTRACT_MAP` so real fields populate.
2. **`.gitignore` allow-list** for the new operator dropzones
   `data/raw/Cabilderos/**.csv`, `data/raw/Donaciones/**.csv`, and the
   `data/raw/reference/donantes_lookup/` tree (folder README tracked; binary
   xlsx kept out by policy — see note below).
3. **Pandas-free unit test.** Path-resolution and dataset-partition logic were
   split into stdlib-only `scripts/source_intake_paths.py`; new
   `tests/test_source_intake_paths.py` exercises dropzone discovery and the
   ACT/ACUDEN reconciliation without importing pandas.

> Note on the allow-list: the actual Cabilderos roster / Donaciones / donantes
> xlsx files described in `reports/current_status.json` were staged in a
> different sandbox and are **not present in this clone** (only `README.md` and
> `.gitkeep` exist in those dirs). The allow-list is therefore forward policy —
> it makes the CSVs trackable when placed — and commits no large or binary blob
> here. The donor-lookup exports are binary xlsx and remain intentionally
> untracked.

## Remaining — data / network-blocked

These cannot be closed offline; they need live HTTPS, credentials, or a
dependency absent from the no-network sandbox.

- **Production certification** needs live HTTPS reachability plus API keys to
  materialize the 99 ready sources. Registry-required keys (13 sources across 9
  key names): `CENSUS_API_KEY`, `EIA_API_KEY`, `FAC_API_KEY`, `FEC_API_KEY`,
  `FINANCIALDATA_API_KEY`, `FRED_API_KEY`, `HIGHERGOV_API_KEY`,
  `OPENSTATES_API_KEY`, `SAM_API_KEY`.
- **Tranche B manual ingestion** (`ACQUIRED_NOT_INGESTED`): DCAA active
  contractor listings (FY2007 / FY2012 / FY2013), PRASA completed projects, PRASA
  FY2024 Consulting Engineer report, and Federal LDA registrants — no files in
  the expected dropzones. Parser + canonical output + schema validation +
  regression tests must all pass before any is `fully_materialized`.
- **PR2.5 / PR2.6 → PR3 entity-dedup chain.** The entity-gate branches must be
  reconciled against latest `main` before PR3 deduplication/entity integration
  can run.
- **2 scraper stubs** remain (`scraper_needed`): `hacienda_sut_ivu` and
  `pr_act_154_excise`.
- **81-page Abril-18-2026 cabilderos registry PDF**
  (`Registro_de_cabilderos_Abril_18_2026_2.pdf`, ~7.9 MB) — the authoritative
  full lobbyist snapshot — cannot be parsed here; Claude's multi-page PDF path
  needs `poppler-utils` (`pdftoppm`), absent and not installable under the
  no-network rule. The March-2025 roster (70 registrations) plus 23 later
  certificate-only entries were already placed and structurally validated.

## Leverage-ordered checklist

Ordered by unlock value per unit of effort.

1. **[data] Provision the 9 API keys** → flips all 13 key-gated sources and lets
   the 99 ready automatable sources actually materialize. Single highest-leverage
   action; unblocks production certification.
2. **[data] Live-HTTPS certification run** of the 99 ready sources once keys are
   in place → moves `production_status` off `NON_PRODUCTION_DIAGNOSTIC`.
3. **[code] Reconcile PR2.5/PR2.6 onto main, then run PR3 dedup** → unblocks
   entity integration, the largest remaining code milestone.
4. **[data] Ingest the Tranche B manual exports** (DCAA ×3, PRASA ×2, Federal
   LDA) → drops the manual_export queue from 38 and closes the
   `ACQUIRED_NOT_INGESTED` backlog. ACT/ACUDEN are already extracted and, after
   this PR, correctly partitioned.
5. **[data] Parse the Abril-2026 cabilderos PDF** in an environment with
   `poppler-utils` → replaces the March-2025 roster snapshot with the
   authoritative registry.
6. **[code] Implement the 2 scraper stubs** (`hacienda_sut_ivu`,
   `pr_act_154_excise`) → clears the `scraper_needed` queue.
7. **[data] Run the Donaciones ingest end-to-end** once pandas is available
   (extractor already extended for the previously-unmapped columns).
