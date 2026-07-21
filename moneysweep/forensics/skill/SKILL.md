---
name: contract-forensics
description: Exhaustive graph-first investigation of public contracts, contractors, projects, agencies, corporate families, awards, modifications, subcontractors, payments, audits, litigation, oversight, and outcomes. Builds a time-aware canonical entity and award graph before drawing conclusions, measures coverage by domain, runs capacity and pass-through tests, resolves acquisitions/divestitures/novations, reports null results and contradictions, and explains WHY an outcome occurred using ranked competing hypotheses. Use for government contracts, procurement, public works, disaster recovery, contractor family trees, corporate lineage, audit reports, registries, financial statements, cost overruns, abandoned projects, no-bid awards, subcontracting, lobbying overlap, or “where did the money go” questions. Works for any jurisdiction and includes specialized Puerto Rico tooling for OCPR, Registro de Corporaciones, Contralor reports, PRASA, PREPA, ACT, COR3, FEMA, USACE, and related sources.
---

# Contract Forensics v2 — Graph-First Major Upgrade

Build the evidence graph first. Explain the outcome only after the graph is exhausted.

```text
ENTITY GRAPH → AWARD GRAPH → SUBAWARD GRAPH → MONEY GRAPH → OUTCOME GRAPH → WHY
```

The operating objective is **maximum defensible public-data coverage in the fewest rounds**. A run is not complete merely because a plausible narrative has been found. It is complete when the required queues have been processed, contradictions have been reviewed, domain coverage has been quantified, and remaining gaps have been classified.

---

## 0. THE DISCIPLINE — NON-NEGOTIABLE

This skill exists because plausible detail can be fabricated accidentally. A correct guess and a confabulation are indistinguishable from inside the model.

1. **Never assert a name, number, date, ownership link, award, or outcome without a citation.**
2. **A silent or empty tool response is not a finding.** Record the search as failed or null and retry by a different route.
3. **Label every material claim with an evidence tier.**
4. **Report passes and nulls.** Do not force suspicious patterns.
5. **Separate ownership from name similarity.** Shared words, addresses, officers, or branding are not ownership proof by themselves.
6. **Make corporate relationships time-aware.** Record owner at award, current owner, acquisition/divestiture date, novation date, and successor.
7. **Never collapse legal entities merely because they share a parent.** Preserve UEI, CAGE, DUNS, EIN when public, jurisdiction, address, and effective dates.
8. **Retract loudly.** If a prior assertion was unsourced or contradicted, mark it withdrawn.
9. **Do not claim 100% when inaccessible records exist.** State practical public-data coverage and identify structural limits.

### Evidence tiers

| Tier | Meaning |
|---|---|
| **T1** | Primary/authoritative: contracts, registries, SEC/corporate filings, audited financials, court filings, audit reports, agency payment records, official project records. |
| **T2** | Credible secondary: investigative reporting tied to named documents; official statements not accompanied by the underlying record. |
| **T3** | Circumstantial: shared address, timing, name overlap, personnel overlap, website claims. Suggestive, not probative. |
| **T4** | Analytic inference or hypothesis. Must identify the supporting evidence and alternative explanations. |
| **T0** | Gap/null: searched and not found, inaccessible, withheld, sealed, purged, or not applicable. |

---

## 1. OPERATING MODEL: ONE BROAD RUN, THEN TARGETED GAP CLOSURE

Use a **single broad fan-out round** wherever tools and time permit. Do not search one alias at a time and write prose between searches.

### Round 0 — Scope contract

Resolve or infer:

- root entity, project, agency, or award
- jurisdiction and time range
- whether the request includes the full corporate family
- required outputs: ledger, graph, narrative, timeline, risk matrix, FOIA plan
- public-data ceiling and unavailable-source constraints

Do not narrow “all subsidiaries/spinoffs/everything” to significant subsidiaries only. Use significant-subsidiary filings as seeds, then expand recursively.

### Round 1 — Graph-first exhaustive discovery

Run entity, award, subaward, outcome, oversight, financial, litigation, and influence discovery in parallel. Populate the canonical tables before narrative drafting.

### Round 2 — Gap closure only

After the first synthesis, run only searches that target:

- unresolved ownership edges
- unidentified awardees or subcontractors
- missing modifications/payments
- conflicting values or dates
- successor/novation uncertainty
- low-coverage domains

### Round 3 — Optional record acquisition

FOIA, public-records requests, PACER purchases, archived-site recovery, or user-provided documents. Clearly distinguish this from immediate public-source coverage.

---

## 2. CANONICAL DATA MODEL

Create these internal tables or equivalent structured records before final analysis.

### 2.1 `entities`

| Field | Requirement |
|---|---|
| `entity_id` | Stable internal ID |
| `legal_name` | Exact authoritative name |
| `normalized_name` | Search normalization only |
| `entity_type` | parent, subsidiary, JV, SPV, predecessor, successor, branch, DBA, government entity |
| `jurisdiction` | Incorporation/registration jurisdiction |
| `status` | active, dissolved, merged, withdrawn, unknown |
| `formed_date` / `dissolved_date` | Effective dates where known |
| `uei`, `cage`, `duns`, `ein_public` | Preserve separately |
| `addresses` | Time-stamped if possible |
| `source_ids` | Registry/filing IDs |
| `evidence_tier` | Edge/node support |

