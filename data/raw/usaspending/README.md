<<<<<<< Updated upstream
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
=======
# USASpending FY2026 — Puerto Rico slice (consolidated 2026-07-05)

`FY2026_All_Contracts_PR.csv` — Puerto Rico subset of the USASpending
`FY2026_All_Contracts_Full_20260207` bulk archive (1.86 GB, 889,804 contract
rows nationwide). Stream-filtered to **1,157 PR rows** where
`recipient_state_code == 'PR'` OR `primary_place_of_performance_state_code == 'PR'`
(union = money awarded to PR vendors + money performed in PR).

Original 270 MB zip left in place under `Contract Data/`; only the PR slice was
brought into the repo. Supplements the API-driven `usaspending_prime`
(`pr_contracts_master.csv`).
>>>>>>> Stashed changes
