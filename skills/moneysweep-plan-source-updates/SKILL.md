---
name: moneysweep-plan-source-updates
description: >-
  Plan MoneySweep source refreshes: which sources are due, freshness against SLA,
  drop scans, and a DAG-safe update plan. Use for "what needs updating",
  freshness, drop-scan, or source-specific refresh requests. Default is plan-only
  (read_only); a live refresh adds live_network and REQUIRES explicit user
  authorization.
default_mode: read_only
allowed_modes: [read_only, offline_write, live_network]
command_ids: []
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-plan-source-updates

Orchestrates the existing update controller; it does not reimplement scheduling,
the policy engine, or the DAG. The authority is `scripts/update_sources.py`
wrapping `moneysweep/update_controller/` (policy, planner, state, drop_scanner).
This skill selects the read-only subcommands, interprets their output, and holds
the live-execution gate.

## When this fires
Due-source checks, freshness-against-SLA, drop scans, or a request to refresh a
specific source.

## When this does NOT fire (boundary)
- Materialization coverage / gap-closure accounting → `moneysweep-recover-source-coverage`.
- Staging a dropped manual file for intake → `moneysweep-ingest-manual-source`.
- Cross-producer work → `thehub-pr`.

## Procedure
1. Validate first (read-only): `python3 scripts/update_sources.py validate-policy`.
   A malformed policy or a cyclic/broken DAG is a hard stop.
2. Plan (read-only, no network): `python3 scripts/update_sources.py plan` and
   `... freshness`. Report due sources, freshness vs the SLA in
   `registries/source_update_policy.yaml`, and DAG order — parents before any
   derived source, never reordered.
3. Drop scan for file-drop sources: `... scan-drops` against
   `registries/manual_export_registry.yaml`; a due file-drop source with no
   staged drop is a stop, not a live fetch.
4. A live refresh (`run`) is live_network: state it needs explicit user
   authorization and do NOT run it until granted.

## Required outputs
- policy/DAG validation result; list of due sources with freshness vs SLA (SLA
  cited from source_update_policy.yaml);
- DAG-ordered plan (parents → derived) and the exclusions (not-due, disabled,
  missing-drop);
- explicit statement of what a live run would do and its authorization status.

## Stop conditions
- Invalid policy or DAG → STOP; do not plan around it.
- A due file-drop source missing its manual drop → STOP; route to intake.
- Live run requested but not authorized → STOP; stay plan-only.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Report required keys by name only, never
value. Never bypass the controller's policy/DAG or launch a live refresh
unauthorized.
