# Financial & Political Source Audit — Consolidated Snapshot

**Date:** 2026-07-07 · **Scope:** repo-wide · **Program:** Puerto Rico public-money intelligence (`moneysweep-pr`)
**Mode:** read-only re-projection of the live registry + existing coverage reports. No network producers were run; no registry or CI-view report was modified.

**Reproduce:**
```bash
python3 scripts/build_financial_political_audit_20260707.py   # per-source needs + remediation → .csv
# underlying ledgers (regenerate in-memory; canonical): scripts/build_financial_source_audit.py,
#   scripts/gap_analysis_builder.py, scripts/build_source_recovery_matrix.py
```
**Machine-readable companions:**
[`financial_political_source_audit_2026-07-07.csv`](financial_political_source_audit_2026-07-07.csv) ·
[`financial_political_coverage_gaps_2026-07-07.csv`](financial_political_coverage_gaps_2026-07-07.csv)

---

## 1. Are we at 100%? — **No.**

The answer is **no on two independent axes**, and they must not be conflated:

| Axis | Question | Where we are |
|---|---|---|
| **Coverage / wiring** | Is every source declared and wired to a producer? | **High but not complete** — 137 of 142 sources are wired with **0 structural defects**, but ~37 are queued behind manual files/scrapers and **9 real datasets aren't in the registry at all** (fresh 2026-07-07 gap analysis, §6; the audit ledger's `not_considered` bucket carries only the 5-row legacy backlog). |
| **Materialization** | Do the wired sources actually hold the data? | **Low** — committed/CI view reads **0%**; even locally only **~7 sources hold bulk data**. Of 14 **required** sources, only **5 carry genuine bulk data**. |

"Ready to run" (97/97 automatable per `reports/materialization_readiness.json`) is **not** "materialized." Readiness is a static import/entrypoint check; with outbound HTTPS blocked in this environment (403), no producer can fetch data here, so live-API correctness is unverified. The two axes are the whole story: **the pipeline is well-built; it is not yet filled.**

---

## 2. Registry drift (a finding in itself)

The "how many sources" number disagrees across artifacts because the registry has grown and the ledgers were regenerated on different dates:

| Artifact | Count | What it is |
|---|---|---|
| `registries/source_registry.json` (raw base) | **140** | hand-maintained base definitions |
| `load_source_registry()` (base + `source_registry_extensions/` + `_overlays/`) | **142** | **authoritative loaded registry** (adds 2 NARA deferred stubs + a legislapr overlay) |
| `reports/source_registry_status.csv` / `source_recovery_matrix.csv` | **142** | agree with the loader |
| `reports/current_status.json` → `materialization_readiness_truth` | **136** | **stale** snapshot |
| `reports/financial_source_audit.md` (committed) | 136 / "queued_scraper 15" | **stale** — regenerating today yields 142 / queued_scraper **2** |