### 2.2 `entity_aliases`

Store exact alias, alias type, effective dates, source, and confidence.

Alias types:

- former legal name
- current legal name
- DBA/trade name
- abbreviation
- punctuation/suffix variant
- transliteration/translation
- misspelling found in source
- acquired brand
- division name
- award-recipient display name

### 2.3 `entity_relationships`

| Field | Requirement |
|---|---|
| `parent_entity_id` / `child_entity_id` | Do not infer from naming alone |
| `relationship_type` | owns, controlled-by, predecessor-of, successor-of, merged-into, divested-to, JV-member, DBA-of, branch-of |
| `ownership_percent` | If known |
| `effective_from` / `effective_to` | Mandatory when material |
| `transaction_type` | acquisition, spin-off, Reverse Morris Trust, asset sale, merger, novation |
| `source` / `tier` | Required |

### 2.4 `awards`

Minimum fields:

- award ID / PIID / contract number
- parent award and task/delivery order IDs
- agency and subagency
- exact recipient legal entity and identifiers
- owner at award and current owner
- award type, procurement method, competition, statutory authority
- description and project
- place of performance
- signed, start, end, closeout dates
- base value, current value, ceiling, obligations, outlays/payments
- funding source/program/disaster declaration
- source and tier

### 2.5 `award_transactions`

One row per modification, amendment, obligation, deobligation, option, extension, novation, termination, settlement, or payment event.

### 2.6 `subawards`

Preserve prime, subrecipient, tier level, amount, date, scope, self-subcontract status, affiliate status, and source.

### 2.7 `projects`

Link announced project, funded project, procurement package, construction contract, design contract, CEI/inspection contract, grants, permits, and physical outcome.

### 2.8 `evidence`

Each material claim receives:

- claim ID
- subject/predicate/object
- source URI/document/page/line
- evidence tier
- date accessed
- quote or structured extraction
- contradiction group if applicable

### 2.9 `gaps`

Classify each missing field as:

- `NOT_SEARCHED`
- `SEARCHED_NOT_FOUND`
- `SOURCE_INACCESSIBLE`
- `RECORD_PURGED`
- `SEALED_OR_CONFIDENTIAL`
- `REQUIRES_FOIA`
- `REQUIRES_PACER`
- `REQUIRES_USER_BROWSER`
- `NOT_APPLICABLE`
- `SUCCESSOR_UNRESOLVED`
- `IDENTITY_UNRESOLVED`

---

## 3. ENTITY GRAPH FIRST

Do not begin award totals until the entity seed set is stable enough to search comprehensively.

### 3.1 Seed sources

Use, as applicable:

- SEC exhibits and annual reports
- official corporate subsidiary lists
- merger/acquisition announcements and transaction filings
- state/territorial corporate registries
- SAM entity records
- historical DCAA active-contractor listings
- CAGE/DUNS/UEI records
- official corporate websites and archived websites
- court filings and bankruptcy schedules
- competition decisions and novation notices
- lobbying registrations that disclose exact client entities

### 3.2 Recursive expansion queue

Maintain queues:

```text
ENTITY_QUEUE
ALIAS_QUEUE
RELATIONSHIP_QUEUE
IDENTIFIER_QUEUE
JV_QUEUE
SUCCESSOR_QUEUE
```

For every confirmed entity, test:

- parent and ultimate parent
- direct and indirect subsidiaries
- predecessor names
- acquired entities and brands
- divested businesses
- spun-off entities
- successors and novated contractors
- joint ventures and members
- special-purpose vehicles
- branches and local operating entities
- dissolved entities with historical awards
- foreign affiliates relevant to the jurisdiction or award

Continue until an expansion cycle returns no new confirmed nodes or edges, or until remaining leads are explicitly downgraded to T0/T3.

### 3.3 Alias explosion

Generate and search:

- punctuation and suffix variants
- `&` versus `AND`
- initials and compressed forms
- legacy names
- DBA names
- source-specific misspellings
- Spanish/English variants
- parenthetical division names
- hyphen and spacing variants
- names embedded in JV names

Never treat generated aliases as confirmed aliases until a source links them.

### 3.4 Time-aware attribution

For every award, calculate:

```text
LEGAL_RECIPIENT_AT_AWARD
PARENT_AT_AWARD
CURRENT_PARENT
SUCCESSOR_CONTRACTOR
NOVATION_EFFECTIVE_DATE
ATTRIBUTION_PERIOD
```

Historical awards remain part of a predecessor lineage, but post-divestiture obligations belong to the successor when the contract was transferred or novated.

---

## 4. PARALLEL SOURCE FAN-OUT

Search source families concurrently where possible. Deduplicate only after preserving source-specific identifiers.

### 4.1 Corporate and financial

- SEC EDGAR and equivalent securities filings
- audited financial statements
- annual reports and subsidiary exhibits
- corporate registries
- bankruptcy and lien records
- credit facilities and bond disclosures

### 4.2 Federal procurement

