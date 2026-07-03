# Intake finance-lane normalization (#114)

How Puerto Rico politics/finance records flow from the shared PR-intake router
into moneysweep-pr's normalized finance lane.

> **Partially revived (2026-07): the `spiderweb_pr_derivatives.csv` stream.**
> The automated cross-repo delivery hop (`scripts/deliver_derivatives.py`,
> removed 2026-06) stays retired, but spiderweb-pr now ships a consumer for the
> derivatives file — its spatial lane
> (`spiderweb-pr/readiness/spiderweb_spatial_lane.py`) reads
> `spiderweb_pr_derivatives.csv` from a router dropzone and validates rows
> against `spiderweb-pr/schemas/pr_intake_derivative.schema.json` — so the
> router writes the stream again alongside `moneysweep_derivatives.csv`. The
> lane volume is still reported in `routing_summary.json` as
> `spiderweb_pr_derivative_count`. Delivery of the file to a spiderweb checkout
> remains a manual/operator step.

## The chain

```
raw intake items (JSONL/JSON/CSV)
  └─ scripts/route_pr_intake.py            # shared/pr_intake_router.py + config/pr_intake_domain_router.yaml
       └─ data/exports/pr_intake_router/moneysweep_derivatives.csv
            └─ scripts/build_moneysweep_finance_lane.py   (this repo, #114)
                 → data/normalized/{funding_event_leads, contracts_procurement_events,
                    politics_finance_items, agency_actions, lobbying_political_links}.csv
                 + data/review/{verification_queue, moneysweep_crosswalk_queue,
                    discrepancy_queue}.csv
```

The finance lane fans each derivative out into exactly the tables the router
assigned via the row's `output_tables` field. It is **zero-loss**: every input
row lands in ≥1 normalized table or review queue, or is recorded in
`discrepancy_queue.csv` — nothing is dropped.

## Run it locally

```bash
python3 scripts/route_pr_intake.py --input tests/fixtures/pr_intake_router_sample.jsonl \
        --out-dir data/exports/pr_intake_router
python3 scripts/build_moneysweep_finance_lane.py --input data/exports/pr_intake_router --out .
```

## Automation

`.github/workflows/intake-delivery.yml` (manual `workflow_dispatch`) runs the
chain and opens a same-repo finance-lane PR (using the default `GITHUB_TOKEN`).

> The workflow is delivery scaffolding and is **not** exercised by CI. The logic
> it calls **is** covered: `tests/test_moneysweep_finance_lane.py`.
