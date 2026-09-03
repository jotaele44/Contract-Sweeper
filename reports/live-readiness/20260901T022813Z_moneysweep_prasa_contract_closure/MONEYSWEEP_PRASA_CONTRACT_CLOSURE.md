# MoneySweep PRASA Contract Closure Receipt

- Run ID: `20260901T022813Z_moneysweep_prasa_contract_closure`
- Result: `PROVISIONAL_LIVE_READINESS_PRASA_CLOSED_HUD_DRGR_PRESERVED`
- Package: `pkg_9642c2a411343e9c0c20891ac84f4f08`
- PRASA contract rows: `642`
- PRASA vendor master rows: `309`
- Source-drop arithmetic: `19=15 FOUND + 4 PARTIAL/UNRESOLVED + 0 missing`
- Materialization: `12/16` required sources fully materialized; `19` total sources fully materialized; `2` partial.

## Closed

- `prasa`: closed from the ACT agency 163 PRASA 2024 transition `Contratos Vigentes` PDF, parsed into `data/staging/processed/pr_prasa_contracts.csv` and `data/staging/processed/prasa_contracts_master.csv`.

## Preserved Blockers

- `hud_drgr_authorized`: remains `PARTIAL_UNRESOLVED`; no non-empty authorized DRGR activities/projects export was found. Public CDBG/HCV or zero-row DRGR-shaped files are not promoted to authorized DRGR.

## Gates

- Focused MoneySweep tests: `PASS` (`36 passed`)
- TheHub package validation: `PASS` (`VALID package`)
- Legacy MoneySweep `validate_export.py`: `FAIL_LEGACY_CONTRACT`, preserved because it expects an old five-stream package shape.

## Search Limitation

- `LUMEN_UNAVAILABLE_OR_UNHEALTHY`; bounded local inspection was used.