- USAspending prime awards and subawards
- FPDS-derived transaction records
- SAM entity records and exclusions
- agency procurement forecasts and award notices
- DCAA active-contractor listings
- federal audit and inspector-general reports
- GAO bid protests and decisions

### 4.3 State, territorial, and local procurement

- contract registries
- agency contract lists
- transition reports
- comptroller/contralor reports
- procurement portals
- payment/checkbook systems
- legislative appropriations
- municipal awards

### 4.4 Project and outcome

- capital improvement plans
- FEMA/COR3 project inventories
- engineering deliverables
- permits and environmental reviews
- inspection/CEI contracts
- progress reports
- completion and closeout records
- consent decrees and regulatory filings
- GIS/project-location records

### 4.5 Litigation, enforcement, and influence

- court dockets
- DOJ/OIG/AG enforcement
- suspension/debarment records
- lobbying registrations
- campaign-finance records where relevant and lawful
- ethics disclosures
- legislative testimony

Influence overlap is never proof of causation. It is a separate graph requiring chronology and cross-source corroboration.

### 4.6 Archives and secondary sources

Use archived websites when live sources are missing. Use credible journalism to locate primary records, not as a substitute when the primary record is available.

---

## 5. DOCUMENT INGESTION

Do not summarize uploaded documents. Interrogate them and register every useful join key.

Read `references/interpreting-documents.md` for document-specific extraction.

### Required extraction passes

1. **Identity pass:** names, IDs, addresses, officers, agencies.
2. **Award pass:** contract numbers, amounts, dates, amendments, procurement method.
3. **Money pass:** obligations, invoices, payments, disbursements, questioned costs.
4. **Project pass:** scope, location, milestones, deliverables, status.
5. **Oversight pass:** inspectors, CEI, auditors, monitoring terms, missing records.
6. **Contradiction pass:** inconsistent names, values, dates, or descriptions.
7. **Lead pass:** references to attachments, exhibits, external records, and omitted documents.

For PDFs, inspect tables/images using page rendering when parsed text is insufficient. OCR only when necessary.

---

## 6. AWARD-CENTRIC CHAIN

For every award or project, build:

```text
PROJECT
  ├─ FUNDING AUTHORITY
  ├─ PROCUREMENT
  ├─ PRIME AWARD
  │    ├─ MODIFICATIONS
  │    ├─ PAYMENTS
  │    ├─ SUBAWARDS
  │    ├─ AFFILIATED SUBCONTRACTS
  │    └─ NOVATION/SUCCESSOR EVENTS
  ├─ DESIGN/PROGRAM MANAGEMENT
  ├─ CEI/INSPECTION/OVERSIGHT
  ├─ AUDITS/LITIGATION
  └─ PHYSICAL AND FINANCIAL OUTCOME
```

### Award completeness rule

A base award without transaction history is incomplete. Search separately for:

- modifications and amendments
- task/delivery orders
- option exercises
- extensions
- deobligations
- novations
- terminations
- closeout
- payment/outlay records

---

## 7. CORE DIAGNOSTICS

### 7.1 Pass-through test

```text
external_subaward_amount / prime_obligations
```

Classify:

- `>80%`: likely conduit/billing layer, subject to sector context
- `40–80%`: heavy subcontracting
- `<20%`: predominantly self-performing

Exclude or separately classify:

- parent-to-subsidiary transfers
- subsidiary-to-parent transfers
- JV member allocations
- entities acquired during performance
- post-novation successor transactions

Do not call missing subaward data a 0% ratio.

### 7.2 Capacity test

Measure at award date and legal-awardee level:

- award value ÷ prior-year revenue
- award value ÷ equity
- staff/officer count
- equipment and fixed assets
- credit facilities
- relevant prior work
- federal/state award history
- licenses and professional capacity
- local presence versus parent support

A consolidated-parent pass does not automatically prove subsidiary-level capacity.

Use `scripts/capacity_test.py` where applicable.

### 7.3 Oversight-vacuum test

Compare construction/performance term with:

- design oversight
- CEI/inspection
- program management
- monitoring
- independent engineering
- audit coverage

If oversight expired while performance continued, test whether missing records were never generated.

### 7.4 Procurement-machine test

Score as a hypothesis generator:

1. emergency authority
2. bidding exemption or sole source
3. capacity gap
4. pass-through
5. waiver over objection
6. missing evaluation

Add aggravators only with evidence: federal reimbursement, repeated adverse findings, recurring actors, unusual chronology.

### 7.5 Outcome test

Compare:

- promised scope
- contracted scope
- modified scope
- paid amount
- delivered work
- completion date
- current physical condition
- audit/regulatory outcome

---

## 8. CONTRADICTION ENGINE

Create a contradiction record whenever authoritative sources disagree on:

- legal name or recipient
- parentage
- award amount
- start/end dates
- project status
- payments
- subcontractor identity
- ownership/successor

For each contradiction report:

```text
CONTRADICTION_ID
CLAIM_A + SOURCE/TIER
CLAIM_B + SOURCE/TIER
LIKELY_CAUSE
CONTROLLING_SOURCE
RESOLUTION_STATUS
```

Typical benign causes include amendments, fiscal-year snapshots, rounding, trade names, database lag, and novation. Do not treat disagreement as misconduct without evidence.

