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

## Canonical evidence crosswalk

Case Manager stores only references to `canonical_v1/evidence.schema.json` identifiers. Evidence tier, confidence and review status remain owned by the canonical evidence pipeline. Case claims use the existing claim-language vocabulary: `observed`, `linked`, `inferred`, and `blocked`.

New imports default to pending review. The Carraízo fixture is explicitly `read_only_pending_review` with `canonical_promotion=false`.

## Migration ledger

`migrations/001_case_manager_v1.sql` is additive:

- creates eleven Case Manager tables;
- adds foreign keys within the Case Manager domain;
- does not alter existing canonical tables or rows;
- treats money as decimal strings at the domain boundary;
- installs update/delete blocking triggers on the audit-event table.

Rollback for the draft foundation is table removal in reverse dependency order. Production rollback should be implemented only after repository migration tooling and deployment topology are confirmed.

## Tests

`tests/test_case_manager_foundation.py` covers:

1. deterministic and idempotent identifiers;
2. claim/finding separation;
3. explicit evidence relations;
4. contradiction hold-apart behavior;
5. contradiction review before accepted findings;
6. audit-event sequence and hash-chain validation;
7. SQLite append-only trigger enforcement;
8. read-only, non-promoted Carraízo fixture state.

## Remaining UI dependencies

- Case Index and Case Overview API contracts;
- dedicated Claims, Timeline and Financials views;
- Reconcile queue with reviewer, severity and resolution rationale;
- Gaps-to-Leads assignment workflow;
- field-level authorization and redaction profiles;
- immutable snapshot/export service;
- responsive and accessibility certification;
- production persistence adapter and migration runner.

## Known limits

The foundation does not independently verify that a referenced `evidence_id` exists in a database; the validator accepts an explicit set of canonical evidence IDs from the caller. Cross-table enforcement against the existing evidence storage must be added once its production database boundary is confirmed.
