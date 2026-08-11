# MoneySweep Case Manager Phase 1 API Contract v0.12

## Scope

This phase adds an API-only, SQLite-backed Case Manager service stacked on PR #440. It does not implement production UI, mutate canonical evidence, promote evidence, collapse contradictions automatically, expose generic `PATCH`, or expose deletion routes.

## Runtime

```bash
uvicorn server.backend.case_manager_app:app --reload --port 8001
```

The database path defaults to `data/case_manager.sqlite3` and may be overridden with `MONEYSWEEP_CASE_DB`.

## Authorization boundary

Clients supply:

- `X-Case-Actor` on commands;
- `X-Case-Clearance: public|internal|restricted` on queries.

The current policy is a bounded Phase 1 clearance filter, not a replacement for the future authenticated identity provider. Records above the caller clearance are omitted.

## Read endpoints

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

## Command endpoints

- `POST /cases`
- `POST /cases/{case_id}/evidence-links`
- `POST /cases/{case_id}/claims`
- `POST /cases/{case_id}/claims/{claim_id}/evidence-relations`
- `POST /cases/{case_id}/contradictions`
- `POST /cases/{case_id}/contradictions/{contradiction_id}/resolution`
- `POST /cases/{case_id}/leads`
- `POST /cases/{case_id}/leads/{lead_id}/closure`
- `POST /cases/{case_id}/findings`
- `POST /cases/{case_id}/findings/{finding_id}/acceptance`
- `POST /cases/{case_id}/snapshots`

## Transaction contract

Every command:

1. validates the command boundary;
2. starts `BEGIN IMMEDIATE`;
3. writes the analytical object or explicit lifecycle transition;
4. verifies the latest audit sequence and predecessor hash;
5. appends exactly one audit event;
6. commits once.

A failure in either the object write or audit append rolls back both. Concurrent writers that observed a stale audit sequence receive a conflict instead of creating a forked audit chain.

## Canonical evidence boundary

The service accepts canonical identifiers matching `evidence_*` for links, lead closure, and snapshots. The Case Manager schema contains no canonical evidence table and exposes no operation that can alter evidence text, tier, review status, or promotion state.

## Persistence certificate

- migration: `migrations/001_case_manager_v1.sql`;
- foreign keys: enabled;
- deletion behavior: restrictive;
- audit events: append-only triggers plus service-level sequence/hash verification;
- JSON arrays: SQLite JSON1 checks;
- canonical writes: none;
- generic update/delete API: absent.
