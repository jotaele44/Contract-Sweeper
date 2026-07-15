# Fusion Engine Methodology

The **FUSION** layer produces *deterministic, evidence-backed, cross-domain joins* over the
`FIN_AUDIT` and `INF_CTRL` domains. It resolves records to canonical entities, builds typed
relationship edges that always carry a source, and exposes documented cross-layer paths —
**without** drawing influence or wrongdoing conclusions.

This methodology reuses existing repo machinery rather than re-implementing it:

- Deterministic IDs: `moneysweep/runtime/canonical_ids.py`
  (`entity_id`, `edge_id`, `evidence_id`; pure functions of payload — same input, same id).
- Name normalization: `moneysweep/runtime/name_normalization.py`
  (`normalize_name`, `normalize_person_name`).
- Evidence-backed edge model: `schemas/canonical_v1/edges.schema.json`,
  `schemas/canonical_v1/evidence.schema.json`, `schemas/entity_master.schema.json`.

## 1. Canonical identifier hierarchy

Resolution prefers the most authoritative identifier available. Only the identifiers marked
**authoritative** can, on their own, justify an auto-merge.

| Priority | Identifier | Authoritative |
|---|---|---|
| 1 | UEI | yes |
| 2 | CAGE | yes |
| 3 | Puerto Rico corporation registration number | yes |
| 4 | EIN (where lawfully available) | yes |
| 5 | DUNS (historical records) | yes |
| 6 | Government agency code | yes |
| 7 | Municipality code | yes |
| 8 | Lobby-registration number | no (contextual) |
| 9 | Contracting-system vendor identifier | no (contextual) |
| 10 | Deterministic internal canonical ID | no (assigned, not evidentiary) |

**Temporal validity.** Historical identifiers (notably DUNS) are preserved, not discarded.
Every identifier carries `valid_from` / `valid_to` / `source_date`, so an obsolete id still
resolves longitudinal records to the correct entity for the period it was valid. See
`moneysweep/entity_resolution/keys.py`.

## 2. Match features

`moneysweep/entity_resolution/scoring.py` combines:

`exact_identifier`, `normalized_legal_name`, `registered_alias`, `address_similarity`,
`telephone_match`, `officer_or_authorized_person_overlap`, `parent_subsidiary_relationship`,
`contract_number_context`, `lobby_client_context`, `temporal_overlap`,
`municipality_and_project_context`.

**Name similarity alone must never trigger an auto-merge.** The scorer caps any candidate
whose only evidence is name/alias similarity strictly below the auto-merge threshold.

## 3. Resolution thresholds

| Score | Action |
|---|---|
| ≥ 0.95 | Auto-merge **only** with a unique authoritative identifier |
| 0.85 – 0.949 | Suggested merge; human review required |
| 0.65 – 0.849 | Possible relationship; **do not merge** |
| < 0.65 | Keep separate |

Non-merged candidates are preserved (as suggested merges or possible relationships), never
deleted. See `moneysweep/entity_resolution/resolver.py`.

## 4. Approved predicates

Relationship edges use a fixed predicate whitelist (`moneysweep/fusion/models.py`):

```
AWARDED_CONTRACT_TO   AMENDS_CONTRACT        TRANSFERRED_FUNDS_TO
RECEIVED_GRANT_FROM   SUBCONTRACTED_TO       LOBBIED_FOR
AUTHORIZED_PERSON_FOR EMPLOYED_BY            BOARD_MEMBER_OF
REGISTERED_AS         OWNS                   CONTROLS
AFFILIATED_WITH       OPERATES_PROJECT       LOCATED_AT
SERVES_MUNICIPALITY   FUNDED_PROJECT         INSPECTED_ASSET
REPORTED_EXPENDITURE_FOR                     PREPARED_REPORT_FOR
```

`PREPARED_REPORT_FOR` supports engineering-report authorship (e.g. a consulting-engineer
report). There is deliberately **no** `INFLUENCED`, `CAPTURED`, `COORDINATED_WITH`, or
similar conclusory predicate.

Every edge requires: `source_record_id`, an `assertion_type`
(`explicit` | `derived` | `inferred`), an `evidence_tier` (T1–T4), and a `confidence`.
`edge_builder.build_edge` raises if `source_record_id` is missing or the predicate is not
approved.

## 5. Prohibited inference pattern

A documented path such as:

```
contractor  --LOBBIED_FOR-->  (via firm)  --AUTHORIZED_PERSON_FOR-->  official
```

must **never** be collapsed into:

```
contractor  --INFLUENCED-->  official
```

The engine may surface the documented path (each hop evidence-backed). "Influence" is an
analytical hypothesis, not a fusion output. It requires an explicit record, temporal
evidence linked to a policy outcome, or additional corroboration — and is published only via
the review pipeline. `join_engine.cross_layer_join(...)` always returns
`influence_conclusion: null`.

## 6. Assertion types

| Type | Meaning |
|---|---|
| `explicit` | Stated directly in a source record (e.g. "X is the preparer of report Y"). |
| `derived` | Deterministically computed from explicit facts (e.g. resolving a variant name to a canonical entity). |
| `inferred` | A weaker analytical link. **Never public without review**; never a conclusion. |

## 7. Contradictions

Conflicting claims are **stored side-by-side**, not overwritten
(`moneysweep/fusion/contradictions.py`). A contradiction carries a status
(`none` | `unresolved` | `resolved`). Source disagreement is data to preserve, not an error
to silently reconcile.
