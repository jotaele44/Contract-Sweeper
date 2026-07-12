---
name: moneysweep-ingest-manual-source
description: >-
  Stage a dropped PDF/XLSX/CSV manual source (Tranche B intake): hash the file,
  inventory it, run the parser, check schema and row counts, record lineage, and
  queue it for review. Use on a file drop or manual-intake request. Default is
  read-only inspect/dry-run; it never auto-promotes a manual source to production.
default_mode: read_only
allowed_modes: [read_only, offline_write]
command_ids: []
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-ingest-manual-source

Orchestrates the existing intake controller; it does not reimplement parsing,
normalization, or promotion. The authority is
`scripts/source_intake_tranche_b.py` with the per-source importers
(`scripts/ingest_donaciones.py`, `scripts/ingest_cor3.py`, …) and the operator
runbook `docs/GAP_CLOSURE_OPERATOR_RUNBOOK.md`. This skill inspects a drop,
interprets the parser/schema result, and stages it for review.

## When this fires
A PDF/XLSX/CSV file drop, or a Tranche B manual-source intake request.

## When this does NOT fire (boundary)
- Scanning which file-drop sources are due → `moneysweep-plan-source-updates`.
- Promoting a staged source to production → out of scope; promotion has its own
  gates (`moneysweep-assess-promotion-readiness`).
- Cross-producer work → `thehub-pr`.

## Procedure
1. Inspect/dry-run first (read-only): confirm the dropped file exists and its
   provenance is registered in `registries/manual_export_registry.yaml`. A
   missing file, provenance, parser, or schema is a hard stop.
2. Hash the raw file (sha256) and inventory it before any transform.
3. Run intake dry-run via `python3 scripts/source_intake_tranche_b.py`; capture
   the parser result, the target schema check, and row counts BEFORE and AFTER
   normalization.
4. Record lineage (source document → staged output) and place the source on the
   review queue. Stop there — promotion is a separate, gated step.

## Required outputs
- raw-file sha256 and file inventory; parser result; schema check and row counts
  before vs after normalization;
- retained source-document provenance and lineage; the review-queue entry.

## Stop conditions
- Missing file, provenance, parser, or schema → STOP; surface which is absent.
- Automatic promotion requested → STOP; promotion needs its own gates, not this
  skill.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Report secrets by name only, never value.
Never auto-promote a manual source to production; the promotion gate (parser,
canonical output, schema validation, regression tests) is owned elsewhere.
