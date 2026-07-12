# Dropzone: donaciones_pr

CEE / CEEPUR campaign-donation CSV exports (e.g. Donaciones_20260320.csv, 4,686 rows). Manual export from ceepur.org. The 2026-07-09 operator pass placed this file here on another machine but it was never git-tracked — re-drop it to close ledger gap GAP-001.

- **Consumer:** `scripts/ingest_donaciones.py`
- **Run after dropping files:** `python3 scripts/ingest_donaciones.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
