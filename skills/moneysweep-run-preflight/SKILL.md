---
name: moneysweep-run-preflight
description: >-
  Run MoneySweep's structural preflight before any pipeline execution. Use when
  the user asks to run setup, check structural readiness, or confirm the repo is
  safe to execute. Reports checked sources, structural errors, missing API keys
  (distinct from failures), and exit semantics — and stops before live execution
  if any structural error exists.
default_mode: read_only
allowed_modes: [read_only, offline_write]
command_ids: [setup, strict_preflight]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-run-preflight

Orchestrates the existing preflight; it does not reimplement it. The read-only
authority is `scripts/pipeline_preflight.py` (`classify_source_readiness`), which
inspects sources without touching the workspace. The full setup wrapper
`run_all.py --only-setup --strict-preflight` is the offline_write path: it
creates `data/logs` and opens a pipeline log, so it is NOT read-only. This skill
selects the right path for the requested mode, interprets output, and enforces
the structural gate.

## When this fires
Preflight, setup, or "is the repo safe to run the pipeline" requests.

## When this does NOT fire (boundary)
- Actually running the pipeline or a producer → that is a live-execution step; this
  skill only gates it. Hand back to the operator once preflight passes.
- Cross-producer work → `thehub-pr`.

## Procedure
1. Default (read-only): run `scripts/pipeline_preflight.py`
   (`classify_source_readiness`) — it classifies sources without creating logs
   or mutating the workspace.
2. Classify each source via the preflight readiness statuses; separate
   `missing_key_limited` (a key is absent — NOT a structural failure) from
   `STRUCTURAL_STATUSES` (missing producer / import error / missing callable).
3. Only when the user authorizes offline_write, run the full setup wrapper
   `python3 run_all.py --only-setup --strict-preflight` (this writes a pipeline
   log under `data/logs`). Report exit semantics: strict preflight is the gate;
   a nonzero exit or any structural status blocks live execution.

## Required outputs
- count of sources checked; list of structural errors (with source_id + reason);
- list of missing keys, labelled as limitations not failures;
- explicit exit-code interpretation and go/no-go for live execution.

## Stop conditions
- Any structural error → STOP; do not proceed to live execution; surface the
  errors and the remediation owner.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Missing keys are reported by name only, never
value. Do not claim readiness the preflight did not confirm.
