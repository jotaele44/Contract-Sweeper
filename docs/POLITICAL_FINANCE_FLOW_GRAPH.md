# Political Finance Flow Graph

## Scope

This subsystem converts FEC Schedule A/B/E and Puerto Rico OCE/CEE records into a canonical, provenance-bearing graph for donor, committee, PAC, Super PAC, independent-expenditure, vendor, awardee, lobbying-client, and downstream-recipient analysis.

## Materialized outputs

All outputs are written below `data/staging/processed/political_finance/`:

- `political_entities.csv`
- `political_transactions.csv`
- `political_recipient_resolution.csv`
- `political_contract_lobbying_correlations.csv`
- `political_flow_paths.csv`
- `political_materialization_accounting.csv`

## Edge contract

| Edge | Meaning |
|---|---|
| `DONATED_TO` | FEC, OCE, or CEE receipt |
| `DISBURSED_TO` | Schedule B downstream outflow |
| `TRANSFERRED_TO` | Schedule B committee-to-committee transfer using a known recipient committee ID |
| `AUTHORIZED_COMMITTEE_OF` | Principal campaign committee to candidate |
| `AFFILIATED_WITH` | Explicit committee affiliation |
| `INDEPENDENT_EXPENDITURE_FOR` | Schedule E spending supporting a candidate |
| `INDEPENDENT_EXPENDITURE_AGAINST` | Schedule E spending opposing a candidate |

## Resolution and correlation rules

Recipient resolution remains fail-closed. Only a unique exact normalized-name match is accepted automatically. Ambiguous and unmatched recipients remain review-required nodes.

Contract and lobbying correlations are analytical leads, not causal assertions. They require exact normalized-name agreement. When dates exist, the output records the nearest non-negative day interval and applies a 730-day default window. Evidence, method, and confidence are persisted per row.

## Candidate and affiliation input

The materializer consumes `data/staging/processed/pr_fec_candidates.csv` when available. Expected fields are `candidate_id`, `name`, and `principal_campaign_committee_id`. Missing candidate input is recorded as `accounted_zero`; it does not silently imply complete coverage.

## Verification

```bash
python scripts/download_fec_committees.py --force
python scripts/materialize_political_finance_graph.py
python -m pytest tests/test_political_finance_flow_graph.py tests/test_political_finance_completion.py -v
python -m pytest -q
```

The accounting output requires every configured input and output to be either nonzero or explicitly `accounted_zero`. A zero row count remains a coverage gap unless the source is genuinely inapplicable.

## Capability matrix

| Capability | State |
|---|---|
| Schedule A donations | implemented |
| Schedule B disbursements | implemented; live rows source-dependent |
| Schedule E independent expenditures | implemented; live rows source-dependent |
| Candidate authorization edges | implemented when candidate master is present |
| Committee affiliation edges | implemented when affiliation IDs are present |
| Committee transfer edges | implemented when recipient committee IDs are present |
| Award and lobbying correlations | implemented as conservative name/time correlations |
| Provenance, confidence, deduplication | implemented |
| Multi-hop paths | implemented |
| Accounted-zero reporting | implemented |
| Live OCE/CEE acquisition | residual gap |
| Reviewed fuzzy aliases | residual gap |
| API/GUI exposure | residual gap |

## Gap ledger

1. Live FEC Schedule B/E materialization still requires API execution and sufficient quota.
2. The candidate master must be produced by the repository ingestion environment; this PR registers and consumes it but does not embed a second credentialed downloader.
3. OCE and CEE remain operator-delivered sources.
4. Exact-name correlations can miss aliases and legal-name changes; fuzzy resolution remains deferred until a reviewed alias registry exists.
5. API and GUI exposure remain outside this data-contract PR.
