# SEC 13F Capital/Control v0.2

## Scope

This vector extends `CAPITAL_CONTROL_GRAPH_V0_1` with a bounded, auditable SEC Form 13F acquisition and materialization path for MoneySweep. It does not claim that Form 13F is a complete shareholder register, that a reporting manager is automatically a beneficial owner, or that a provider metric is equivalent to an SEC-derived metric without a proven common denominator.

## Authoritative source

- Authority: U.S. Securities and Exchange Commission.
- Index: `https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets`.
- Source family: `REGULATORY_HOLDINGS`.
- Canonical source rows: as-filed flattened Form 13F bulk data.

The producer requires a SEC-compliant `User-Agent`. Network acquisition is isolated from canonicalization: first freeze the ZIP, then build from the frozen path.

## Puerto Rico golden cases

`registries/capital_control_golden_cases.json` defines the regression set:

- `BPOP` / Popular, Inc. / CIK `0000763901` / CUSIP `733174700`: primary eight-quarter golden case.
- `EVTC` / EVERTEC, Inc. / CIK `0001559865` / CUSIP `30040P103`: cross-sector identity regression; `EVTC` must never be collapsed with `EVRI` by name-only logic.
- `OFG` / OFG Bancorp / CIK `0001030469` / CUSIP `67103X102`: RAW-versus-NORMALIZED regression fixture.

Issuer identity is bound from the explicit CUSIP-to-issuer registry. CUSIP discovery alone never creates an issuer identity outside that registry.

## BPOP eight-quarter contract

The v0.2 certification window is fixed to report periods:

- 2024-06-30
- 2024-09-30
- 2024-12-31
- 2025-03-31
- 2025-06-30
- 2025-09-30
- 2025-12-31
- 2026-03-31

and to the eight SEC publication-window ZIP basenames listed in the golden-case registry. Supplying fewer or additional archives makes this exact bounded certification OPEN rather than silently widening the claim.

## Byte and archive invariants

`download_sec_13f_bulk.py`:

1. discovers archive links from the SEC index;
2. validates that every required basename is present on the authoritative index;
3. downloads to a `.part` file;
4. computes SHA-256 while downloading;
5. verifies ZIP structure before atomic replacement;
6. preserves an existing frozen snapshot unless `--refresh` is explicit;
7. writes a freeze manifest.

`Sec13FBulkAdapter` additionally records:

- outer byte size and SHA-256;
- every archive member path;
- every member uncompressed size and SHA-256;
- required table schemas;
- source row counts;
- retained target-CUSIP count;
- canonical schema fingerprint.

Different hashes prove byte difference only. Regenerated outputs cannot prove prior byte identity.

## Source schema and identity

The canonical join keys are source-defined:

- submission-level tables: `ACCESSION_NUMBER`;
- information table: `ACCESSION_NUMBER + INFOTABLE_SK`.

The reporting manager legal-holder node uses the SEC filer CIK as the stable identity spine. Manager names are retained as raw source manifestations. Branding, normalized names, counts, proximity, or deterministic similarity do not collapse managers.

The BPOP Vanguard regression explicitly requires distinct reporting CIKs to remain distinct legal-holder identities. Investor-family and ultimate-parent rollups require their own authoritative bindings.

## Amendment semantics

MoneySweep distinguishes:

- `ORIGINAL`;
- `AMENDED_ADDITION`: additive amendment; does not automatically supersede a prior row;
- `AMENDED_RESTATEMENT`: a restatement whose prior structural observation has been uniquely proven;
- `UNKNOWN`: amendment semantics or target unresolved;
- `SUPERSEDED`: derived state applied to the displaced observation while preserving that observation.

A restatement is promoted to `AMENDED_RESTATEMENT` only when exactly one prior observation survives the holder, issuer, security, position-class, period, put/call, discretion, other-manager, and prior-report-date gate. Zero or tied candidates remain unresolved and block certification.

## Metric equivalence boundary

MoneySweep keeps source/provider metric taxonomies separate.

`percent_13f_reportable_value` is computed only as the information-table position `VALUE` divided by the filing's SEC `TABLEVALUETOTAL`, multiplied by 100. It is explicitly not named `% Total Assets`.

`provider_percent_total_assets` remains null unless supplied by a provider source whose denominator definition is preserved. `provider_metric_equivalence` remains `OPEN` unless authoritative semantic evidence proves that the provider denominator and the MoneySweep denominator are identical for the same entity and date.

Similarly, `percent_issuer` remains null unless a dated, source-bound shares-outstanding denominator is separately acquired and validated. A current shares-outstanding value cannot be applied retrospectively to a historical holding.

## Deep Dive boundary

The batch producer writes:

- `data/staging/processed/capital_control/sec13f_holdings.csv`;
- `data/staging/processed/capital_control/sec13f_investors.csv`;
- source manifests, archive audits, build receipt, and BPOP certification under `data/manifests/capital_control/`.

The entity-mode adapter `sec_13f_capital_control` exposes only the already-materialized, already-gated holdings table and matches by exact CUSIP. Interactive Deep Dive queries never download or recanonicalize live SEC data and therefore cannot bypass provenance, amendment, or certification gates.

## Certification gates

The BPOP bounded claim may be `PASS` only when all of these are true:

- the exact eight required frozen archive basenames are supplied;
- all eight required BPOP report periods are present;
- source-record identities are unique;
- BPOP issuer identity is authoritatively bound;
- required holder/security fields are non-null;
- report date is not earlier than as-of date;
- restatement residue is zero;
- source and retained counts close;
- active plus superseded rows equals the preserved row count.

Script success is not certification. An unresolved restatement, missing archive, missing period, duplicate, null required field, identity gap, or arithmetic mismatch fails closed.

## What this does not certify

Even a BPOP `PASS` does not certify:

- every economic or beneficial shareholder of Popular, Inc.;
- non-13F assets of a reporting manager;
- Morningstar or another provider's proprietary asset denominator;
- current Q2 2026 ownership until the selected authoritative source snapshot is defined and frozen;
- a GUI workflow.

Those scopes require separate source denominators and certification vectors.
