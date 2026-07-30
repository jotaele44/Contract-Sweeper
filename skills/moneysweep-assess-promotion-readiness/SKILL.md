---
name: moneysweep-assess-promotion-readiness
description: >-
  Decide whether a MoneySweep source or export package can be promoted. Use when
  the user asks if something is ready for promotion or Hub-live execution.
  Read-only: runs the materialization matrix and test suite, reads the gate
  reports, and returns a pass/fail decision with evidence, blockers, and a
  rollback target — and can never pass while the federation live-execution gate
  is closed.
default_mode: read_only
allowed_modes: [read_only]
command_ids: [materialization_matrix, test_suite]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-assess-promotion-readiness

Interprets the existing gates; it does not reimplement them. The authorities are
`materialization_matrix`, `test_suite`, `scripts/run_production_status_gate.py`,
and `scripts/run_promotion_guard.py`. This skill runs them read-only, reconciles
their evidence, and states a defensible go/no-go.

## When this fires
"Is this source / package promotable, ready for Hub-live execution" decisions.

## When this does NOT fire (boundary)
- Building or packaging the export → `moneysweep-build-federation-export`.
- Executing a promotion (writing a production package) → gated there, not here.
- Cross-producer promotion or aggregation → `thehub-pr`.

## Procedure
1. Read `reports/materialization_readiness.json` and
   `data/exports/production_status.json` for the current truth.
2. Run the gates read-only: `materialization_matrix`, `test_suite`,
   `scripts/run_production_status_gate.py`, `scripts/run_promotion_guard.py`.
   Collect each gate's pass/fail and its rollback target.
3. Read `federation.json#federation_readiness_gate`. If
   `ready_for_hub_live_execution` is false, the decision CANNOT be "pass"; quote
   every `blocking_conditions` entry verbatim.

## Required outputs
- pass/fail matrix per gate with its evidence; consolidated blockers; the
  rollback target; and the readiness truth with its source count.

## Stop conditions
- Any failed gate → STOP; return no-go with the failing gate named.
- Source-count mismatch across surfaces → STOP; do not paper over it.
- Lineage or review gap → STOP; the promotion is not defensible.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. HARD BOUNDARY: never return "pass" while
`federation.json` reports `ready_for_hub_live_execution: false` — quote the
`blocking_conditions`. Cite every source count from
`reports/materialization_readiness.json`; secrets by name only.
