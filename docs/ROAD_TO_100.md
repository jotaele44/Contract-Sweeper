# MoneySweep — Road to 100

**Reconciled:** 2026-07-30  
**PR:** #448, draft and unmerged  
**Current base incorporated:** `bd337fb092eb639cdb24b490bc90a8b07e9e51c4`  
**Last certified v0.8 head:** `b1f088c98c8175298b856a5df8215c77fa933877`  
**Production status:** `NON_PRODUCTION_DIAGNOSTIC`

## Certified baseline

| Control | Result |
|---|---:|
| Registry sources | 151 |
| Automatable / structurally ready | 104 / 104 |
| Queued or excluded | 47 |
| Fully / partially / not materialized | 67 / 11 / 73 |
| Required fully materialized | 10 / 14 |
| Registry source-ID digest | `7830358c254767bc9db34ae5230b41f815ffaea9aa0c3abe4dfdebfe36b2f2d0` |
| Physical processed rows | 1,183,565 |
| Registry-declared rows | 849,898 |
| Adjudicated derived rows | 212,930 |
| Pipeline intermediates | 120,737 |
| Unadjudicated orphan rows | 0 |
| Derived rows with unresolved lineage | 104,280 |
| Live universe probe | Not run |

The last v0.8 head passed **16/16 triggered workflows**, including Skills Validation. GitHub checks remain authoritative for later remediation commits.

## Residual repairs completed before source ingestion

### Entity comparison

`entity_product_comparison_v2` now:

- rejects duplicate headers, extra fields, missing fields, and empty products;
- selects the first populated recognized key rather than the first matching header;
- reports no-shared-column projection as not computable instead of 100% overlap;
- distinguishes byte identity, semantic duplication, high key overlap, and distinct products;
- exits nonzero for invalid or empty products even when `--allow-missing` is supplied.

The real comparison remains pending because the certification bundle did not include the two operator CSVs.

### HUD DRGR producer contract

`scripts/ingest_hud_drgr_exports.py` now writes the registry-declared staging products:

- `data/staging/processed/hud_drgr_activities.csv`
- `data/staging/processed/hud_drgr_projects.csv`

It also preserves normalized analytical products for activities, projects, drawdowns, and appropriations. Empty manual drops remain fail-closed with `manual_required` and zero credit.

### Provenance metadata

A validated source-override layer records metadata corrections without changing source IDs or the required-source denominator:

- COR3 keeps `download_cor3.py` as the separately gated registry producer and records `ingest_cor3.py` as the authorized offline workbook path.
- The cabilderos source records the Puerto Rico Department of Justice as official custodian and uses the Justice registry surface.

### Derived-output lineage

Five of six derived producers are confirmed. `data/staging/processed/entity_master.csv` remains a derived, non-credit output with unresolved staging lineage because the candidate `scripts/build_entity_master.py` declares `data/reference/entity_master.csv`.

## Required-source queue

| Source | Evidence status | Required next action |
|---|---|---|
| `cor3` | Export surface verified; workbook bytes absent | Supply official workbooks and run the offline ingest, or separately authorize a verified live producer |
| `hud_drgr_authorized` | Authorized export absent | Drop exports under `data/manual/hud_drgr/` and run the producer |
| `pr_cabilderos` | Official registry verified; complete export absent | Supply a current machine-readable Justice export |
| `prasa` | Official contract-export route verified; filtered export absent | Supply the PRASA export and run the dropzone ingest |

## Gates remaining before production consideration

1. Materialize and validate the four required sources.
2. Execute `entity_product_comparison_v2` against the operator corpus.
3. Resolve `entity_master.csv` staging lineage.
4. Re-run the 151-source audit and preserve digest/status parity.
5. Certify source freshness and external-universe completeness.
6. Complete PR2.5/PR2.6 reconciliation before PR3 deduplication.
7. Validate production export and downstream federation consumers.
8. Keep promotion guards closed until every blocker is cleared.

## Preservation

This roadmap does not authorize merge, auto-merge, live fetch, credential automation, data promotion, force push, or history rewrite.
