# Capital and Control Graph v0.1

## Scope

This vector establishes the canonical **identity, holding-observation, source-provenance, strict-ingestion, supersession, and temporal-analytics core** for MoneySweep's capital-and-control graph. It is backend infrastructure only: it does not expose a user-facing API or GUI, does not acquire live filings, and does not claim current ownership for any issuer.

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
- Provisional or unresolved identity cannot drive legal-holder, family, or ultimate-parent rollups.

## Ingestion invariants

- A source adapter must provide one source manifest plus canonical observation rows.
- Every row must bind to the same `source_id` as its source manifest.
- Manifest `record_count`, when supplied, must equal the observed input count exactly.
- Duplicate source-record IDs or duplicate observation IDs within one manifestation fail closed.
- Ingestion is whole-row and all-or-nothing; no silent exclusion or synthesis is permitted.
- Input count and retained count must close arithmetically.

## Holding and temporal invariants

- Every holding observation is date-bounded by both `as_of_date` and `report_date`.
- `report_date` cannot precede `as_of_date`.
- Every observation binds to a source and a source-record identifier.
- A non-empty security identifier or explicit raw security-class description is required.
- Asset manager/AUM data must not be represented as direct beneficial ownership without source support.
- Amendments are distinct observations; the replacing observation points to the displaced observation.
- Supersession cannot cross holder, issuer, security, or position-class identity.
- Superseded rows remain preserved with `amendment_status=SUPERSEDED`; their identity classification is not overwritten.
- Current and historical holdings are never conflated.
- Tied top current observations fail closed for explicit adjudication.
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

A frozen source manifestation requires non-null byte size and SHA-256. Different hashes prove byte difference only.

## Implemented analytics

- whole-row current-position selection;
- legal-holder rollup;
- investor-family rollup;
- ultimate-parent rollup;
- pairwise `INTERSECTION`;
- `A_ONLY`;
- `B_ONLY`;
- `UNION`;
- `SYMMETRIC_DIFFERENCE`.

Future derived views may include current/historical top investors, beneficial owners, voting controllers, investment managers, cross-portfolio exposure, ownership-change events, and capital/control concentration.

## GUI boundary

The runtime core is classified as active `internal` infrastructure in the federation GUI-capability manifest. This is not a parity exception or baseline regeneration. A human-facing workflow requires a separate backend -> API -> client state -> GUI -> discoverability vector with its own end-to-end tests.

## Certification boundary

This v0.1 vector may be certified for **runtime-core behavior only after the current-head CI matrix passes**. Even then, it does not certify any live source denominator, investor identity, issuer holding, ownership percentage, beneficial-owner claim, current ranking, API, or GUI workflow.
