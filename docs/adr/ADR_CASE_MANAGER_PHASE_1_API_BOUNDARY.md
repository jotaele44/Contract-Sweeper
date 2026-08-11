# ADR: Case Manager Phase 1 API Boundary

## Status

Proposed for the schema-foundation phase. No production endpoint or UI is implemented by this ADR.

## Context

Case Manager organizes canonical evidence into cases, claims, contradictions, leads, findings, events and immutable snapshots. Canonical evidence remains owned by the existing evidence pipeline. The API must preserve provenance, prevent silent mutation and make every adjudication auditable.

## Decision

Phase 1 uses separated query endpoints and command endpoints. Generic record updates and deletes are not supported for evidentiary objects.

### Queries

- `GET /cases`
- `GET /cases/{case_id}`
- `GET /cases/{case_id}/evidence`
- `GET /cases/{case_id}/claims`
- `GET /cases/{case_id}/contradictions`
- `GET /cases/{case_id}/events`
- `GET /cases/{case_id}/leads`
- `GET /cases/{case_id}/findings`
- `GET /cases/{case_id}/snapshots`
- `GET /cases/{case_id}/audit-events`

Every query applies object visibility and may narrow results according to caller authorization. A response must never broaden the stored visibility of an object.

### Commands

- `POST /cases`
- `POST /cases/{case_id}/evidence-links`
- `POST /cases/{case_id}/claims`
- `POST /claims/{claim_id}/evidence-relations`
- `POST /cases/{case_id}/contradictions`
- `POST /contradictions/{contradiction_id}/resolution`
- `POST /cases/{case_id}/leads`
- `POST /leads/{lead_id}/closure`
- `POST /cases/{case_id}/findings`
- `POST /findings/{finding_id}/acceptance`
- `POST /cases/{case_id}/snapshots`

Each successful command executes one transaction that:

1. authenticates and authorizes the actor;
2. validates deterministic identifiers and object visibility;
3. resolves canonical evidence references without modifying canonical evidence;
4. validates same-case and lifecycle invariants;
5. writes a new object or explicit superseding object;
6. appends the corresponding audit event and hash-chain link;
7. commits once.

A failed command writes neither the analytical object nor the audit event.

## Prohibited endpoints and behavior

- no generic `PATCH` for findings, contradictions, snapshots or audit events;
- no `DELETE` for evidentiary records;
- no mutation of canonical evidence text, tier, confidence or review status;
- no automatic contradiction collapse;
- no automatic promotion of pending evidence;
- no accepted finding without contradiction review;
- no direct SQL write path outside the transactional service.

Corrections are represented by superseding records or compensating commands and audit events.

## Persistence boundary

SQLite constraints enforce local checks, visibility vocabulary, JSON validity, restrictive foreign keys and append-only audit rows. Cross-record invariants remain the responsibility of the transactional service because canonical evidence may live outside the Case Manager database boundary.

## Consequences

This design creates more command types than a generic CRUD API, but it preserves analytical intent and auditability. The UI must call commands matching user actions rather than editing database records directly.

## Deferred decisions

- authentication provider and role vocabulary;
- pagination and search syntax;
- optimistic concurrency token format;
- snapshot export media types;
- production database topology;
- controlled registries for case, claim, event, lead and severity values.
