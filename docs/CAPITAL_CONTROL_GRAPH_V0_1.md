# Capital and Control Graph v0.1

## Scope

This vector establishes the canonical **identity, holding-observation, and source-provenance contracts** for a future MoneySweep capital-and-control graph. It is infrastructure only: it does not expose a user-facing API or GUI, does not ingest live filings, and does not claim current ownership for any issuer.

## Core rule

`TOP_INVESTOR` is a derived temporal view, never a canonical identity table.

The canonical chain is:

`issuer -> security/asset -> holding_observation -> investor legal entity -> investor family -> ultimate parent`

Fund/vehicle, investment adviser, beneficial owner, custodian/nominee, and ultimate parent are distinct semantic and identity levels. Shared branding, normalized names, count equality, proximity, or source absence are not sufficient identity evidence.

## Identity invariants

- Preserve `raw_name` exactly as reported by the source.
- Keep raw, normalized, canonical, legal-entity, investor-family, and ultimate-parent identity layers separate.
- Never promote a heuristic discovery match to `PASS` identity.
- A `PASS` identity requires stable-ID or authoritative/corroborated binding evidence.
- Preserve 1:1, 1:N, N:1, N:N, 0:1, and unresolved relationships.
- Tied top evidence remains review/unresolved; deterministic selection is not identity evidence.

## Holding invariants

- Every holding observation is date-bounded by both `as_of_date` and `report_date`.
- Every observation binds to a source and a source-record identifier.
- A security identifier or explicit raw security-class description is required.
- Asset manager/AUM data must not be represented as direct beneficial ownership without source support.
- Amendments are distinct observations; superseded rows remain preserved and are excluded from current derived views.
- Current and historical holdings are never conflated.
- No aggregation may synthesize a holder record that did not exist in the source.

## Provenance invariants

For each source manifestation preserve, when obtainable:

- authority;
- URL or stable locator;
- retrieval UTC;
- source as-of / refresh date;
- query identity;
- page/offset;
- raw byte size and SHA-256;
- schema fingerprint;
- source record count;
- canonicality state.

A frozen source manifestation requires both byte size and SHA-256. Different hashes prove byte difference only.

## Derived views planned after this foundation

- current top investors;
- historical top investors;
- beneficial owners;
- voting controllers;
- investment managers;
- investor-family exposure;
- common ownership;
- cross-portfolio exposure;
- ownership-change events;
- capital concentration;
- control concentration.

For pairwise issuer comparison, compute `INTERSECTION`, `A_ONLY`, `B_ONLY`, `UNION`, and `SYMMETRIC_DIFFERENCE` separately for legal holder, investor family, ultimate parent, beneficial owner, and voting controller.

## Certification boundary

This v0.1 vector may be certified only for **schema/contract completeness within its defined scope**. It does not certify any investor identity, issuer holding, ownership percentage, beneficial-owner claim, source denominator, current ranking, or GUI workflow.
