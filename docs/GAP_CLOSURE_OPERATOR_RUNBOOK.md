# Gap-Closure Operator Runbook — Closing the Absent-Dataset Gaps

This runbook makes each remaining `dataset_absent` gap in
`reports/gap_closure/unresolved_gap_ledger.csv` a turnkey operator action:
drop the file in its validated dropzone, run one command, verify, and flip the
ledger row. It complements (does not replace) `docs/MATERIALIZATION_RUNBOOK.md`
and `docs/MANUAL_SOURCE_OPERATIONS.md`.

**Governance:** all of this is diagnostic Tranche-B work
(`docs/TRANCHE_B_MANUAL_SOURCE_INGESTION_PREP.md`): operator-delivered files,
no automated credentialed scraping, no production promotion.
`production_status=NON_PRODUCTION_DIAGNOSTIC` and `phase_7_8_blocked=True`
stay as they are; promotion has its own gates (`docs/PRODUCTION_GATES.md`).

## Why these files are missing here

`reports/current_status.json` records that several datasets were placed and
validated on an operator machine (2026-07-09) but the files were never
git-tracked — `data/` is deny-all gitignored and the allow-list was
deliberately not extended for them. This runbook's dropzones are the tracked,
declared landing spots (`.gitkeep` + README committed; the data files
themselves stay untracked unless the operator adds an explicit allow-list
entry, subject to the 5 MiB size-guard).

## The loop (same for every dataset)

1. **Drop** the file(s) into the dropzone listed below (each has a README with
   filename patterns and expected columns, mirrored from
   `registries/manual_export_registry.yaml`).
2. **Run** the consumer command.
3. **Manifest**: record the ingest evidence —
   ```bash
   python3 scripts/build_staging_manifest.py          # merge mode: safe
   python3 - <<'EOF'
   from pathlib import Path
   from moneysweep.runtime.manifest_runtime import profile_file, write_per_source_manifest
   root = Path(".").resolve()
   sid, rel = "<source_id>", "<expected_output_path>"
   write_per_source_manifest(root, source_id=sid, files=[profile_file(root / rel, root=root, source_id=sid)])
   EOF
   ```
4. **Regenerate** reports:
   ```bash
   python3 scripts/gap_analysis_builder.py
   python3 scripts/build_source_recovery_matrix.py
   python3 scripts/audit_materialization_coverage.py
   python3 scripts/build_completeness_matrix.py
   ```
5. **Flip the ledger row** once the completeness matrix shows the source
   `acquired_ingested`:
   ```bash
   python3 scripts/build_gap_closure_baseline.py --update-ledger GAP-00X \
       --ledger-status resolved --resolved-by <commit-or-PR-ref>
   ```
6. **Commit** the manifests + regenerated reports (never the raw data files
   themselves unless the allow-list is deliberately extended).

## Per-dataset instructions

| Gap | Source | Dropzone | Consumer |
| --- | --- | --- | --- |
| GAP-001 | `donaciones_pr` | `data/raw/Donaciones/` | `python3 scripts/ingest_donaciones.py` |
| GAP-002 | `pr_cabilderos` | `data/raw/Cabilderos/` | `python3 scripts/ingest_cabilderos.py` |
| GAP-003 | `cor3` | `data/raw/COR3/` | `python3 scripts/ingest_cor3.py` |
| GAP-004 | `ocpr_contracts` | `data/raw/OCPR_Contracts/` | `python3 scripts/ingest_ocpr_contracts.py` |
| GAP-005 | `oficina_contralor` | `data/raw/Oficina del Contralor/` | `python3 scripts/ingest_contralor.py` |
| GAP-006 | `fpds_report_builder` | `data/raw/FPDS_Report_Builder/` | `python3 scripts/ingest_report_builder.py` |
| GAP-007 | `sam_entities` | `data/raw/sam/` | `python3 scripts/ingest_sam_bulk.py` |
| GAP-008 | `usaspending_prime` slices | `data/raw/USAspending_Slices/` | inventory first — see below |

Dataset-specific notes:

- **Donaciones (GAP-001).** Re-export from ceepur.org or re-drop
  `Donaciones_20260320.csv` (4,686 rows — the attested universe in the
  coverage contract). Validate amounts/dates; retain original CEE identifiers.
- **Cabilderos (GAP-002).** Three artifacts: the 2025-03-26 roster CSV (1,175
  lobbyist-client pairs), the certifications-only CSV (23 rows), and the
  authoritative April 2026 registry PDF (81 pages — parse in an environment
  with poppler; it is the coverage contract's universe reference). Keep
  registration snapshots reconciled, never merged blindly.
- **COR3 (GAP-003).** Classify each export as project / procurement /
  obligation / disbursement / contractor / status data and keep the grains in
  separate files. Link to FEMA disaster + project identifiers; never merge
  with FEMA PA records (dedup policy in the coverage contract).
- **OCPR contracts (GAP-004).** Interim bounded snapshots only: record the
  snapshot date and portal filters. The full corpus comes from
  `scripts/scrape_ocpr_contracts.py`; the coverage denominator must come from
  paginated portal counts, never the contract-ID range.
- **Contralor audits (GAP-005).** Keep separate from `ocpr_contracts`.
  Preserve report type, finding, entity, period, amount, recommendation.
- **FPDS Report Builder (GAP-006).** Drop `Report Builder FY20-24 *.xlsx`.
  After ingest, reconcile against USAspending (classify FPDS-only /
  USAspending-only / matching) before counting rows toward any total.
- **SAM bulk (GAP-007).** Monthly public extracts
  (`SAM_PUBLIC_MONTHLY_V2_*.dat`, ~1.1 GB — set `SAM_BULK_DIR` if stored
  outside the repo). Build the UEI/CAGE/legal-name index; validate PR-address
  filtering. Never rebuild the universe from per-entity API paging (capped).
- **USAspending slices (GAP-008).** Inventory before ingest: record each
  slice's query filters and date window, identify overlap with the committed
  masters, dedupe on award/transaction identifiers, THEN regenerate masters
  and manifests. Slices are increments to an existing lane, not a new corpus.

## What "done" means (per the coverage contracts)

A dataset is not complete because its CSV exists. The completeness matrix
(`reports/completeness_matrix.csv`) must show, for the source:
`acquisition_status=acquired_ingested`, `materialization_status=
fully_materialized`, and — once the denominator in
`registries/coverage_contracts.yaml` is measured — `coverage_status=
meets_contract`. `validated_complete` is unreachable without contract
evidence; `min_rows: 1` proves nothing.

## Update-controller note

`manual_export_registry.yaml` entries now drive file-drop trigger inference
(the registry key mismatch in `update_controller/policy.py` is fixed —
baseline contradiction 10). Adding a source to the manual-export registry
makes its update policy file-drop-triggered with the `expected_drop_dir` as
the watch path; removing it restores cadence/path-type inference.
