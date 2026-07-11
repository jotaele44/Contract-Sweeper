# Dropzone: dcaa_active_contractors

DCAA active-contractor listing exports (registry manual_drop_dir).

- **Consumer:** `scripts/download_active_contractors.py`
- **Run after dropping files:** `python3 scripts/download_active_contractors.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
