---
name: moneysweep-operator
description: >-
  Orient, report status, and route MoneySweep work to the right skill. Use for
  general "what is the state of MoneySweep / which command or skill handles X"
  requests. Read-only: reports the active vector, readiness truth, and blockers,
  then routes; it never executes the pipeline or crosses a producer boundary.
default_mode: read_only
allowed_modes: [read_only]
command_ids: []
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-operator

The entry point and router. It reads the manifest and status reports, states the
truth, and hands off to a specific skill. It selects flags and enforces gates; it
never owns orchestration (`run_all.py` does) or cross-producer correlation
(`thehub-pr` does).

## When this fires
General orientation, status, or "which command / skill handles X" requests.

## When this does NOT fire (boundary)
- Cross-producer correlation / aggregation → `thehub-pr` (route there, don't do it).
- Centinelas signal collection → `centinelas-pr`.
- Presenting the diagnostic dashboard as a product surface → decline; the Hub
  frontend is the product.

## Procedure
1. Read `federation.json` (active_vector, production_status,
   `federation_readiness_gate`), `reports/current_status.json`, and
   `reports/materialization_readiness.json`.
2. Report: active vector, production status, readiness truth (total / automatable
   / queued from the readiness JSON only), and the `blocking_conditions` verbatim.
3. Route to the matching skill per `activation-matrix.yaml` /
   `dependency-graph.yaml`. If the target is ambiguous, ask before routing.

## Required outputs
- active vector + production status; readiness truth with its source; blockers
  quoted verbatim; the chosen next skill (or a clarifying question).

## Stop conditions
- Ambiguous target → ask, don't guess.
- Requested action is owned by the Hub or another producer → route, don't perform.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Every source count cites
`reports/materialization_readiness.json`; never quote a count from narrative docs.
