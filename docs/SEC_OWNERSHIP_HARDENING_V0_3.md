# SEC Ownership Hardening v0.3

## Scope

This vector freezes the uploaded `MONEYSWEEP_PR_SEC_UPLOAD_AUDIT_v0_1` findings as regression fixtures, adds a stable-ID-gated BPOP/OFG/EVTC SEC issuer re-materialization, separates Form 13F file numbers from CIKs in the legacy municipal/debt holdings discovery output, and adds a fail-closed SEC Form 13F eight-quarter certification path.

It does **not** promote ownership data into Deep Dive. Promotion remains downstream of both code CI and authoritative BPOP data certification.

## Frozen baseline findings

- BPOP binds to CIK `0000763901`.
- OFG binds to CIK `0001030469`; the legacy `OFG -> 0001016178 -> CARVER BANCORP INC` manifestation is rejected/superseded for identity use.
- EVTC binds to CIK `0001559865`; `EVTC != EVRI` is a permanent negative regression.
- Legacy `pr_sec_holdings.csv` is municipal/debt discovery, not a corporate-equity ownership denominator.
- Values such as `028-14486` are Form 13F file-number manifestations and must not occupy `filer_cik`.
- The uploaded financial snapshot had no populated historical `shares_outstanding` values and therefore cannot support issuer-ownership percentages.

The exact uploaded row counts and SHA-256 values are frozen in `tests/fixtures/capital_control/sec_upload_baseline_v0_1.json`.

## Identity repair

`scripts/download_sec_equity_v2.py` is deliberately bounded to BPOP, OFG, and EVTC. It requires each ticker to bind to its expected CIK in SEC `company_tickers.json`, then independently requires the SEC submissions document to bind back to the same CIK. Names are preserved as source strings but never establish identity.

The legacy `sec_edgar` producer is not overwritten in this vector because it has broader historical scope. Its old outputs remain source manifestations; they are not eligible to drive the ownership certification. The new bounded source family must pass first before any broader replacement is attempted.

No synthetic financial fallback is permitted. Raw SEC ticker-map, submissions, and companyfacts bytes are frozen locally and reused unless `--refresh` is explicit.

## Historical issuer-share denominator

The v2 equity producer materializes every 10-K/10-Q `shares`-unit observation found under:

- `dei:EntityCommonStockSharesOutstanding`; and
- `us-gaap:CommonStockSharesOutstanding`.

Each denominator candidate preserves `as_of_date`, `filed_date`, form, fiscal year/period, frame, accession number, concept, and value. The BPOP certifier uses only exact quarter-end candidates. Zero candidates or multiple distinct values remain `UNRESOLVED`; nearest-date substitution is prohibited.

## Legacy holdings identifier repair

`scripts/rematerialize_sec_holdings_discovery_v2.py` leaves `pr_sec_holdings.csv` unchanged and writes a new manifestation. It preserves `filer_cik_raw`, puts recognized `028-...` values in `form13f_file_number`, preserves numeric CIKs separately, and marks every migrated row `PUERTO_RICO_MUNICIPAL_DEBT_DISCOVERY` with `corporate_equity_ownership_eligible=false`.

## SEC 13F authoritative path

`scripts/acquire_sec13f_bpop_golden.py` freezes exactly eight official bulk ZIPs spanning BPOP 2024Q2 through 2026Q1. Every archive receives an outer SHA-256 and every member receives `PATH + UNCOMPRESSED_SIZE + SHA256`. Required `SUBMISSION`, `COVERPAGE`, `SUMMARYPAGE`, and `INFOTABLE` members must exist.

The GitHub Actions wrapper ZIP is transport-only and may be recompressed. Certification pins the freeze-manifest and SEC identity/denominator payload hashes, then compares every inner SEC archive's path, byte size, SHA-256, and complete member `PATH + UNCOMPRESSED_SIZE + SHA256` set. Wrapper-byte difference alone cannot change source identity.

`moneysweep.capital_control.sec13f` parses the frozen archives with:

- `(ACCESSION_NUMBER, INFOTABLE_SK)` duplicate rejection;
- stable filer CIK holder IDs;
- exact target CUSIP matching;
- source row/member/outer hash provenance;
- additive-amendment vs restatement distinction;
- filing-level restatement lineage keyed by stable CIK, report period, and SEC accession;
- provider `% Total Assets` kept separate from SEC reportable-portfolio weight.

## Certification gates

`scripts/certify_bpop_sec13f_8q.py` requires all of the following:

1. exact eight archive names and hashes;
2. exact archive/member identity against the pinned freeze manifest;
3. row conservation and unique source records;
4. every retained restatement filing is classified, and all prior retained target-row
   filings for that CIK/report period are superseded as a set without synthesizing
   row-to-row identity;
5. all eight BPOP report periods present;
6. one unique exact-date BPOP shares-outstanding denominator per period;
7. stable CUSIP issuer bindings;
8. stable filer-CIK holder IDs;
9. all eligible non-option BPOP share rows receive a computed issuer percentage;
10. at least one OFG and one EVTC target row for parser regression coverage;
11. supersession arithmetic closes;
12. Morningstar/provider equivalence remains `OPEN` rather than being silently promoted.

The official filing archives are filing-date windows and can contain amendments for older `PERIODOFREPORT` values. Those rows remain preserved whole in `sec13f_pr_golden_excluded_periods.csv` with an explicit exclusion reason; they do not expand the eight-period certification denominator. The partition must satisfy `discovered = in-scope + excluded`.

The [official SEC Form 13F instructions](https://www.sec.gov/files/form13f.pdf) require a restatement to restate the report in its entirety;
an additive amendment instead contains only new holdings. Within the retained target-CUSIP
corpus, all prior filings for the same stable filer CIK and report period are superseded as
a set. A
restatement with no prior retained target rows is classified
`NO_PRIOR_TARGET_ROWS_RETAINED`; that bounded state does not claim that no prior SEC filing
exists. Every source row remains materialized, and active plus superseded arithmetic must
equal the in-scope source count.

Only a `PASS` certification makes the dataset eligible for a **separate** Deep Dive promotion vector.

## Current certification state

Workflow run `32946731464` froze the authoritative SEC identity inputs and all eight official archives. Downstream runs reuse that immutable snapshot rather than redownloading mutable sources. A local replay of those exact payloads passed all certification gates on 2026-08-27 with `11,866 discovered = 11,400 in scope + 466 excluded` and `11,400 in scope = 10,743 active + 657 superseded`. Hosted exact-head certification remains required; code CI success alone does not promote the ownership data or establish provider equivalence.
