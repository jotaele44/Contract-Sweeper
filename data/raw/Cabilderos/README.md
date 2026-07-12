# Dropzone: pr_cabilderos

PR lobbyist-registry files: pr_cabilderos_roster_2025-03-26.csv (1,175 lobbyist-client rows), pr_cabilderos_certifications_only.csv (23 rows), and the authoritative Registro_de_cabilderos_Abril_18_2026_2.pdf (81 pages, needs poppler to parse). Ledger gap GAP-002.

- **Consumer:** `scripts/ingest_cabilderos.py`
- **Run after dropping files:** `python3 scripts/ingest_cabilderos.py`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