---

## 9. COVERAGE ENGINE

Coverage is not a subjective feeling. Calculate it by domain.

### 9.1 Domain coverage

Required domains:

| Domain | Denominator concept |
|---|---|
| Parent/ownership graph | confirmed/expected ownership edges from authoritative seeds |
| Subsidiaries | verified entities versus disclosed and discovered candidates |
| Aliases/identifiers | verified aliases and identifiers versus candidates |
| Acquisitions/predecessors | transactions and predecessor nodes resolved |
| Spinoffs/successors | divestitures, novations, successor periods resolved |
| Joint ventures | JVs identified and member/control relationships resolved |
| Prime awards | award sources searched and deduplicated; transaction coverage |
| Modifications | base awards with complete modification histories |
| Payments/outlays | awards with payment/outlay evidence |
| Subawards | awards with searched and classified subcontract data |
| Financial capacity | awardees with award-date financial/capacity evidence |
| Oversight | projects with inspector/CEI/monitoring term resolved |
| Outcomes | projects with financial and physical outcome evidence |
| Audits/enforcement | relevant oversight sources searched |
| Litigation | relevant dockets searched and material cases resolved |
| Influence | lobbying/campaign/ethics sources searched where relevant |
| Jurisdiction-specific | required local source families searched |

### 9.2 Weighted state model

Assign each required item:

- `1.0` confirmed/resolved
- `0.75` strongly supported but missing one authoritative field
- `0.5` partially resolved
- `0.25` lead only
- `0.0` not searched or unresolved
- exclude only when `NOT_APPLICABLE`

Report both:

```text
PUBLIC_DATA_COVERAGE
RESOLVABLE_COVERAGE
```

`PUBLIC_DATA_COVERAGE` includes inaccessible records in the denominator. `RESOLVABLE_COVERAGE` excludes demonstrably sealed, confidential, destroyed, or structurally unavailable records. Never hide the distinction.

### 9.3 Confidence

Coverage and confidence are separate:

- high coverage can still contain low-confidence T3 links
- low coverage can contain a few high-confidence T1 findings

Report both.

---

## 10. EXHAUSTION AND STOP GATES

A broad run may close only after these queues are empty or every remaining item is classified:

```text
NEW_CONFIRMED_ENTITY = 0
NEW_CONFIRMED_ALIAS = 0
NEW_OWNERSHIP_EDGE = 0
NEW_IDENTIFIER = 0
NEW_JV = 0
NEW_SUCCESSOR_OR_NOVATION = 0
NEW_PRIME_AWARD = 0
NEW_MODIFICATION = 0
NEW_PAYMENT = 0
NEW_SUBAWARD = 0
NEW_PROJECT_LINK = 0
NEW_AUDIT_OR_CASE = 0
UNREVIEWED_CONTRADICTION = 0
```

### Practical stop rule

Stop when:

1. all mandatory source families have been searched;
2. two consecutive expansion cycles produce no new T1/T2 nodes or material award records;
3. remaining leads are T0/T3 and listed in the gap queue;
4. every domain has a coverage score and blocker explanation;
5. the next round would require non-public access, paid records, FOIA, or user action.

This avoids endless searching while preventing premature narrative closure.

---

## 11. EXPLAINING WHY

Always generate and test competing explanations:

| Explanation | Core test |
|---|---|
| Corruption/improper selection | capacity + pass-through + influence chronology + waiver/objection evidence |
| Incompetence | capacity gap without stronger selection evidence |
| Oversight vacuum | inspection/CEI/monitoring lapse |
| Legitimate cost growth | scope, inflation, conditions, sector norms, amendments |
| Accounting/disbursement failure | payment records versus contract terms |
| Cancellation/change in policy | cancellation chronology versus spending |
| Corporate-successor attribution error | acquisition/divestiture/novation timeline |
| Ordinary large-prime integration | adequate capacity plus sector-normal subcontracting |

Rank by evidence, not narrative appeal. State what would falsify each hypothesis.

---

## 12. PUERTO RICO SOURCE STACK

Use as applicable:

- OCPR Consulta de Contratos
- Registro de Corporaciones
- Contralor audit reports
- transition contract reports
- PRASA/AAA documents and CERs
- PREPA/AEE and PREB records
- ACT/DTOP contracts and projects
- COR3/FEMA project and procurement records
- AAFAF, FOMB, P3A, CDBG-DR/MIT records
- municipal records
- Puerto Rico court records
- lobbying registry
- permits, environmental, property, and infrastructure records

### Bundled tooling

**`scripts/ocpr.py`**

- OCPR contract registry search
- preserves contract numbers, dates, amounts, entities, amendments
- paginate and rate-limit responsibly
- older records may be purged after retention periods; classify as `RECORD_PURGED`, not absent

**`scripts/rcp_fetch.py`**

- fetches Puerto Rico corporation records by ID
- name search may require the user's browser because of WAF restrictions
- no officer-name reverse search and no reliable affiliation endpoint; classify these structural gaps explicitly

---

## 13. FEDERAL TOOLING

Use USAspending, FPDS-derived records, SAM, agency award files, DCAA lists, and federal audit sources.

