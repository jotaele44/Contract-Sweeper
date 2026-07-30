---
name: moneysweep-audit-financial-gaps
description: >-
  Audit which financial coverage is missing across MoneySweep — domains,
  periods, fields, agencies, and municipalities. Use when the user asks what
  financial data is absent or where the gaps are. Produces a gap matrix in which
  every row carries a denominator, a priority, an owner, and an acquisition path.
  Read-only; it interprets existing audits and never invents new financial events.
default_mode: read_only
allowed_modes: [read_only]
command_ids: [gap_matrix]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-audit-financial-gaps

Orchestrates the existing gap and completeness builders; it does not compute a new
coverage universe. The authority is the `gap_matrix` command
(`scripts/gap_analysis_builder.py`) plus `scripts/build_financial_source_audit.py`,
`scripts/build_completeness_matrix.py`, and `scripts/build_gap_closure_baseline.py`.
This skill runs them, reads their output, and assembles the priced gap matrix.

## When this fires
Requests to find missing financial domains, periods, fields, agencies, or
municipalities — "what financial data are we missing / where are the gaps".

## When this does NOT fire (boundary)
- Materialization recovery / 0-to-100 closure of the source universe →
  `moneysweep-recover-source-coverage` (route there).
- Never add overlapping-source rows as if they were separate financial events:
  obligations, payments, and contracts stay distinct — they are not summed or
  double-counted into one gap.
- Cross-producer aggregation → `thehub-pr`.

## Procedure
1. Read-only: run `gap_matrix` (`python3 scripts/gap_analysis_builder.py`) and the
   local audit builders (`build_financial_source_audit.py`,
   `build_completeness_matrix.py`, `build_gap_closure_baseline.py`).
2. For each gap, attach its denominator (the universe it is measured against),
   priority, owning agency/domain, and acquisition path from those outputs.
3. Reconcile: fold overlapping sources into one row per financial event type;
   flag any denominator the builders did not supply.

## Required outputs
- a gap matrix; each row carries a denominator + its source, a priority, an
  owner, and an acquisition path;
- explicit list of overlapping sources collapsed and any denominator still unknown.

## Stop conditions
- Unknown denominator → STOP; do not price a gap you cannot measure.
- A source counted twice (overlap treated as separate events) → STOP and collapse.
- Unresolved contradiction across the audit surfaces → STOP and surface it.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Every coverage claim cites
`reports/materialization_readiness.json`; secrets are named only, never valued.
