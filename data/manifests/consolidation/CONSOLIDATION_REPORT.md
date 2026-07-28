# Financial Data Consolidation — moneysweep-pr

_Consolidated 2026-07-05. Scope: 100% of financial (and, per request, legislative) data across
`Contract Data/`, `Contract-Sweeper/`, `processed/`, and the archives, deduped, normalized, and
mapped into the `moneysweep-pr` repo._

## Authority model

- **`moneysweep-pr/`** — authoritative target (current repo).
- **`Contract-Sweeper/`** — beta version of moneysweep-pr; used only as a dedup source.
- **`Contract Data/data/`** and **`data.zip`** — an older (Jun-22) snapshot of the same pipeline; dedup source.

Rule applied: **the repo's existing files are never overwritten** — only missing gaps were filled.
Where the repo and a beta snapshot both had a file, the repo's copy won (10 curated files had drifted;
the repo's newer versions were kept).

## 1. Raw consolidation (into `data/raw/…`, git-ignored bulk)

**447 files / 1.24 GB** copied into the repo, deduped:

| Action | Files | Size |
|---|---|---|
| Gap-fill (pipeline files missing from repo, sourced from beta) | 395 | 1,027 MB |
| Loose drops → registry drop-dirs | 13 | 13.5 MB |
| Legislative (OpenStates + roster) | 39 | 195 MB |

Gap files landed in their original pipeline paths: `data/staging/raw/` (federal grant/loan/direct-recipient
FY downloads), `data/staging/processed/` (masters incl. the 256 MB `pr_all_awards_master.csv`),
`data/raw/sam/` (285 MB entity extracts), `data/staging/expansion/` (PR-filtered FPDS), `data/normalized/`.

Loose drops mapped to the repo's registered drop-dirs:

| File | → drop-dir | source_id |
|---|---|---|
| `Donaciones_20260320.csv` | `data/raw/Donaciones/` | donaciones_pr |
| OCE donor exports (×3) | `data/raw/OCE/` | contralor_electoral |
| `oficina del contralor … contratos.xlsx` | `data/raw/Oficina del Contralor/` | oficina_contralor |
| `DoD_Prime_Contractors_2013.xlsx` | `data/raw/Active Contractor Listing/` | dcaa_active_contractors |
| Report Builder FY20–24 + FY2018/19 procurement | `data/raw/fpds_report_builder/` | fpds_report_builder |
| `employer_data…`, `Contractor Index.rtf` | `data/raw/entity_resolution_aids/` | (new overlay) |
| `Puerto Rico Government (2024-2028).csv` | `data/raw/legislative/roster/` | legislative_openstates_pr |
| OpenStates PR bills (3 cycles) | `data/raw/legislative/openstates/` | legislative_openstates_pr |

## 2. FY2026 USASpending — PR filter

The 1.86 GB `FY2026_All_Contracts_Full` CSV (270 MB zip) was stream-decompressed and filtered:
**889,804 nationwide contract rows scanned → 1,157 Puerto Rico rows** kept (recipient state = PR **or**
place-of-performance state = PR) → `data/raw/usaspending/FY2026_All_Contracts_PR.csv` (2.5 MB). The full
archive was left in place; only the PR slice entered the repo.

## 3. Deduplication decisions

- **383.8 MB** of redundant bytes avoided — `Contract Data/` and `Contract-Sweeper/` were near-identical;
  each pipeline file was taken once (beta-repo copy preferred).
- **OpenStates bills** existed **three times** (loose folder ≡ `Archive.zip` ≡ loose `.zip`) — the complete
  loose folder was used; the two archives were not re-ingested.
- **`data.zip` (111 MB)** = the `Contract Data/data/` snapshot — not re-ingested (already covered).
- **OCE "Búsqueda de Donantes" xlsx** = renamed duplicates of the OCE folder exports — skipped by hash.
- **HigherGov municipal-awards PDF** = identical to the repo's copy — skipped.
- macOS junk (`.DS_Store`, `__MACOSX`, `._*`) excluded throughout.

## 4. Normalization → `data/staging/processed/` (the repo's schema)

Each source was run through its **own repo producer script** (Spanish→canonical header mapping), not hand-rolled:

| Source | Producer | Rows |
|---|---|---|
| CEE donations | `ingest_donaciones.py` | 4,579 |
| OCE campaign finance | `ingest_oce.py` | 6,480 |
| OCPR audits/contracts | `ingest_contralor.py` | 85 |
| DoD active contractors | `download_active_contractors.py` | 8,361 |
| FPDS Report Builder (PR-filtered) | `ingest_report_builder.py` | 238 ($1.74 B obligated) |
| Follow-the-Money (SF-133 …) | `ingest_follow_the_money.py` | 1,247 |

Two normalizations were needed so the producers would accept the files (data-side only — **no repo code changed**):
- **OCE** donor exports used headers `Nombre completo / Fecha de donación / Ciudad`; normalized CSVs with
  mapper-recognized headers were emitted, and the overlapping `2020-2026` export dropped in favour of the
  `2019-2026` superset.
- **FY_2019** procurement had a blank leading row that crashed the parser → normalized in place (2,922 rows);
  **FY_2018** `.xls` → clean `.xlsx` (409 rows).

`data/staging/processed/` now holds **120 master CSVs / 1,093,774 rows**; the source audit reports **0 broken sources**.

## 5. Canonical_v1 mapping

`canonical_v1` is the repo's **curated, evidence-backed graph seeded from `data/reference/`** — not a dump of
bulk staging. It was regenerated with the repo's own builders (`ingest_contracts`, `build_edges`,
`build_entity_master`, `build_person_master`, `bridge_canonical_v1_federation`). Bulk sources correctly
normalize into `staging/processed`; the canonical graph stays curated. The regeneration changed only 3
manifest timestamps (no curated data clobbered).

## 6. Manifests & registry

- `data/manifests/staging_masters.json` rebuilt — 120 files, 1,093,774 rows.
- `data/manifests/consolidation/consolidation_manifest.json` — machine-readable record of this run.
- `registries/source_registry_overlays/consolidated_2026_07_05.yaml` — registers the new dirs
  (usaspending FY2026 slice, legislative, entity-resolution aids).
- Provenance `README.md` in each new drop-dir.

## 7. Verification

- **Canonical integrity: clean** — 0 duplicate IDs and 0 unresolved `evidence_id` foreign keys across all 14
  canonical tables.
- **Copy integrity** — all 447 copies present and size-verified (byte-exact; large files tail-checksum matched).
- **Federation bridge** validates: 4,480 sources, 200 entities, 0 `not_yet_federated`.

## 8. Follow-ups (out of offline scope)

These need network access or API keys and were **not** fabricated:
- `usaspending_prime`, `sam_entities`, `fec_committees`, `sba_loans` etc. — API/credentialed pulls.
- The legacy `FY_2018 .xls` requires `xlrd` (absent from repo deps); its data is preserved as a clean `.xlsx`.