For USAspending:

- preserve prime and subaward records separately
- use valid award type codes
- avoid invalid date ranges
- distinguish registration from award history
- do not assume recipient-parent fields reflect recent corporate transactions

Use `scripts/capacity_test.py` for capacity, federal profile, and subaward diagnostics where applicable.

---

## 14. OUTPUT CONTRACT

Every full deliverable must include:

1. **Scope and public-data ceiling**
2. **Canonical corporate/entity tree**, with time-aware ownership
3. **Alias and identifier table**
4. **Award ledger**, including modifications and successor attribution
5. **Project → prime → sub → money → outcome chain**
6. **Capacity and pass-through tests**, including passes
7. **Oversight/CEI comparison**
8. **Contradiction register**
9. **Competing explanations ranked by evidence**
10. **Domain coverage matrix**
11. **Gap queue**, classified by recovery route
12. **One-sentence finding**
13. **Exact next vector**, limited to unresolved material gaps

### Completion language

Use one of:

- `PUBLIC-DATA GRAPH EXHAUSTED`
- `HIGH-COVERAGE, MATERIAL GAPS REMAIN`
- `PARTIAL — SOURCE ACCESS BLOCKED`
- `PRELIMINARY — ENTITY GRAPH NOT EXHAUSTED`

Do not say “complete” without domain scores and stop-gate evidence.

### Prose discipline

- Numbers over adjectives.
- Chronology over characterization.
- Distinguish facts, inferences, and assumptions.
- Never let the sentence outrun the source.
- Do not repeat static context; report deltas after the first full run.

---

## 15. FAILURE MODES

1. Fabricating plausible detail.
2. Searching the root name only.
3. Writing the narrative before building the graph.
4. Collapsing subsidiaries, JVs, and successors into one recipient.
5. Treating a null result as absence.
6. Treating missing subaward data as zero subcontracting.
7. Using current ownership to attribute historical performance.
8. Ignoring novations and divestitures.
9. Stopping at the base award without modifications/payments.
10. Skipping oversight-contract comparison.
11. Confusing announcements, budgets, ceilings, obligations, and payments.
12. Counting self-subcontracts as external pass-through.
13. Treating lobbying or donations as proof rather than a lead.
14. Claiming 100% despite sealed, private, purged, or classified records.
15. Repeating broad audits in later rounds instead of closing specific gaps.

---

## 16. FAST EXECUTION TEMPLATE

```text
CONTRACT_FORENSICS_V2_RUN
ROOT: [entity/project/agency]
SCOPE: [jurisdiction + dates + full family yes/no]

PHASE_1_ENTITY_GRAPH:
  seed authoritative corporate sources
  recursively expand parents/subs/predecessors/acquisitions/divestitures/JVs/successors
  generate aliases and resolve identifiers
  stop after two zero-new-material cycles

PHASE_2_PARALLEL_FANOUT:
  search federal + state/local + project/outcome + audit/litigation + influence + archives
  ingest all uploaded documents using identity/award/money/project/oversight/contradiction passes

PHASE_3_AWARD_GRAPH:
  deduplicate by identifiers
  attach modifications, payments, subawards, projects, oversight, audits, cases
  resolve owner-at-award/current-owner/novation

PHASE_4_DIAGNOSTICS:
  capacity
  pass-through
  oversight vacuum
  procurement machine
  outcome gap
  contradiction review

PHASE_5_COVERAGE:
  score every required domain
  classify every gap
  enforce stop gates

PHASE_6_OUTPUT:
  evidence-tiered graph + ledgers + ranked explanations + coverage matrix + exact gap-closing vector
```

Read `references/worked-example.md` before the first investigation and `references/interpreting-documents.md` whenever documents are supplied.

---

# V3 Persistent Memory, Anti-Retread, and Controlled Self-Adjustment

This section upgrades the graph-first method into a cumulative Puerto Rico entity-recovery engine. Chat memory is never the system of record. Durable state belongs in a repository ledger or database.

## Persistent ledger contract

Before each investigation, load or initialize these logical tables:

```text
entities
entity_aliases
entity_identifiers
entity_relationships
entity_addresses
awards
award_transactions
subawards
payments
projects
project_award_bridges
project_locations
project_outcomes
oversight_assignments
evidence
contradictions
gaps
sources
source_runs
query_history
coverage_state
entity_priority_queue
skill_improvement_proposals
skill_validation_runs
```

Recommended store: DuckDB with deterministic Parquet exports. CSV is interchange only.

Every mutable fact must preserve:

```text
valid_from
valid_to
observed_at
superseded_at
source_id
source_run_id
evidence_tier
confidence
review_status
supersedes_record_id
```

Never erase historical ownership, contractor identity, award value, or evidence. Insert new states and supersede prior records.

## Canonical keys

### Puerto Rico contract action

```text
issuing_entity_id
+ normalized_base_contract_number
+ normalized_amendment_identifier
+ contractor_entity_id
```

Contract numbers are not globally unique across Puerto Rico agencies. Never join on contract number alone.

### Federal award

```text
award_id_or_piid
+ recipient_entity_id
+ awarding_subagency_code
```

