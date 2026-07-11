# Dropzone: fpds_report_builder

FPDS / USASpending Report Builder Excel exports (Report Builder FY20-24 *.xlsx). The ingester scans data/raw/ and one level down, so files dropped here are found. Ledger gap GAP-006.

- **Consumer:** `scripts/ingest_report_builder.py`
- **Run after dropping files:** `python3 scripts/ingest_report_builder.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
