<<<<<<< Updated upstream
# Dropzone: entity_resolution_aids

Crosswalk and alias aids used to resolve vendor/recipient names across sources.
Registered by `registries/source_registry_overlays/consolidated_2026_07_05.yaml`
(family `entity_resolution`, `required: false`).

Current contents:

- `employer_data_cumulative2001-2024_redacted.xlsx` — redacted cumulative
  employer roster, 2001–2024.
- `Contractor Index.rtf` — contractor name index.

- **Consumer:** none yet — these are reference aids read ad hoc during entity
  resolution, not a scheduled ingest.
- **Not a spending source.** Nothing here is asserted as PR spending; it exists
  only to link names. Do not feed these into financial totals.
- **Provenance:** keep original filenames where possible; record retrieval date
  and source URL/portal filters alongside non-obvious exports.
- **Tracking:** the `.xlsx`/`.rtf` files stay OUT of git by policy (binary
  blobs — see the `.gitignore` note on committing derived CSVs instead). Only
  this README is tracked.
=======
# Entity-resolution aids (consolidated 2026-07-05)

Reference/crosswalk data used for entity resolution — NOT asserted as PR spending.

- `employer_data_cumulative2001-2024_redacted.xlsx` — employer registry (name/UEI
  crosswalk aid).
- `Contractor Index.rtf` — contractor name index.

No dedicated producer; consumed opportunistically by alias/entity-resolution
tooling (`scripts/build_entity_aliases.py`, `scripts/alias_registry_builder.py`).
>>>>>>> Stashed changes