### Federal transaction

```text
federal_award_key
+ transaction_unique_id
```

### Evidence

```text
source_content_hash
+ source_locator
+ normalized_claim_hash
```

### Query history

```text
source_id
+ entity_id_or_project_id
+ normalized_query_type
+ canonical_parameters_hash
```

## Amount semantics

Do not sum every reported amount. Classify each value:

```text
BASE_VALUE
AMENDMENT_DELTA_POSITIVE
AMENDMENT_DELTA_NEGATIVE
ZERO_DOLLAR_TERM_CHANGE
CEILING
OBLIGATION
DEOBLIGATION
PAYMENT
OUTLAY
DISBURSEMENT
PROJECT_BUDGET
FEDERAL_SHARE
LOCAL_MATCH
ANNOUNCED_VALUE
UNKNOWN_AMOUNT_TYPE
```

Maintain separately:

```text
base_contract_value
amount_delta
cumulative_authorized_value
obligated_amount
paid_amount
deobligated_amount
ceiling_amount
source_reported_amount
amount_interpretation_confidence
```

## Anti-retread preflight

Before issuing any query, compare it against `query_history`.

```text
IF never executed:
    RUN
ELIF previous result failed:
    RUN using next fallback route
ELIF previous result successful AND source still fresh:
    SKIP
ELIF previous result was null AND aliases/identifiers unchanged:
    SKIP until freshness expiry
ELIF new alias, identifier, contradiction, or project bridge exists:
    RUN
ELIF source is stale:
    RUN
ELSE:
    SKIP
```

Persist:

```text
query_id
query_key
source_id
entity_id
project_id
query_type
parameters_json
parameters_hash
started_at
finished_at
status
result_count
new_record_count
updated_record_count
null_result
failure_type
fallback_route
retry_after
fresh_until
```

Allowed statuses:

```text
PLANNED
RUNNING
SUCCESS
SUCCESS_NULL
FAILED_TRANSIENT
FAILED_PERMANENT
BLOCKED_AUTH
BLOCKED_WAF
BLOCKED_NETWORK
RECORD_PURGED
REQUIRES_BROWSER
REQUIRES_FOIA
```

## Source fallback chain

Use source-specific adapters, but default to:

```text
API
→ official bulk export
→ official document download
→ official mirror
→ archived official copy
→ search-indexed official record
→ legislative or budget attachment
→ connected/manual browser retrieval
→ FOIA queue
```

A failed route updates source state. It never becomes a zero-result finding.

## Three-round maximum recovery model

### Round 1 — broad graph and source fan-out

- load prior ledger state;
- expand entities, aliases, identifiers, predecessors, successors, JVs, SPVs;
- fan out across all relevant source families;
- ingest documents;
- upsert only net-new or improved evidence.

### Round 2 — gap and contradiction closure

Run only queries triggered by:

- unresolved identity edges;
- contract-number collisions;
- recipient identifier collisions;
- missing modifications, payments, subawards, or novations;
- low-coverage, high-priority domains;
- open contradictions.

### Round 3 — inaccessible-record recovery

Queue:

- FOIA/public-records requests;
- PACER or paid dockets;
- archived websites;
- user-browser retrieval;
- agency document requests.

Do not repeat broad Round 1 searches after the ledger indicates they are fresh and complete enough.

## Persistent coverage engine

Required domains:

```text
entity_graph
aliases
identifiers
relationships
puerto_rico_contracts
contract_amendments
federal_awards
award_transactions
subawards
payments
projects
project_award_bridges
oversight
outcomes
financial_capacity
litigation
audits
lobbying
successor_mapping
geospatial_links
```

Maintain two metrics:

```text
PUBLIC_DATA_COVERAGE
RESOLVABLE_COVERAGE
```

`PUBLIC_DATA_COVERAGE` retains inaccessible records in the denominator. `RESOLVABLE_COVERAGE` excludes records proved sealed, classified, private, destroyed, or purged. Report both with denominator notes and domain confidence.

Each execution reports only:

```text
new records
updated records
new contradictions
resolved contradictions
coverage delta
priority-rank delta
new blockers
next action
```

## Dynamic priority queue

Recalculate entity priority after every run.

```text
priority_score =
0.16 financial_materiality
+ 0.14 infrastructure_criticality
+ 0.10 federal_state_overlap
+ 0.08 amendment_density
+ 0.08 ownership_complexity
+ 0.08 successor_complexity
+ 0.08 subcontract_opacity
+ 0.07 source_gap_severity
+ 0.06 network_centrality
+ 0.05 litigation_signal
+ 0.04 lobbying_signal
+ 0.03 recency
+ 0.03 staleness
```

Store:

```text
entity_id
current_rank
previous_rank
rank_delta
priority_score
coverage_deficit
last_researched_at
staleness_score
priority_reasons
highest_value_next_action
estimated_recovery_gain
```

### Seed priority clusters

Use these as bootstrap entries only; dynamic scoring controls later order.