**Source of truth going forward:** `load_source_registry()` = **142**. Regenerate status with `scripts/gap_analysis_builder.py`. The committed `financial_source_audit.md` is stale (it predates the scraper→automatable promotions in PRs #341–#348); this snapshot uses freshly regenerated numbers.

---

## 3. To what extent is each source implemented — the buckets

Freshly regenerated `scripts/build_financial_source_audit.py` over the live 142-source registry (+5 not-considered = 147 audit rows). 134 are financial money-flow sources; 8 are supporting/reference (entity resolution, archival, commercial enrichment).

| Bucket | All | What each source in it needs to be fully prepared |
|---|--:|---|
| `wired_materializing` | 2 | Nothing — producing output on disk now. |
| `wired_offline_ready` | 3 | A run; materializes from a **committed input** (no key/network). |
| `wired_ready_unmaterialized` | 84 | **Outbound HTTPS egress + a run** (sandbox blocks with 403). |
| `wired_needs_key` | 11 | **API key** then a run (see key list below). |
| `wired_not_set_to_materialize` | 5 | Design decision — deferred stub / semantic duplicate; produces nothing by design. |
| `queued_manual` | 35 | **Operator drops the export file**, then run the parser/ingest. |
| `queued_scraper` | 2 | **Build a scraping adapter** (`hacienda_sut_ivu`, `pr_act_154_excise`). |
| `broken` | 0 | — none. |
| `not_considered` | 5 | **No registry entry** — this is the pre-existing 5-row `financial_source_coverage_gaps.csv` backlog. The fresh 2026-07-07 gap analysis (§6) supersedes it with **9** verified-absent datasets (the same 5 plus 4 new, incl. the two political disclosure surfaces). |

**"Needs" rollup** (from `financial_political_source_audit_2026-07-07.csv`): egress 84 · operator_file 35 · api_key 11 · design_decision 5 · registry_intake 5 · run_offline 3 · none 2 · scraper 2.

**The 11 key-gated sources** need one of: `FEC_API_KEY` (×2), `FAC_API_KEY` (×2), `SAM_API_KEY` (×2), `CENSUS_API_KEY`, `EIA_API_KEY`, `FRED_API_KEY`, `OPENSTATES_API_KEY`, `FINANCIALDATA_API_KEY`. Templates in `.env.example`.

---

## 4. The required critical path (14 sources)

`required_coverage_rate = 0.6429` → **9 of 14** required sources carry *some* data; only **5 carry bulk data**. From `reports/source_registry_status.csv` (pipeline_status) cross-checked against the on-disk materiality tiers in `reports/financial_sources_materialization_audit_2026-06-10.md`:

| Source | pipeline_status | on-disk reality | how to finish |
|---|---|---|---|
| `usaspending_prime` | partial | bulk ✓ (68,681 rows) | produce the missing 2nd output `pr_all_awards_master.csv` → flips to full |
| `fema_pa_openfema_v2` | full | bulk ✓ (~21,868, ~100% of universe) | done |
| `fec` | full | bulk ✓ (16,637) | done |
| `hud_cdbg_dr_public` | full | bulk ✓ (7,700) | done |
| `usaspending_subawards` | full | bulk ✓ (7,125) | done |
| `emma_bonds` | full | **seed** (35) | run EMMA/MSRB producer at scale |
| `sam_entities` | partial | **seed** (50) | set `SAM_API_KEY`, run enrichment |
| `lda` | partial | **seed** (14 ≈ 0.5% of universe) | replace dry-run fixture with live LDA pull |
| `fsrs_subawards` | full | 0 (semantic dup of subawards) | design decision — keep or retire |
| `cor3` | not | 0 (header-only) | operator file / COR3 export |
| `oficina_contralor` | not | 0 | operator manual export |
| `pr_cabilderos` | not | 0 | operator manual export (cabilderos registry PDF) |
| `hud_drgr_authorized` | not | 0 | credentialed manual export |
| `prasa` | not | 0 | operator manual export (CER/CIP) |

**Bottom line for required sources:** 5 bulk, 3 seed-level, 6 empty/pending.

---

## 5. Political / campaign-finance / lobbying / legislative coverage

The user asked specifically about the political datasets. There are **12** political/influence sources; **only FEC is truly materialized**:

| source_id | family | required | materialization | needs to finish |
|---|---|---|---|---|
| `fec` | political_finance | yes | **full (16,637)** | `FEC_API_KEY` to refresh |
| `lda` | lobbying | yes | partial (14 ≈ 0.5%) | egress run — replace dry-run fixture w/ live pull |
| `pr_cabilderos` | lobbying | yes | not | operator file (PR lobbyist registry PDF) |
| `contralor_electoral` | political_finance | no | not | operator file (OCE — PR campaign finance) |
| `donaciones_pr` | political_finance | no | not | operator file |
| `fec_committees` | political_finance | no | not | `FEC_API_KEY` + egress run |
| `follow_the_money` | political_finance | no | not | run offline (committed bridge input present) |
| `legislapr_discovery` / `legislapr_sessions` / `legislative_fiscal_link_candidates` / `osl_sutra_crosswalk` | territorial_legislation | no | not (×4) | egress run |
| `legislative_canonical_sources` | territorial_legislation | no | not | `OPENSTATES_API_KEY` + egress run |

**Political reading:** federal contributions (FEC) are well-covered; **PR territorial campaign finance (OCE/contralor_electoral), lobbying (LDA + PR cabilderos), and all 5 legislative-linkage sources are seed-level or empty.** This is the weakest domain relative to its declared scope.

---

## 6. Overlooked datasets — fresh gap analysis (2026-07-07)

**9** candidates, each **verified absent** from the live 142-id registry and confirmed against a primary source via web research today. This supersedes the audit ledger's 5-row `not_considered` backlog (§3): the 5 legacy items (`gsa_iolp_real_property`, `hmda_ffiec`, `prac_pandemic_oversight`, `pr_arbitrios_excise`, `pr_ui_trust_fund`) are all included, plus **4 new** — the two political disclosure surfaces, `faa_aip_grants`, and `ffiec_call_reports`. Full rows in [`financial_political_coverage_gaps_2026-07-07.csv`](financial_political_coverage_gaps_2026-07-07.csv).

| candidate | category | flow captured | access | priority |
|---|---|---|---|---|
| `gsa_iolp_real_property` | financial | GSA-leased federal property in PR (lease $ to PR landlords) | Data.gov bulk CSV, `state=PR` | **P1** |
| `us_congress_financial_disclosure` | **political** | US House/Senate member disclosures + STOCK Act trades | House Clerk bulk XML + Senate eFD | **P1** |
| `oeg_financial_disclosure` | **political** | PR public-official financial disclosures (~9–10k officials) | OEG CDPE+ portal (scrape) | **P1** |
| `hmda_ffiec` | financial | Mortgage-origination flows in PR | FFIEC combined modified-LAR bulk | P2 |
| `pr_ui_trust_fund` | financial | PR unemployment-insurance trust fund (DOL ETA-5159) | DOL ETA / Data.gov bulk | P2 |
| `pr_arbitrios_excise` | financial | PR excise taxes (alcohol/tobacco/fuel/cement…) | Hacienda SC-2225 (scrape) | P2 |
| `prac_pandemic_oversight` | financial | PRAC pandemic-spending crosswalk + IG findings | PandemicOversight.gov exports | P3 (mostly overlap) |
| `faa_aip_grants` | financial | FAA Airport Improvement grants to PR airports | FAA AIP history | P3 (overlaps usaspending) |
| `ffiec_call_reports` | financial | Institution-level bank Call Reports (PR banks) | FFIEC CDR bulk | P3 (overlaps fdic) |

**Highest-leverage new work:** the two **political** disclosure surfaces (US Congress + PR OEG) — the registry captures campaign/lobbying money but not officials' *personal* finances — and **GSA IOLP** (a federal-money-into-PR flow procurement feeds miss).
**Caveat on `oeg_financial_disclosure`:** OEG restricted its public summary in ~2024 (per-transaction amounts hidden, pre-2020 reports removed), so only aggregate totals are currently public; full access may require FOIA.

---

## 7. Three bookkeeping gaps that suppress the reported %

From `reports/financial_sources_materialization_audit_2026-06-10.md` (still current — these are structural, not date-sensitive). Fixing them is bookkeeping, not data acquisition, and would move the reported number sharply without pulling a single new row:

- **Gap A — gitignore hides the data.** `.gitignore` uses `data/**` deny-all, then re-includes only *directories* (`!…/**/`), never the files, so `data/staging/processed/*.csv` is invisible to any run against committed state. That is why every committed report reads **0%** while the working tree holds ~740k rows. **Fix:** re-include the files, or commit a row-count+sha256 manifest (partly present in `data/manifests/`).
- **Gap B — registry orphans.** **612,557 rows across 39 files** are real data that no registry source claims (`pr_grants_master.csv` 461k has no declaring source; `pr_ofac_sdn.csv` is a path mismatch vs `ofac_sdn`). Registry-accounted coverage is only ~17% of on-disk rows. **Fix:** declare `pr_grants_master.csv` as an assistance output and correct the `ofac_sdn` path → ~80% accounted immediately.
- **Gap C — seed counts as full.** Gap-analysis treats `min_rows=1` as "materialized," so 14-row seeds (`lda`, `emma_bonds`) count as fully materialized. **Fix:** apply the materiality tiers (bulk ≥1k / moderate / seed / empty) already computed in the coverage audit.

---

## 8. What to do next (priority order)

1. **Materialize the 84 egress-ready + 11 key-gated sources** in an egress-enabled environment (set the 8 keys, `python3 run_all.py --strict-preflight` + `python -m moneysweep.query --source <id>`). This is the single biggest lever — most of the pipeline is one networked run away from data.
2. **Complete `usaspending_prime`** (missing `pr_all_awards_master.csv`) — flips the largest required source partial → full.
3. **Fix the bookkeeping (Gaps A/B/C)** so the repo can *report* its own materialization honestly.
4. **Fill the political weak spot:** live LDA pull, PR cabilderos + OCE/contralor_electoral ingestion.
5. **Tranche B manual drops:** PRASA CER/CIP, cabilderos, DCAA, ACT transition, HUD DRGR (35 `queued_manual`).
6. **Intake the P1 overlooked sources:** `gsa_iolp_real_property`, `us_congress_financial_disclosure`, `oeg_financial_disclosure`.

---

## 9. Provenance & limits

- **Deterministic & offline.** Every count reuses the existing gate logic (`build_source_recovery_matrix._classify`, `pipeline_preflight.classify_source_readiness`, `gap_analysis_builder`) over the live registry — it cannot drift from the materialization gate. The new generator only re-projects; it defines no new classifier.
- **No committed report was overwritten.** The canonical ledgers were regenerated in-memory to read fresh numbers, then the working tree was restored; only the three new dated deliverables are added. The CI-view `gap_analysis_report.json` 0% guardrail is preserved.
- **Egress blocked here.** This snapshot audits and plans materialization; it did not pull the egress/key-gated sources. The §6 web research used the read-only agent proxy.
- **On-disk reality figures** (7 bulk sources, 740k rows, 612k orphans) are carried from `financial_sources_materialization_audit_2026-06-10.md`, whose line-vs-record caveats still apply.
