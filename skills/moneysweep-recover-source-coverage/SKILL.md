---
name: moneysweep-recover-source-coverage
description: >-
  Account for MoneySweep materialization coverage and 0→100 gap closure: the true
  denominator, the automatable/queued split, the unresolved-gap ledger, and any
  contradictions between surfaces. Use for coverage-recovery or "close the gap"
  requests. Read-only and offline. Every coverage % it reports carries its
  denominator and the registry SHA.
default_mode: read_only
allowed_modes: [read_only, offline_write]
command_ids: [materialization_matrix, gap_matrix]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-recover-source-coverage

Orchestrates the existing coverage and gap builders; it does not recompute the
readiness truth or invent a universe. The authority is the materialization
matrix (`materialization_matrix`), the gap matrix (`gap_matrix`), and the local
audit/completeness/baseline scripts. This skill runs them, reconciles their
counts, and reports coverage with a declared denominator.

## When this fires
Materialization recovery, coverage accounting, or 0→100 gap-closure requests.

## When this does NOT fire (boundary)
- Planning which sources to refresh → `moneysweep-plan-source-updates`.
- Deciding whether a source can be promoted → `moneysweep-assess-promotion-readiness`.
- Cross-producer aggregation → `thehub-pr`.

## Procedure
1. Read the readiness truth from `reports/materialization_readiness.json` (total,
   automatable, queued/excluded) — the only source of source counts.
2. Build the surfaces: `materialization_matrix`, `gap_matrix`, and
   `scripts/audit_materialization_coverage.py` /
   `scripts/build_completeness_matrix.py` /
   `scripts/build_gap_closure_baseline.py`.
3. Reconcile counts across every surface and classify each source (automatable /
   queued-excluded with reason). An unclassified source or a count that disagrees
   across surfaces is a stop.
4. Read the unresolved ledger `reports/gap_closure/unresolved_gap_ledger.csv` and
   report it as-is; never absorb its rows into the denominator.

## Required outputs
- the denominator (with its source), the automatable vs queued/excluded split,
  and the queued reasons;
- the unresolved-gap ledger and any contradictions between surfaces;
- every coverage % stated as numerator / denominator / exclusions / failures.

## Stop conditions
- Source-count disagreement across surfaces → STOP; report the contradiction.
- An unclassified source → STOP; do not guess a class.
- A proposed denominator that inflates the universe (e.g. an identifier range as
  the universe) → STOP; that is forbidden.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Every coverage % declares its numerator,
denominator, exclusions, failures, and the registry SHA from
`reports/materialization_readiness.json`
(`source_count_provenance.source_ids_sha256`). Never report a completeness %
without its denominator + registry hash.
