---
name: moneysweep-ownership-capital
description: >-
  Inspect MoneySweep institutional ownership and capital-control evidence using
  independently certified SEC observations. Use for BPOP ownership history,
  Form 13F holder positions, amendment lineage, exact issuer-share percentages,
  or determining whether an ownership dataset is eligible for Deep Dive.
  Read-only by default and fail-closed: regression coverage is not inherited as
  issuer certification, provider metrics remain separate, and no holder rows are
  synthesized by aggregation.
default_mode: read_only
allowed_modes: [read_only, offline_write]
command_ids: []
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-ownership-capital

Uses the existing `moneysweep.capital_control` runtime and the bounded SEC 13F
certification pipeline. It does not reimplement entity resolution and it does not
fetch fresh SEC evidence by default. Frozen source snapshots, stable CIK/CUSIP
bindings, amendment lineage, exact-period denominators, and certification state
control every result.

## When this fires
- institutional holder / Form 13F questions;
- BPOP ownership history and eight-quarter position review;
- ownership-and-capital Deep Dive eligibility;
- amendment/restatement lineage or superseded-position review;
- comparison of SEC-computed ownership metrics with provider-reported metrics.

## Certified scope boundary
The current promoted golden scope is BPOP / CUSIP `733174700` for exactly the
eight certified periods 2024Q2 through 2026Q1. OFG and EVTC are real-source
regression fixtures only and **do not inherit BPOP certification**.

Morningstar/provider `% Total Assets` remains a distinct manifestation with
semantic-equivalence state `OPEN`. Never replace it with SEC 13F reportable
portfolio weight or claim equality without a separate authoritative semantic
binding.

## Procedure
1. Read the certification receipt before reading holdings. STOP unless `state = PASS`,
   `bounded_claim_only = true`, and provider equivalence remains `OPEN`.
2. Bind issuer by exact stable identifiers. For the current certified scope:
   BPOP → CIK `0000763901` → CUSIP `733174700`.
3. Preserve each source observation whole with holder CIK, issuer/CUSIP, accession,
   `INFOTABLE_SK`, report period, filing date, amendment state, source hash, and
   denominator provenance.
4. Apply filing-level restatement lineage. A restatement supersedes the prior
   retained filing set for the same stable filer CIK and report period; do not
   invent row-to-row predecessor identity.
5. Require exact historical issuer-share denominators. Nearest-date, current-share,
   average, max, or provider denominators are not substitutes.
6. Present ACTIVE and SUPERSEDED observations separately. Arithmetic must satisfy
   `source = active + superseded` inside the certified partition, while historical
   out-of-scope observations remain in the explicit exclusion ledger.
7. Return whole source observations. Do not sum positions across reporting managers,
   options, other-manager allocations, or investor-family labels unless a separate
   aggregation contract is independently certified.

## Required outputs
- certification ID/state and exact bounded periods;
- exact issuer stable IDs and requested security CUSIP;
- whole holder observations with ACTIVE/SUPERSEDED state and filing lineage;
- exact issuer-share denominator provenance and computed percent where eligible;
- OFG/EVTC regression coverage stated as regression coverage only;
- provider-equivalence state, retained as `OPEN` unless separately proven;
- blockers/contradictions and the next safe action.

## Stop conditions
- certification receipt absent or state != PASS;
- requested issuer/security is outside the independently certified scope;
- exact-period denominator is absent, non-positive, or contradictory;
- duplicate `(ACCESSION_NUMBER, INFOTABLE_SK)` or duplicate observation identity;
- tied/ambiguous identity or amendment lineage;
- provider metric is being promoted to SEC equivalence without semantic proof;
- a requested aggregation would synthesize a holder position not present in source.

## Forbidden operations
- name-only holder/issuer identity promotion;
- OFG/EVTC regression coverage promoted to issuer certification;
- cross-holder or brand-family summation presented as a source record;
- nearest-date/current-share denominator substitution;
- fabricated row-level supersession links;
- silently dropping original, additive, restated, superseded, or excluded manifestations;
- treating deterministic behavior as evidence of identity.

## Adversarial regression gates
The machine-readable adversarial policy is `adversarial-cases.json`. Every BLOCKED
case must fail closed before output promotion. In particular:

- `OFG_REGRESSION_NOT_CERTIFICATION`: OFG regression rows never inherit BPOP PASS.
- `EVTC_EVRI_IDENTITY_COLLISION`: EVTC must not be satisfied by ticker `EVRI`, a
  normalized-name approximation, or any other near match; stable issuer identity
  evidence controls.
- `BRAND_FAMILY_AGGREGATION`: manager labels such as Vanguard do not authorize a
  synthetic consolidated source holder row.
- `NEAREST_DATE_DENOMINATOR` and `CURRENT_SHARE_DENOMINATOR`: only the exact
  historical denominator bound to the observation period may support issuer-share
  percentage certification.
- `MORNINGSTAR_EQUIVALENCE`: provider `% Total Assets` remains `OPEN` and cannot be
  promoted to SEC metric equivalence from numerical similarity.
- `FAKE_ROW_LEVEL_RESTATEMENT_LINEAGE`: filing-level supersession does not create
  row-to-row identity between original and amended information-table rows.
- `DUPLICATE_SOURCE_RECORD`: `(ACCESSION_NUMBER, INFOTABLE_SK)` uniqueness is a hard
  invariant regardless of display-name variation.
- `NAME_ONLY_HOLDER_BINDING`: normalized names are discovery evidence only, never a
  stable holder identity proof.

A positive regression gate is retained for the exact BPOP certified scope; the
negative cases above must remain blocked even if a parser or UI path would otherwise
produce deterministic output.

## Evidence & result envelope
Emit `{status, certification, scope, identifiers, observations, lineage,
denominators, provider_equivalence, regression_coverage, blockers,
contradictions, next_safe_action}`. A script success is not a certification;
the certification receipt and its gates are controlling.
