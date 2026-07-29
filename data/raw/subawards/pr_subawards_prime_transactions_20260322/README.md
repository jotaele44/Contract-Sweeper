<<<<<<< Updated upstream
# PR subawards + prime transactions (retrieved 2026-03-22)

USASpending subaward and prime-transaction export scoped to Puerto Rico.

| File | Rows |
| --- | --- |
| `All_Assistance_PrimeTransactions.csv` | 122,272 |
| `All_Contracts_PrimeTransactions.csv` | 56,055 |
| `All_Assistance_Subawards.csv` | 4,895 |
| `All_Contracts_Subawards.csv` | 245 |

The subaward files are the reason this drop exists — prime transactions are
also available from the automated `usaspending_prime` source, but subaward
linkage (prime recipient → subrecipient) is not.

- **Consumer:** none wired yet — the subaward join is performed ad hoc.
- **Caution:** subaward totals must never be added to prime totals; a subaward
  is a portion of its prime award, so summing both double-counts.
- **Provenance:** USASpending Custom Award Data download, retrieved 2026-03-22.
- **Tracking:** CSVs stay OUT of git (205 MB as measured 2026-07-28; matched by
  the `data/**` deny-all, with no allow-list entry). Only this README is
  tracked.
=======
# USASpending Subawards + Prime Transactions — Puerto Rico (export 2026-03-22)

Consolidated union of **10** USASpending Advanced-Search "All Subawards and Prime
Transactions" bundles (exported 2026-03-22, 15:29–16:21). Scope: **place-of-performance
= Puerto Rico** (subaward pop = PR 100%; contract prime-transaction pop = PR 100%).

| File | Rows | Notes |
|---|---|---|
| `All_Contracts_Subawards.csv` | 102 | contract subawards, subaward pop = PR |
| `All_Assistance_Subawards.csv` | 632 | assistance (grant/loan) subawards |
| `All_Contracts_PrimeTransactions.csv` | 56,055 | prime contract transactions, pop = PR |
| `All_Assistance_PrimeTransactions.csv` | 122,272 | prime assistance transactions |

## Dedup / union
The 10 bundles are **distinct slices** of one query (paginated / split downloads), not
duplicates — every bundle's PrimeTransactions CSV differed. Consolidated by **row-level
union with exact-duplicate removal** per file type (subaward data was concentrated in 3
bundles; the rest carried unique prime-transaction rows). Feeds `usaspending_subawards`
/ `fsrs_subawards`.
>>>>>>> Stashed changes
