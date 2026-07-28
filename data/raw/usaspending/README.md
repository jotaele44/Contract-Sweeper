# Dropzone: usaspending_fy2026_pr_slice

Manual USASpending bulk-archive exports, filtered to Puerto Rico. Registered by
`registries/source_registry_overlays/consolidated_2026_07_05.yaml` (family
`federal`, `required: false`). Supplements the automated `usaspending_prime`
source rather than replacing it.

Current contents:

- `FY2026_All_Contracts_PR.csv` — PR slice of the FY2026 "All Contracts" bulk
  archive, 1,157 rows.
- `FY_All_Contracts_Delta_20260208_PR.csv` — 4,837 rows; see `README_delta.md`
  for the two-part extraction detail.
- `prime_awards_transactions_pr_20260707/` — award/transaction export; see that
  directory's own README.

- **Consumer:** none wired yet — these are supplemental slices read alongside
  the automated `usaspending_prime` outputs.
- **Filter:** rows are kept where `recipient_state = PR` OR
  `place_of_performance_state = PR`. Record the filter used for any new drop.
- **Provenance:** USASpending caps CSV exports at 1,000,000 rows, so large
  pulls arrive in parts. Keep only the PR slice — leave the multi-GB source
  archives outside the repo.
- **Tracking:** these CSVs stay OUT of git (`data/**` deny-all; no allow-list
  entry for this directory). Only the READMEs are tracked.
