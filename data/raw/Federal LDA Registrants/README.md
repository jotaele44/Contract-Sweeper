# Dropzone: federal_lda_registrants (tranche-B lane)

Federal LDA registrant exports for the offline tranche-B lane. The automated lda source (Senate LDA API) is separate and preferred.

- **Consumer:** `scripts/source_intake_tranche_b.py --sources lda`
- **Run after dropping files:** `python3 scripts/source_intake_tranche_b.py --sources lda`
- **Provenance:** keep original filenames where possible; record retrieval
  date and source URL/portal filters alongside non-obvious exports.
- **Validation:** files here are inputs, never outputs. After ingest, verify
  the per-source manifest under `data/manifests/` shows the expected row
  count and sha256, then regenerate reports (see
  docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md).
