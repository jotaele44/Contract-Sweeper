# Publication & Correction Policy

Defines how a research product (a dataset, an edge, an observation, a report) moves from
internal working state to public, and how corrections and right-of-reply are handled. This
policy operationalizes the mandatory controls in
[`nonprofit_layer_legal_scope.md`](nonprofit_layer_legal_scope.md) and works with the claim
rules in [`CLAIM_LANGUAGE_POLICY.md`](CLAIM_LANGUAGE_POLICY.md).

## Review states

Records advance through four states (see `schemas/publication_review.schema.json`):

| State | Meaning | Gate to advance |
|---|---|---|
| `internal` | Working data; not for publication. | Assigned reviewer. |
| `legal_review` | Checked for legal risk, PII, and claim-language compliance. | Legal sign-off. |
| `fact_check` | Every claim traced to a source record; evidence tier confirmed. | Fact-checker sign-off. |
| `public` | Eligible for publication. | Publication approval recorded. |

A record may only move forward one state at a time, and every transition is logged with the
reviewer and timestamp. Moving to `public` requires that `fact_check` was completed.

## Publication gate (enforced in code)

`moneysweep/fusion/publication_gate.py` blocks publication unless **all** hold:

1. The edge/observation has a `source_record_id` (evidence-required rule).
2. Its review status reached `fact_check` and publication is approved.
3. `assertion_type` is not `inferred` — inferred links are never published automatically;
   they require explicit human review first.
4. No PII beyond the minimized, necessary set is present.
5. The edge is not a guilt-by-association construct (its basis is a documented relationship,
   not mere proximity).

## Evidence tiers

Publication weight follows the existing tiering (`T1` strongest … `T4` weakest;
see `confidence_model.md` / `canonical_v1/evidence.schema.json`). Lower-tier evidence may be
collected and retained internally but is held to stricter review before any public claim.

## Corrections

- Every published product carries a stable identifier and supports a **correction log**.
- A correction records: what changed, why, the date, and the superseded value.
- Corrections do not silently overwrite history; the prior state is retained.

## Right of reply

Before publishing a research product that names a person or organization in a
relationship, the subject is offered a right of reply where practicable. A submitted reply
is preserved and linked to the product. Declining to reply is not treated as agreement or
admission.

## Nonpartisanship

Every published product records a nonpartisanship attestation and applies uniform inclusion
criteria. Selection of subjects is driven by documented financial/lobbying records, not by
party or affiliation.
