# Federal Financial Ontology v1

Status: **candidate for certification**. Population of new FAINs/PIIDs is intentionally blocked until this ontology passes its acceptance gates.

## Purpose

MoneySweep historically exposes a generic `funding_awards` stream where `award_id` is a repository identity. That legacy contract remains immutable. This ontology adds a namespaced federal layer so a program identifier, federal award identifier, entity identifier, award action, subaward, account, project, and financial flow can never be silently conflated.

The root is `federal_financial_flow`, with three disjoint branches:

1. `federal_financial_assistance`
2. `federal_procurement`
3. `federal_account_non_award_spending`

This follows the authoritative split used by SAM.gov Assistance Listings and USAspending. The live USAspending award-type reference endpoint exposes 33 granular award-type codes across contracts, IDVs, grants/cooperative agreements, loans, direct payments, and other financial assistance.

## Canonical object model

`program -> award -> award_action`

`award -> subaward`

`entity <-> award/subaward/action`

`account <-> award/action/financial_flow`

`project <-> award/subaward/financial_flow`

`financial_flow` records the monetary event; an award is not itself a cash movement.

## Identifier semantics

| Scheme | Scope |
|---|---|
| Federal Assistance ID (legacy CFDA/ALN aliases retained) | program |
| FAIN / URI | assistance award |
| USAspending unique/generated award keys | award |
| PIID | procurement award |
| parent award ID | procurement parent |
| UEI / legacy DUNS | entity |
| subaward number | subaward |
| modification number | award action |
| TAS / federal account code | account |
| program activity code | account program activity |
| DEFC | funding-authority tag |

Federal Assistance IDs are temporal/versioned and permit post-2025 alphanumeric values. Historical values are append-only; no migration rewrites prior identifiers.

## Puerto Rico nexus

Program applicability and actual Puerto Rico funding are distinct. Every program eventually receives exactly one classification for a given snapshot:

- `confirmed_pr_activity`
- `pr_eligible_no_activity_recovered`
- `not_pr_applicable`
- `historical`
- `unresolved`
- `requires_award_level_test`

## Backward compatibility

Existing `awd_<32hex>` identities and export streams are untouched. New federal hard identifiers bind through namespaced identifier objects. No FAIN, PIID, UEI, Assistance ID, amount, date, or name may be inferred from another identifier.

## Acceptance gates

Certification requires:

- 100% of the authoritative USAspending award-type code denominator mapped.
- 100% identifier-scheme scope coverage.
- Zero unadjudicated identifier-scope conflicts.
- Zero special-case schema mutations across the eight acceptance topologies.
- 100% of the SAM Assistance Listing denominator classified by Puerto Rico nexus state before claiming program-population completeness.
- FAIN population remains blocked until those gates pass.

The machine-readable source of truth is `registries/federal_financial_ontology_v1.json`; the generic object contract is `schemas/federal_financial_ontology.schema.json`.
