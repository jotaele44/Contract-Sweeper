---
name: moneysweep-resolve-entities
description: >-
  Resolve vendor and person identities across MoneySweep — aliases, UEI/DUNS/LEI
  identifiers, and parent-child ownership. Use when the user asks to match,
  dedupe, or link entities. Read-only and review-first: it proposes candidate
  matches with evidence and confidence and queues conflicts; it never auto-merges
  high-value entities on a name alone.
default_mode: read_only
allowed_modes: [read_only, offline_write]
command_ids: []
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-resolve-entities

Orchestrates the existing resolution stack; it does not reimplement matching. The
authority is `scripts/entity_resolution.py` together with the alias-override and
entity modules already in the repo (`build_entity_aliases.py`,
`alias_registry_builder.py`, `build_entity_parent_map.py`,
`build_entity_resolution_review_queue.py`). This skill runs them, reads the
candidates, and enforces the review-first gate.

## When this fires
Vendor/person alias resolution, UEI/DUNS/LEI identifier matching, or parent-child
(ownership) linking requests.

## When this does NOT fire (boundary)
- Name-only automatic merge of high-value entities → never; route the pair to the
  conflict queue for human review instead.
- Deriving political or risk conclusions from identity proximity alone → out of
  scope; this skill resolves identity, it does not editorialize about it.
- Cross-producer correlation → `thehub-pr`.

## Procedure
1. Default read-only: run `scripts/entity_resolution.py` and read the existing
   alias / parent-map / review-queue outputs.
2. For each candidate, record a match class, its supporting evidence fields
   (identifiers, normalized names, parent), and a confidence.
3. Route ambiguity to the conflict queue; preserve every alias and the match
   provenance — nothing is dropped or silently rewritten.

## Required outputs
- candidate matches with a match class + supporting fields per candidate;
- a confidence per candidate and a conflict queue of unresolved/competing cases;
- aliases and match provenance preserved.

## Stop conditions
- Weak identifier-only match on a high-value entity → STOP; queue for review.
- Competing parents for one entity → STOP; do not pick one silently.
- An unreviewed alias override in play → STOP; require the review before applying.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Confidence is stated whenever a match is
inferred; secrets are named only, never valued.
