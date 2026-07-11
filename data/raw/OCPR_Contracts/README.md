# Dropzone: ocpr_contracts

OCPR consultacontratos.ocpr.gov.pr contract-registry xlsx snapshots. Interim bounded snapshots only — record the snapshot date and portal filters in the filename; the full corpus comes from the scraper (scripts/scrape_ocpr_contracts.py). Ledger gap GAP-004.

- **Consumer:** `scripts/ingest_ocpr_contracts.py`
- **Run after dropping files:** `python3 scripts/ingest_ocpr_contracts.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
