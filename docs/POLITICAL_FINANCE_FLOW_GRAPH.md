# Political Finance Flow Graph

## Scope

This subsystem converts FEC Schedule A/B/E and Puerto Rico OCE/CEE records into
a canonical, provenance-bearing graph suitable for donor, committee, PAC,
Super PAC, independent-expenditure, vendor and downstream-recipient analysis.

## Materialized outputs

- `political_entities.csv`
- `political_transactions.csv`
- `political_recipient_resolution.csv`
- `political_contract_lobbying_correlations.csv`
- `political_flow_paths.csv`

All outputs are written beneath `data/staging/processed/political_finance/`.
The graph is additive and does not replace source-specific masters.

## Edge contract

| Edge | Meaning |
|---|---|
| `DONATED_TO` | Donor receipt reported by FEC, OCE or CEE |
| `DISBURSED_TO` | Schedule B committee outflow |
| `INDEPENDENT_EXPENDITURE_FOR` | Schedule E spending supporting a candidate |
| `INDEPENDENT_EXPENDITURE_AGAINST` | Schedule E spending opposing a candidate |

Recipient resolution is deliberately fail-closed: only a unique exact
normalized-name match is accepted automatically. Ambiguous and unmatched names
are retained as downstream-recipient nodes with `review_required=true`.

## Confidence

- Source-native identifiers and transaction edges: `1.00` or `0.95`.
- Unique exact normalized-name resolution: `0.98`.
- Source rows lacking stable entity identifiers: `0.85`–`0.90`.
- Unresolved free-text recipients: `0.40`, always requiring review.

## Execution

```bash
python scripts/download_fec_committees.py --force
python scripts/materialize_political_finance_graph.py
python -m pytest tests/test_political_finance_flow_graph.py -v
```

Live OCE/CEE depth remains constrained by operator-delivered exports. The graph
normalizes those records when present but does not claim a live Puerto Rico
campaign-finance API where none is configured.

## Residual gaps

1. Candidate master ingestion and authorized-committee filings are not yet a
   dedicated source; Schedule E candidate identifiers are supported.
2. Fuzzy recipient resolution is intentionally deferred until a reviewed alias
   registry and threshold calibration exist.
3. Schedule B/E materialization still depends on FEC API availability and an
   API key with sufficient quota.
4. GUI/API exposure is outside this initial graph-contract change.
