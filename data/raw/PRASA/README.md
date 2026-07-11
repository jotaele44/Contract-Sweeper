# Dropzone: prasa

PRASA manual exports: contracts, CER, CIP, rate/revenue data. Completed-projects exports go in the completed/ subdirectory.

- **Consumer:** `scripts/source_intake_tranche_b.py --sources prasa_cer`
- **Run after dropping files:** `python3 scripts/source_intake_tranche_b.py --sources prasa_cer`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
