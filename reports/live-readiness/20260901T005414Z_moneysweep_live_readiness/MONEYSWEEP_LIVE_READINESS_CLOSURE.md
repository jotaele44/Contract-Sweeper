# MoneySweep Live-Readiness Closure Receipt

- Run: `20260901T005414Z_moneysweep_live_readiness`
- Result: `PROVISIONAL_LIVE_READINESS_IMPROVED`
- Scope: found source-drop and materialization blockers only
- Lumen: `LUMEN_UNAVAILABLE_OR_UNHEALTHY`; bounded local inspection used
- Source-drop arithmetic: `15=12 FOUND + 3 PARTIAL/UNRESOLVED + 0 missing`
- Materialization: `{'fully_materialized': 17, 'not_materialized': 142, 'partially_materialized': 3}`
- Certification: `{'certified_complete': 1, 'provisional': 16, 'uncertified': 145}`
- Federation export package: `pkg_9208fb0b7dc71cd0b24a44ac5a126e46`

## Closed In This Pass

| Source | Rows | State |
| --- | ---: | --- |
| cor3 | 1481 | FOUND_STAGED_INGESTED_PROVISIONAL |
| pr_cabilderos | 2668 | FOUND_STAGED_INGESTED_PROVISIONAL |
| oficina_contralor | 85 | FOUND_STAGED_INGESTED_PROVISIONAL |
| oce_socrata_live / contralor_electoral | 6474 | FOUND_STAGED_INGESTED_PROVISIONAL_PARTIAL_AMOUNTS_ALLOWED |
| donaciones_pr | 9156 | FOUND_STAGED_INGESTED_CERTIFIED_COMPLETE_BY_LOCAL_CONTRACT |

## Preserved Blockers

| Source | State | Reason |
| --- | --- | --- |
| prasa | PARTIAL | PRASA CER/asset evidence exists, but the contract master has 0 rows. |
| hud_drgr_authorized | PARTIAL_UNRESOLVED | DRGR-shaped parquet exists, but has 0 rows; authorized export is not proven. |

## Gates

- Focused tests with `--no-cov`: PASS, 40 tests.
- OCE default focused test invocation: FAIL_COVERAGE_THRESHOLD after tests passed; preserved as negative evidence.
- MoneySweep federation export test mode: PASS.
