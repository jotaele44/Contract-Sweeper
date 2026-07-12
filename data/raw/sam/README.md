# Dropzone: sam_entities

SAM.gov public monthly extracts (SAM_PUBLIC_MONTHLY_V2_*.dat, ~1.1 GB). Bulk extracts are the correct universe source — never per-entity API paging (capped). Override location with SAM_BULK_DIR or --dat. Ledger gap GAP-007.

- **Consumer:** `scripts/ingest_sam_bulk.py`
- **Run after dropping files:** `python3 scripts/ingest_sam_bulk.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
