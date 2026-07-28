# USASpending prime awards + transactions — PR (retrieved 2026-07-07)

Custom Award Data export from USASpending, scoped to Puerto Rico. Part of the
`usaspending_fy2026_pr_slice` dropzone (see `../README.md`).

| File | Rows |
| --- | --- |
| `Contracts_PrimeTransactions.csv` | 1,692 |
| `Contracts_PrimeAwardSummaries.csv` | 524 |
| `Assistance_PrimeTransactions.csv` | 0 |
| `Assistance_PrimeAwardSummaries.csv` | 0 |

**The two `Assistance_*` files are empty** (header only). That is how they were
delivered — the export returned no assistance rows for the requested scope. Do
not treat the empty files as an ingest failure, and do not infer that PR
received no federal assistance in the period; re-pull with a widened scope if
assistance coverage is needed.

- **Provenance:** USASpending Custom Award Data download, retrieved 2026-07-07.
  Record the date range and filters used for any re-pull.
- **Tracking:** CSVs stay OUT of git; only this README is tracked.
