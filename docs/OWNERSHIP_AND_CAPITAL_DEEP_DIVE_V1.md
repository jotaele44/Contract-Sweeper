# OWNERSHIP_AND_CAPITAL Deep Dive v1

## Certification chain

This promotion is downstream of the independently certified SEC ownership hardening vector.
It does not re-run or broaden the source acquisition claim.

Immutable audit endpoints:

- pre-repair audit snapshot: `313def60cfdde57804733ce96ff1f5c64819b4a4`
- certified SEC ownership source head: `ac69290ba4370a31472fa4b2884abfb182241174`
- exact certified head merged to `main` as: `b35ce8888d755c6be88c6715a70592541af792b0`

The Deep Dive branch is based on that merge commit. No mutable SEC evidence is redownloaded by the user-facing API or dashboard.

## Promoted scope

The only issuer currently eligible for an ownership Deep Dive is:

- issuer: Popular, Inc. / BPOP
- issuer CIK: `0000763901`
- security CUSIP: `733174700`
- bounded periods: 2024Q2 through 2026Q1, exactly eight quarter-end periods
- controlling certification: `BPOP_SEC13F_8Q_v1`, state `PASS`

OFG (`0001030469`, CUSIP `67103X102`) and EVTC (`0001559865`, CUSIP `30040P103`) are retained as real-source parser/identity regressions. Their presence in the certified corpus is **not** issuer-level Deep Dive certification and the API rejects attempts to inherit BPOP certification.

## Read-only promotion boundary

`moneysweep.capital_control.deep_dive` consumes an already-certified receipt and the already-materialized holdings. It fails closed unless:

1. certification `state` is `PASS`;
2. `bounded_claim_only` is true;
3. exactly eight BPOP periods are present in both receipt and materialization;
4. OFG and EVTC real-source regression counts are non-zero;
5. every observation remains adjudicated ACTIVE or SUPERSEDED;
6. observation IDs remain unique;
7. provider-equivalence state remains `OPEN`.

The builder returns whole source observations. It does not sum holdings across reporting managers, brand families, options, other-manager allocations, or amendment manifestations. Such aggregation can synthesize a position that never existed as one source row.

## Amendment lineage

SEC Form 13F restatement semantics remain filing-level. A filing restatement may supersede the prior retained filing set for the same stable filer CIK and report period. Row-level `supersedes` identity is not inferred from count equality, security similarity, order, or temporal proximity.

Original, additive, restated, superseded, and out-of-period manifestations remain preserved in their respective audit/materialization artifacts.

## Denominators

Issuer-share percentages are carried only where the upstream certification bound an exact historical issuer-share denominator to the same period. The Deep Dive does not compute a substitute from:

- current shares outstanding;
- nearest available date;
- an average/max/first observation;
- a provider's asset denominator.

## Provider equivalence

Morningstar/provider `% Total Assets` remains semantically independent from SEC-derived `percent_13f_reportable_value`.

Current state:

`morningstar_percent_total_assets_equivalence = OPEN`

The API and builder fail closed if that field is unexpectedly promoted. A future equivalence claim requires a separate authoritative semantic-binding vector and its own certification.

## API

Read-only endpoints:

- `GET /deep-dive/ownership/status`
- `GET /deep-dive/ownership/BPOP`

`OFG` and `EVTC` return a bounded-scope conflict rather than a BPOP-derived response.

If the frozen certification/materialization artifacts are not mounted, the status endpoint remains available but BPOP data returns a service-unavailable failure. No fixture or provider data is substituted.

## GUI

The dashboard exposes a terminal-free **Ownership** tab. BPOP is enabled; OFG and EVTC appear disabled as regression-only controls so the certification boundary is visible rather than hidden.

The UI labels provider equivalence as `OPEN` and presents latest whole-source observations with stable holder IDs, dates, shares, independently computed issuer percentage where available, SEC 13F reportable-portfolio percentage, amendment state, and accession number.

## Skill

`skills/moneysweep-ownership-capital/` carries the same operational invariants into the MoneySweep Skill Bank. The skill is read-only by default and must not broaden the certified issuer/period scope.

## Independent promotion certification

This Deep Dive implementation is a new downstream scope. The upstream BPOP data certification does not automatically certify the new API, GUI, or skill.

Promotion reaches `PASS` only after the Deep Dive branch itself passes:

- Python tests and type/lint gates;
- Skill packet validation and activation coverage;
- GUI capability parity;
- dashboard lint/build/e2e checks;
- negative regression gates for non-PASS certification, provider-equivalence promotion, non-BPOP issuer requests, missing period coverage, and absent OFG/EVTC regressions.

Until those downstream gates pass, the correct state is `PROVISIONAL` even though the underlying BPOP data scope is already certified.
