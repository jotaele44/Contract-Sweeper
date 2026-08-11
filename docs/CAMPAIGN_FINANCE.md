# Campaign-Finance Data Plane

MoneySweep treats campaign finance as a first-class data plane rather than a
single FEC CSV. The complete materialization ladder covers federal receipts,
federal committee outflows, Puerto Rico donations, reports, entity resolution,
graph edges, cross-references, API endpoints, and the desktop/web dashboard.

## Source families

| Source | Producer | Canonical output |
|---|---|---|
| FEC Schedule A receipts | `scripts/download_fec.py` or `scripts/ingest_fec.py` | `pr_fec_contributions.csv` |
| FEC committee master | `scripts/download_fec_committees.py` | `pr_fec_committees.csv` |
| FEC Schedule B disbursements | `scripts/download_fec_committees.py` | `pr_fec_disbursements.csv` |
| FEC Schedule E independent expenditures | `scripts/download_fec_committees.py` | `pr_fec_independent_expenditures.csv` |
| OCE Socrata donations | `scripts/download_oce.py` | `pr_oce_donations.csv` |
| OCE manual donor/report searches | `scripts/ingest_oce.py` | `pr_oce_donations.csv`, `pr_oce_reports.csv` |
| CEE/CEEPUR exports | `scripts/ingest_donaciones.py` | `pr_donaciones.csv` |

OCE and CEE donation outputs use the same 17-column schema. OCE report-search
exports are detected by their report-number field and are never mixed into the
donation table.

## One-command materialization

```bash
python3 scripts/materialize_campaign_finance.py
```

Network-enabled run:

```bash
export FEC_API_KEY=<key>
python3 scripts/materialize_campaign_finance.py --live-oce --live-fec --strict
```

The orchestrator preserves step-level errors in
`data/manifests/campaign_finance/materialization_run_latest.json` instead of
silently skipping failed source families.

## Entity and graph outputs

`build_campaign_finance_entities.py` writes:

```text
data/staging/processed/pr_campaign_finance_candidates.csv
data/staging/processed/pr_campaign_finance_committees.csv
data/staging/processed/pr_campaign_finance_recipient_resolution.csv
data/staging/processed/pr_campaign_finance_edges.csv
```

Resolution rules are deliberately conservative:

1. Stable FEC candidate and committee IDs are authoritative.
2. Exact normalized-name matches resolve Schedule B recipients automatically.
3. NGO and federal-award recipient matches use existing MoneySweep identity
   universes.
4. Unresolved recipients remain in the output with `needs_review`; they are not
   dropped or guessed.

## Validation gates

```bash
python3 scripts/validate_campaign_finance_materialization.py --strict
```

The strict gate requires:

- non-empty FEC Schedule A, committee, and Schedule B outputs;
- a schema-valid Schedule E output, which may legitimately be header-only;
- a non-empty OCE donation feed;
- candidate, committee, recipient-resolution, and graph-edge outputs;
- FEC/awards and NGO/donation cross-references whenever their upstreams exist.

The report is written to:

```text
data/manifests/campaign_finance/campaign_finance_validation.json
```

The repaired branch baseline has passed canonical Ruff formatting, focused MyPy
validation, offline snapshot generation, deterministic completeness-matrix
regeneration, the restored 11-skill contract, and 24 focused tests with one
intentional skip. Repository-wide CI retains its normal coverage threshold.

## API and GUI

FastAPI routes:

```text
GET /campaign-finance/summary
GET /campaign-finance/contributions
GET /campaign-finance/entities
GET /campaign-finance/reports
```

The dashboard exposes a discoverable **Campaign Finance** tab with contribution,
entity, recipient-resolution, and report views. Offline dashboard exports include
these endpoints in `snapshot.json`.

## Operator-supplied July 29, 2026 corpus

The certification manifest
`data/manifests/campaign_finance/operator_supplied_20260729.json` records source
hashes and the local normalization result. The source binaries are not embedded
in this change; place them in the declared FEC/OCE dropzones and rerun the ladder.

Local verified materialization from those supplied files produced:

| Output | Rows |
|---|---:|
| Normalized FEC Schedule A | 15,260 |
| Deduplicated OCE donations | 161,439 |
| OCE reports | 2,000 |
| Candidate entities | 923 |
| Committee entities | 875 |
| Contribution graph edges | 15,260 |
| Schedule B recipients | Pending terminal live FEC materialization evidence |

The branch must remain unmerged until the secure network-enabled FEC workflow
materializes Schedule B/E, publishes the evidence artifact, and the strict gate
returns `ok: true` on the final head.
