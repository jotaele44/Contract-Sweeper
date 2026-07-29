<<<<<<< Updated upstream
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
=======
# USASpending Prime Awards & Transactions — Puerto Rico (export 2026-07-07)

USASpending.gov Advanced-Search "Prime Awards, Transactions and Subawards" export,
**scope: place-of-performance = Puerto Rico** (recipients are nationwide — federal
money performed in PR). Consolidated 2026-07-07.

| File | Rows | Notes |
|---|---|---|
| `Contracts_PrimeAwardSummaries.csv` | 524 | award-level, PR place-of-performance |
| `Contracts_PrimeTransactions.csv` | 1,692 | transaction-level detail for the 524 awards |
| `Assistance_PrimeAwardSummaries.csv` | 0 | header-only (no PR assistance awards in this export) |
| `Assistance_PrimeTransactions.csv` | 0 | header-only |

## Dedup (3 uploaded bundles → 1)
- `…H15M10S11243615.zip` (b3) — **byte-identical** to `…H15M08S23196692.zip` (b2). Dropped.
- `…H15M07S06026675.zip` (b1) — 17 contracts, a **strict subset** of b2's 524 (b1∩b2 = 17, b1-only = 0). Superseded.
- Assistance CSVs identical across all three bundles.
- **Kept: b2** (the 524-contract superset).

Supplements `usaspending_prime`; distinct export type from `FY2026_All_Contracts_PR.csv`
(advanced-search award+transaction detail vs. the bulk FY2026 archive slice).
>>>>>>> Stashed changes