1. Jacobs / CH2M / Amentum lineage
2. AECOM
3. Arcadis / Arcadis Caribe
4. LUMA Energy
5. Genera PR
6. AES Puerto Rico
7. New Fortress Energy
8. Fluor
9. Tetra Tech
10. Stantec
11. HDR
12. WSP
13. Black & Veatch
14. CDM Smith
15. Parsons
16. Sargent & Lundy
17. Burns & McDonnell
18. Gannett Fleming
19. HNTB
20. Kimley-Horn
21. TYLin
22. Michael Baker International
23. Brown and Caldwell
24. Hazen and Sawyer
25. GHD
26. TRC Companies
27. APTIM
28. Weston Solutions
29. EA Engineering
30. Grant Thornton Puerto Rico
31. Deloitte Puerto Rico
32. Ernst & Young Puerto Rico
33. KPMG Puerto Rico
34. Guidehouse
35. ICF
36. Ankura
37. Alvarez & Marsal
38. Redondo Construction
39. Ferrovial Construcción Puerto Rico
40. Dragados
41. Tutor Perini
42. Dick Corporation / Dick Pacific lineage
43. ECC
44. Webuild
45. LPC & D / Las Piedras Construction lineage
46. Aníbal Díaz Construction
47. ECOVAL / Soria cluster
48. TAM Industries / TAMCOR / Trujillo Alto Metal cluster
49. Cobra Acquisitions / Mammoth Energy lineage
50. MasTec
51. Quanta Services
52. PowerSecure
53. Waste-management and ecological contractor clusters
54. Autopistas Metropolitanas de Puerto Rico
55. Metropistas
56. Global Ports Holdings / San Juan Cruise Port
57. Crowley
58. EcoEléctrica
59. Puma Energy Puerto Rico
60. Naturgy
61. PRASA consulting-engineer cluster
62. PREPA legacy engineering and generation contractors
63. COR3 program-management contractors
64. FEMA PA technical-assistance contractors
65. USACE Puerto Rico engineering contractors
66. NAVFAC Vieques/Culebra remediation contractors
67. CDBG-DR/MIT management contractors
68. Puerto Rico P3 concessionaires
69. Puerto Rico municipal waste contractors
70. Puerto Rico telecom infrastructure contractors

## Project-to-contract bridge

Support both directions:

```text
ENTITY → CONTRACT → PROJECT
PROJECT → EVERY CONTRACTOR → EVERY FUNDING SOURCE
```

Required fields:

```text
project_id
project_name
pw_number
disaster_number
facility_id
municipality
local_contract_action_key
federal_award_key
prime_entity_id
subaward_id
role
bridge_method
bridge_confidence
source_id
```

## Controlled self-adjustment

The skill may diagnose and propose improvements. It must never silently promote its own rewrite.

### Trigger classes

```text
FALSE_ENTITY_MERGE
FALSE_CONTRACT_JOIN
IDENTIFIER_COLLISION
SOURCE_FORMAT_CHANGE
PARSER_MISS
MISSING_SCHEMA_FIELD
REPEATED_QUERY
UNHANDLED_FAILURE
COVERAGE_OVERSTATEMENT
COVERAGE_UNDERSTATEMENT
SUCCESSOR_ATTRIBUTION_ERROR
AMOUNT_SEMANTICS_ERROR
```

### Proposal record

```text
proposal_id
trigger_run_id
trigger_entity_id
problem_type
problem
evidence_ids
current_behavior
proposed_generalized_change
affected_skill_sections
affected_source_adapters
required_tests
expected_coverage_gain
expected_requery_reduction
regression_risk
status
```

Allowed statuses:

```text
PROPOSED
TRIAGED
CANDIDATE_GENERATED
VALIDATING
VALIDATION_FAILED
READY_FOR_REVIEW
APPROVED
REJECTED
PROMOTED
```

### Self-adjustment review prompt

```text
SELF_ADJUSTMENT_REVIEW:

Review the completed forensic run against the current skill behavior.

Identify:
1. source failures not already handled;
2. missing schemas or fields;
3. false joins or duplicate patterns;
4. repeated queries that should have been skipped;
5. contradictions the current workflow failed to detect;
6. source-specific formats that require an adapter;
7. coverage domains that were overstated or understated.

For each issue:
- describe the failure;
- cite the triggering run evidence;
- propose the smallest generalized skill change;
- identify affected sections and tests;
- estimate coverage gain, requery reduction, and regression risk.

Do not modify the promoted skill directly.
Create a candidate patch, changelog, proposal manifest, and validation requirements.
Promote only after all mandatory validation cases pass and the user explicitly approves.
```

## Mandatory regression cases

Validate every candidate against:

- Jacobs / CH2M / Amentum
- AES Puerto Rico
- ECOVAL / Soria
- Dick Corporation / Dick Pacific
- Grant Thornton Puerto Rico

Required gates:

```text
NO schema regression
NO provenance loss
NO increase in false entity merges
NO increase in false contract joins
NO direct self-promotion
NO unsupported completeness claims
NO deletion of source adapters
NO uncontrolled broad reruns
```

At least one measurable improvement is required:

```text
more verified records
better entity resolution
fewer duplicates
fewer false joins
higher coverage
lower query repetition
lower runtime or token cost
```

## State and failure reporting

Maintain or emit equivalents of:

