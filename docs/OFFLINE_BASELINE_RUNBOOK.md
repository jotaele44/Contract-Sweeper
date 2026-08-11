# MoneySweep offline provisional baseline

The `offline-baseline` profile creates a deterministic, local-only diagnostic snapshot. It is not a production promotion mechanism and never certifies source-universe completeness.

## Input dropzone

Place operator files under `data/manual/offline_baseline/`. Recognized files include:

- `cor3_official_projects_export.xlsx`
- `entity_master.csv` or `entity_master(2).csv`
- `pr_entity_profiles.csv`
- `pr_nonprofits.csv`
- `pr_fdic_institutions.csv`
- `pr_fdic_financials.csv`
- `Registro_de_cabilderos_Abril_18_2026 2.pdf`

Raw operator files remain local and must not be committed.

## Command

```bash
python3 run_all.py \
  --profile offline-baseline \
  --offline-strict-inputs \
  --offline-generated-at 2026-07-31T20:57:00-04:00
```

Use `--offline-git-sha <sha>` when the checkout identity must be supplied explicitly. Outputs are written below `reports/offline_baseline/offline-baseline-<digest>/` and are immutable for the same code/input digest.

## Safety properties

- Network access is denied in-process.
- Credential-bearing environment variables are stripped from child environments.
- Only local dropzone files are staged.
- The legacy full pipeline cannot be entered from this profile.
- Required-source credit is held fail-closed.
- Cabilderos PDF extraction is provisional and receives no canonical source credit.
- Every input and output is SHA-256 addressed.
- Output paths do not disclose operator workstation paths.
- Status remains `NON_PRODUCTION_DIAGNOSTIC`.

## Produced evidence

- `input_manifest.json`
- `preexisting_outputs_manifest.json`
- `entity_product_comparison.json`
- `pr_cabilderos_provisional.csv`
- `source_coverage_matrix.json` and `.csv`
- `blocked_source_ledger.json`
- `output_manifest.json`
- `run_receipt.json`
- `SHA256SUMS.txt`

A provisional baseline can be compared against a later receipt-backed run, but it must not be relabeled as a certified canon until all required-source, freshness, provenance, and universe-completeness gates pass.
