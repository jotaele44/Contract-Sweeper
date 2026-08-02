# MoneySweep Wave 0 — Residual Risk Report

**Reconciled:** 2026-07-30  
**Boundary:** repository controls plus the certified offline operator corpus.

| Risk | Severity | Current control | Residual action |
|---|---|---|---|
| Unintended live or credentialed execution | Critical → controlled | Preflight/fetch separation, explicit gates, draft PR, live jobs skipped | Retain environment protection and operator receipts |
| Mixed source denominators | High → controlled | 151-source digest and status parity are authoritative | Require parity on every regeneration |
| Four required sources lack valid rows | High | Access routes and producer boundaries are explicit; no false credit | Supply and validate source exports |
| HUD DRGR producer/registry drift | High → controlled | Producer now writes registry CSVs and normalized Parquets | Validate with authorized exports |
| Derived-output double counting | High → controlled | 212,930 rows are excluded from source credit; arithmetic closes | Keep derived/intermediate buckets separate |
| `entity_master.csv` staging lineage unproven | High | Candidate mismatch is explicit; no source credit | Identify producer/copy step and compare hashes/schema |
| Equal row counts mistaken for duplication | High → controlled | Comparator v2 validates structure and stable-key overlap | Run on operator corpus |
| Cabilderos custodian metadata drift | Medium → controlled | Explicit source override identifies Department of Justice | Regenerate the base registry during a later registry-maintenance vector |
| Main advances during review | Medium → controlled | Current base `bd337fb...` incorporated without force | Recheck base before review transition |
| Local presence mistaken for freshness | High | `probe_ran=false` and freshness remains uncertified | Perform separately authorized source assessments |

## Certification state

The last v0.8 head `b1f088c98c8175298b856a5df8215c77fa933877` passed 16/16 workflows. The remediation commit containing this report must be judged by GitHub checks, not by a self-referential SHA in the file.

Production status remains `NON_PRODUCTION_DIAGNOSTIC` until required inputs, entity lineage, freshness, reconciliation, export, and downstream-consumer gates pass.