```text
current_status.json
current_blockers.md
next_actions.md
forensics_coverage_state.json
entity_priority_queue.json
skill_improvement_queue.json
skill_validation_results.json
```

Use delta-only reports. On execution failure, stop and report:

```text
FAILURE_PACKET:
command:
exit_code:
last_40_lines:
files_recently_changed:
suspected_area:
```

## V3 output contract

Every full entity investigation must deliver:

1. ledger preflight result;
2. skipped-versus-rerun query summary;
3. canonical entity graph;
4. aliases and identifiers;
5. local and federal award ledger;
6. modifications, payments, subawards, and novations;
7. project and geospatial bridges;
8. capacity, pass-through, oversight, and outcome tests;
9. contradictions;
10. coverage and confidence by domain;
11. priority-rank update;
12. gap and FOIA queue;
13. skill-improvement proposals, if triggered;
14. exact next vector limited to unresolved material gaps.

Completion language remains restricted to:

```text
PUBLIC-DATA GRAPH EXHAUSTED
HIGH-COVERAGE, MATERIAL GAPS REMAIN
PARTIAL — SOURCE ACCESS BLOCKED
PRELIMINARY — ENTITY GRAPH NOT EXHAUSTED
```

---

## V3 EXECUTABLE PERSISTENT-MEMORY SCAFFOLD

When this package is available locally, use `engine.core.ForensicsLedger` as the persistent source of truth.

Required startup sequence:

```text
MIGRATE LEDGER
→ READ query_history + coverage_state + entity_priority_queue
→ PREFLIGHT EACH QUERY
→ RUN ONLY NEW, STALE, FAILED, CONTRADICTED, OR ALIAS-INVALIDATED QUERIES
→ UPSERT WITH PROVENANCE
→ EXPORT DETERMINISTIC PARQUET SNAPSHOTS
→ UPDATE COVERAGE + PRIORITY + GAP QUEUES
→ PROPOSE SKILL CHANGES, NEVER SELF-PROMOTE
```

Commands:

```bash
python -m engine.cli init --root .
python -m engine.cli status --root .
python -m engine.cli export --root .
pytest -q
```

The promoted `SKILL.md` must never be overwritten by automated candidate generation. Candidates belong under `candidates/<version>/` and require explicit user approval.

---

## 17. PERSISTENT SOURCE ADAPTER EXECUTION

Version 3.1 adds a uniform source-adapter layer in `engine/adapters.py`.

Every adapter must:

1. call ledger preflight before retrieval;
2. write `sources`, `source_runs`, and `query_history` state;
3. distinguish `SUCCESS_NULL` from retrieval failure;
4. persist a failure packet and next fallback route;
5. return normalized records and evidence without directly promoting uncertain facts;
6. use the canonical Jacobs/entity alias registry supplied by the active cluster;
7. remain idempotent when the same fresh query is repeated.

### Adapter modes

- **Live HTTP/API:** OCPR, USAspending, SAM, Puerto Rico corporations, Contralor, PRASA, PREPA/PREB, ACT/DTOP, COR3/FEMA, Puerto Rico lobbying, federal LDA, and courts.
- **Official bulk/local document:** transition reports, DCAA contractor listings, PRASA project inventories and CERs, lobbying snapshots, and subcontracting directories.
- **Manual snapshot:** user-browser or externally acquired records inserted with provenance when direct runtime retrieval is unavailable.

### Fallback state

```text
API
→ OFFICIAL_BULK_EXPORT
→ OFFICIAL_DOWNLOAD
→ OFFICIAL_MIRROR
→ ARCHIVE
→ SEARCH_INDEX
→ LEGISLATIVE_ATTACHMENT
→ MANUAL_BROWSER
→ FOIA
```

A network, DNS, authentication, WAF, or parser failure must be recorded in the ledger. It is never equivalent to a zero-result source search.

### First seeded cluster

The initial persistent cluster is `JACOBS_CH2M_AMENTUM`. It includes search aliases for Jacobs, CH2M Hill, Sverdrup, Jacobs Technology, Jacobs Facilities, Halcrow, Sinclair Knight Merz, LeighFisher, KlingStubbins, the two Puerto Rico Jacobs branches, and Amentum. Seed relationships are provisional until supported by authoritative evidence.

### Current execution command

```bash
PYTHONPATH=. python scripts_connect.py
PYTHONPATH=. python -m engine.cli export --root .
```

The run writes:

- `reports/source_adapter_run.json`
- `reports/current_status.json`
- `data/contract_forensics.duckdb`
- deterministic `data/parquet/*.parquet` snapshots

Manual skill promotion remains mandatory.


## Persistent Memory and Source Adapters

Before any live query, read `query_history`, `source_runs`, and `coverage_state`. Use this fallback order: direct API, official bulk export, official download, official mirror, archived official copy, search-indexed official record, legislative attachment, manual browser, FOIA/file-drop queue. Search-indexed official records may seed awards and identifiers only when the official page exposes the exact fields. Persist blocked routes; never convert them into null findings.

For Puerto Rico work, award/project recovery must preserve agency-scoped contract keys, recipient UEIs, parent-at-award identities, project bridges, and unresolved novation status. Recalculate coverage and priority after every delta ingestion.
