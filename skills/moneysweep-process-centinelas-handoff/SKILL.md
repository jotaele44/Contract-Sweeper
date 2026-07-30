---
name: moneysweep-process-centinelas-handoff
description: >-
  Process an already-delivered Centinelas signal toward an official-record
  candidate in MoneySweep. Use when an emerging matter is handed off and needs to
  move through the pre-official lifecycle. Offline intake first: it ingests the
  delivered signal, matches it to located finance, and reports handoff status; it
  never collects signals and never promotes past pre-official without an
  officialization record.
default_mode: offline_write
allowed_modes: [read_only, offline_write]
command_ids: [ingest_centinelas, build_contract_finance_bundle]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-process-centinelas-handoff

Orchestrates the MoneySweep end of the Centinelas → MoneySweep handoff; it does
not collect signals. The authority is the `ingest_centinelas`
(`scripts/ingest_centinelas_signals.py`) and `build_contract_finance_bundle`
commands. This skill ingests a delivered signal offline, matches it to finance,
and stages it as a pre-official located-finance candidate.

## When this fires
An emerging matter already delivered by Centinelas becomes an official-record
candidate that must move through the pre-official lifecycle.

## When this does NOT fire (boundary)
- Signal collection is owned by `centinelas-pr` → never collect or re-collect;
  this skill only processes a signal that has already been delivered.
- Cross-producer correlation / spatial overlay → `thehub-pr` / SpiderWeb.
- Promotion past pre-official without an officialization record → refuse.

## Procedure
1. Offline intake first (offline_write): run `ingest_centinelas`
   (`python3 scripts/ingest_centinelas_signals.py`) to read the delivered drop
   into export-stream candidates.
2. Run `build_contract_finance_bundle` (`--export-dir exports/centinelas_intake`)
   to match candidates to located finance and record the lifecycle stage.
3. Report handoff status; cite the official-record evidence before any promotion
   past pre-official — absent that record, the candidate stays pre-official.

## Required outputs
- lifecycle stage of the matter; match candidates against located finance;
- the official-record evidence (or its absence); handoff status.

## Stop conditions
- No officialization record → STOP; keep the candidate pre-official.
- The request would duplicate Centinelas signal ownership → STOP; route to
  `centinelas-pr`, do not collect.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Official-record evidence is cited before
promotion; secrets are named only, never valued.
