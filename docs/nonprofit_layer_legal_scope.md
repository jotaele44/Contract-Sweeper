# Nonprofit / Public-Interest Layer — Legal & Governance Scope

> **This is a technical governance specification, not a determination of nonprofit
> eligibility and not legal advice.** Nothing here decides tax status, incorporation,
> or the legality of any specific activity. Obtain Puerto Rico and federal nonprofit
> counsel before incorporation or fundraising (see [Unresolved gaps](#unresolved-legal-gaps)).

The **NP_LAYER** is the civic / public-interest boundary of this repository. It governs
how publicly available records are collected, reviewed, and published. It sits above the
analytical domains (`FIN_AUDIT`, `INF_CTRL`) and the `FUSION` layer, and constrains what
they may publish.

Related, already-established policy:
[`CLAIM_LANGUAGE_POLICY.md`](CLAIM_LANGUAGE_POLICY.md),
[`confidence_model.md`](confidence_model.md),
[`DATA_POLICY.md`](DATA_POLICY.md),
[`publication_and_correction_policy.md`](publication_and_correction_policy.md),
[`fusion_engine_methodology.md`](fusion_engine_methodology.md).

## Permitted scope

| Function | Classification |
|---|---|
| Collect and preserve publicly available records | Permitted |
| File and track public-record requests | Permitted |
| Publish sourced datasets and methodologies | Permitted |
| Produce nonpartisan financial and institutional research | Permitted |
| Conduct public education and transparency work | Permitted |
| Identify documented relationships | Permitted **with evidence and neutral language** |
| Characterize a person/entity as corrupt, captured, criminal, or coordinated | **Prohibited** without authoritative findings |
| Coordinate electoral advocacy through the research system | **Excluded** from initial scope |
| Publish personal contact information or unnecessary personal data | **Prohibited** |
| Merge donor, lobbying, political, and contract data without provenance | **Prohibited** |

"Authoritative findings" means a court judgment, an audit finding by a competent
oversight body (e.g. Office of the Comptroller / OIG), a regulatory determination, or a
comparable official adjudication — not press coverage and not the system's own inference.

## Mandatory controls

1. **Nonpartisanship field** on every published research product; uniform inclusion
   criteria applied regardless of party or affiliation.
2. **Publication-review status:** `internal → legal_review → fact_check → public`
   (see `schemas/publication_review.schema.json`).
3. **Evidence-required rule:** no public relationship edge without a source record
   (`source_record_id`). Enforced in `moneysweep/fusion/edge_builder.py`.
4. **Observation vs. allegation separation:** the system records *documented observations*,
   not allegations. An observation states what a source shows; it does not assert intent,
   wrongdoing, or causation.
5. **No guilt-by-association scoring:** proximity or shared association never raises an
   entity's risk/score and never creates a conclusory edge. Enforced in
   `moneysweep/fusion/publication_gate.py`.
6. **Right-of-reply and correction log:** every published product supports a correction
   entry and a subject response (see `publication_and_correction_policy.md`).
7. **PII minimization and redaction:** collect and publish the minimum personal data
   necessary; redact contact details and non-essential personal identifiers.
8. **Conflict-of-interest declarations** for researchers and board members.

## Observation vs. allegation — required framing

| Allowed (observation) | Not allowed (allegation / conclusion) |
|---|---|
| "Entity A prepared a consulting-engineer report for Utility B (source: …)." | "Entity A is entrenched at Utility B." |
| "Entity A appears as a lobbying client of Firm C (source: …)." | "Entity A bought influence over Utility B." |
| "The records show A both prepared B's report and lobbied via C." | "A influenced B's decisions." |

The `FUSION` engine may **expose a documented path** between entities. It must never label
that path as "influence", "capture", or "coordination". Influence remains an analytical
hypothesis unless supported by an explicit record, temporal evidence tied to a policy
outcome, or additional corroboration — and even then it is published only through the
review pipeline, never generated automatically.

## Unresolved legal gaps

| Risk | Control / required next step |
|---|---|
| Nonprofit law and tax classification unresolved | Obtain PR + federal nonprofit counsel before incorporation or fundraising |
| Political research misread as partisan activity | Nonpartisan methodology, uniform inclusion criteria, publication review |
| Sensitive personal data | PII minimization + access classification (`access_class`) |
| Public statements exceeding evidence | Evidence-tier and publication gates |

This document defines boundaries for engineering. It does not authorize incorporation,
fundraising, or any public statement; those require the review pipeline and, where noted,
qualified counsel.
