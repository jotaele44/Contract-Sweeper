# MoneySweep Case Manager Schema Foundation v0.1

## Status

Schema-first foundation. No production UI, canonical evidence mutation, data promotion, or merge is included.

## Domain coverage

| Object | Implementation | Key invariant |
|---|---|---|
| Case | `Case`, `cases` | Neutral bounded scope and field-level visibility |
| Case evidence | `CaseEvidence`, `case_evidence` | References existing canonical `evidence_id`; never rewrites evidence |
| Claim | `Claim`, `claims` | Separate identity and lifecycle from findings |
| Claim evidence | `ClaimEvidence`, `claim_evidence` | Explicit `support`, `contradict`, `qualify`, `supersede` relation |
| Case entity | `CaseEntity`, `case_entities` | Case-specific role and temporal validity |
| Case event | `CaseEvent`, `case_events` | Timeline object with source evidence references |
| Contradiction | `Contradiction`, `contradictions` | Minimum two claims; defaults open; no automatic collapse |
| Lead | `Lead`, `leads` | Actionable question, acquisition target and closure evidence |
| Finding | `Finding`, `findings` | Must reference a distinct claim; accepted findings require contradiction review |
| Case snapshot | `CaseSnapshot`, `case_snapshots` | Immutable manifest digest and evidence set |
| Audit event | `AuditEvent`, `case_audit_events` | Contiguous append-only sequence and hash-chain fields |

All analytical objects carry `public`, `internal`, or `restricted` visibility. The persistence layer enforces the same vocabulary. Authorization services may narrow access further but must not broaden an object's stored visibility.

## Canonical evidence crosswalk

Case Manager stores only references to `canonical_v1/evidence.schema.json` identifiers. Evidence tier, confidence and review status remain owned by the canonical evidence pipeline. Case claims use the existing claim-language vocabulary: `observed`, `linked`, `inferred`, and `blocked`.

New imports default to pending review. The Carraízo fixture is explicitly `read_only_pending_review` with `canonical_promotion=false`.

## Migration ledger

`migrations/001_case_manager_v1.sql` is additive:

- creates eleven Case Manager tables;
- adds explicit `ON DELETE RESTRICT` foreign-key policy;
- does not alter existing canonical tables or rows;
- treats money as decimal strings at the domain boundary;
- validates serialized JSON columns with SQLite JSON1 `json_valid` checks;
- applies visibility checks consistently;
- adds indexes for expected case, evidence, timeline, status and audit queries;
- installs update/delete blocking triggers on the audit-event table.

The supported persistence boundary is the transactional Case Manager service. Direct SQL writes are unsupported because cross-record invariants such as same-case claim/finding linkage, contradiction membership, canonical evidence existence and audit hash chaining require application validation.

## Schema dependency policy

`jsonschema` is a development and certification dependency, not a required production runtime dependency. The primary test environment must install it and execute Draft-07 meta-validation. Reduced bootstrap workflows may use `pytest.importorskip("jsonschema")`; such a skip is not a schema certificate. A release or readiness certificate is valid only when the primary `Tests` workflow executes the schema test successfully.

## Rollback policy

### Pre-production rollback

Destructive rollback is permitted only before accepted Case Manager data exists:

1. verify every Case Manager table is empty;
2. verify no deployment or migration registry depends on the migration;
3. drop append-only triggers;
4. drop tables in reverse dependency order;
5. remove the migration registration.

### Production rollback

After persistent case data exists, rollback is forward-only:

1. disable new Case Manager writes;
2. preserve all Case Manager tables and audit events;
3. export and hash a database snapshot;
4. deploy a compatibility adapter or corrective forward migration;
5. never delete accepted evidence links, findings, snapshots or audit events.

A destructive `down.sql` is intentionally not supplied.

## Tests

`tests/test_case_manager_foundation.py` covers:

1. deterministic and idempotent identifiers;
2. claim/finding separation;
3. explicit evidence relations;
4. contradiction hold-apart behavior;
5. contradiction review before accepted findings;
6. audit-event sequence and hash-chain validation;
7. Draft-07 schema meta-validation and full visibility coverage;
8. migration double application from clean state;
9. SQLite visibility and JSON constraints;
10. explicit restrictive foreign-key behavior;
11. required query indexes;
12. SQLite append-only trigger enforcement;
13. read-only, non-promoted Carraízo fixture state.

## Phase 1 API boundary

The Phase 1 command/query contract is defined in `docs/adr/ADR_CASE_MANAGER_PHASE_1_API_BOUNDARY.md`. Generic update and delete endpoints are prohibited for evidentiary records. Successful commands must validate authorization and references, write the new or superseding record, append an audit event and commit atomically.

## Remaining UI dependencies

- Case Index and Case Overview implementation;
- dedicated Claims, Timeline and Financials views;
- Reconcile queue with reviewer, severity and resolution rationale;
- Gaps-to-Leads assignment workflow;
- field-level authorization and redaction profiles;
- immutable snapshot/export service;
- responsive and accessibility certification;
- production persistence adapter and migration runner.

## Known limits

The foundation does not independently verify that a referenced `evidence_id` exists in a database; the validator accepts an explicit set of canonical evidence IDs from the caller. Cross-table enforcement against the existing evidence storage must be added once its production database boundary is confirmed.
