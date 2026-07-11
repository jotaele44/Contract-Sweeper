# Dropzone: usaspending_prime

USAspending bulk-export slices (e.g. the 2026-07-07 PR slices and the ~175MB bulk-award-export archive). Inventory-first lane: record query filters and date windows per file, then deduplicate against the committed masters on award/transaction identifiers before any merge. Ledger gap GAP-008.

- **Consumer:** `scripts/deduplicate_master.py (after inventory)`
- **Run after dropping files:** `see docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md (inventory before ingest)`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
