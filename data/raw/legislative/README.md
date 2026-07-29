<<<<<<< Updated upstream
# Dropzone: legislative_openstates_pr

OpenStates Puerto Rico bill exports plus the legislator roster. Registered by
`registries/source_registry_overlays/consolidated_2026_07_05.yaml` (family
`legislative`, `required: false`). Feeds legislative–fiscal linkage.

Current contents:

- `openstates/2017-2020/` — 14 files
- `openstates/2021-2024/` — 15 files
- `openstates/2025-2028/` — 10 files
- `roster/Puerto Rico Government (2024-2028).csv` — 81 rows

- **Consumer:** none wired yet — bulk bill data is read ad hoc pending a
  dedicated ingest script.
- **Provenance:** OpenStates bulk exports, one directory per four-year cycle.
  Keep the cycle directory naming (`YYYY-YYYY`) — downstream globs rely on it.
- **Tracking:** bulk exports stay OUT of git (186 MB as measured 2026-07-28;
  matched by the `data/**` deny-all, with no allow-list entry). Only this
  README is tracked.
=======
# Legislative source (consolidated 2026-07-05)

OpenStates Puerto Rico bulk exports + legislator roster, consolidated from the
loose `Contract Data/OpenStates Puerto Rico Bills/` folder (the complete copy;
`Archive.zip` and the loose `.zip` were byte-identical triplicates and were NOT
re-ingested).

- `openstates/2017-2020/`, `openstates/2021-2024/`, `openstates/2025-2028/` —
  bills, actions, sponsorships, votes, versions, sources (CSV + JSON) per cycle.
- `roster/Puerto Rico Government (2024-2028).csv` — current legislator roster.

Source: OpenStates (openstates.org). Feeds the legislative-fiscal linkage layer
(`scripts/build_legislative_links.py`, `pr_legislative_fiscal_link_candidates.csv`).
Non-financial; retained per "everything incl. legislative" scope.
>>>>>>> Stashed changes
