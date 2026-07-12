# Dropzone: oficina_contralor

Oficina del Contralor audit/investigation-report exports (CSV/xlsx). Separate lane from OCPR contracts. Interim manual lane; the scraper (scripts/scrape_iapconsulta.py) is the automated path. Ledger gap GAP-005.

- **Consumer:** `scripts/ingest_contralor.py`
- **Run after dropping files:** `python3 scripts/ingest_contralor.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
