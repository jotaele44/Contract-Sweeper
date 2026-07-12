# Dropzone: cor3

COR3 Transparency Portal (recovery.pr.gov) xlsx exports: projects, obligations, disbursements. Keep project/procurement/obligation/disbursement grains as separate files — they are never merged. Ledger gap GAP-003.

- **Consumer:** `scripts/ingest_cor3.py`
- **Run after dropping files:** `python3 scripts/ingest_cor3.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
