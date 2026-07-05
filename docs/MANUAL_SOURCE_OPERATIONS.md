# Manual Source Operations — workflow criteria for operator-gated sources

Four required sources cannot be automated (automation probes 2026-07-04; evidence in
`reports/federation/evidence_moneysweep-pr.jsonl`). This runbook defines the operating
contract per source: **what to export, from where, where to drop it, how often, and how
freshness is enforced.**

Machine-readable counterparts:
- Drop dirs / filename patterns / expected columns / validation rules →
  `registries/manual_export_registry.yaml`
- Cadence (`update_cadence`) → `registries/source_registry.yaml`
- Staleness enforcement → the `source_freshness` gate in
  `moneysweep/runtime/validation_gates.py` (age of newest `data/manifests/<source>/` manifest vs
  cadence + grace: monthly→45d, quarterly→120d, yearly→400d; `ad_hoc` exempt)

## Standard cycle (all sources)

1. Export from the portal (per-source card below) → drop into the source's drop dir.
2. `python3 scripts/ingest_<source>.py` (each is idempotent; bilingual headers accepted).
3. `python3 scripts/write_source_manifests.py --required-only` (stamps the ingest into
   `data/manifests/<source>/`, which the freshness gate reads).
4. `python -m moneysweep.runtime.validation_gates --root . --allow-failed` — confirm the
   source's `required_source_nonempty` is green and `source_freshness` is `ok`.
5. Commit data/manifest changes per `docs/MATERIALIZATION_OPERATOR_CHECKLIST.md`.

**Stop conditions** (per `docs/TRANCHE_B_MANUAL_SOURCE_INGESTION_PREP.md`): reject
header-only files; reject files missing required columns; never hand-edit processed CSVs —
fix the raw drop and re-run the ingest.

## Per-source cards

### cor3 — COR3 recovery-project tracker · **quarterly** (stale >120d)
- **Portal:** https://recovery.pr.gov/en/transparencia (browser required — the portal serves
  empty bodies to non-browser clients; headless fetch is also blocked from CI egress).
- **Export:** the three Excel workbooks — *Financial Summary*, *Procurement Inventory*,
  *RFP and Contracts* (`COR3 Transparency Portal_*.xlsx`).
- **Drop:** `data/raw/COR3/` → `python3 scripts/ingest_cor3.py`.
- **Automation status:** portal is JS/WAF-gated; `scripts/download_cor3.py` keeps candidate
  endpoints for retry, and any operator who captures the portal's real XHR endpoint in browser
  DevTools should add it to `COR3_ENDPOINTS` there. Until then this is manual.

### hud_drgr_authorized — HUD DRGR grantee reports · **monthly** (stale >45d)
- **Portal:** https://drgr.hud.gov/ (credentialed grantee login — structurally not automatable;
  see `moneysweep/runtime/validation_gates.py` PR62 note).
- **Export:** allocation / budget / obligation / drawdown tables (CSV).
- **Drop:** `data/manual/hud_drgr/` → `python3 scripts/ingest_hud_drgr_exports.py`.
- **What it adds over automated sources:** per-activity execution detail (budget/obligated/
  drawdown) that the public `hud_cdbg_dr_public` + `hud_cdbg_mit` allocations lack.
- **Fallback:** FOIA (`docs/FOIA_REQUEST_TEMPLATES.md`).

### pr_cabilderos — OEG lobbyist registry · **quarterly** (stale >120d)
- **Portal:** the registered host `etica.pr.gov` is **dead** (gateway 502, probe 2026-07-04).
  The OEG's live site is **https://eticapr.com** — it exposes ethics datasets via Zoho dashboards
  but no lobbyist-registry export. Request the registry export via the OEG public-information
  channel: https://eticapr.com/nuestra-oficina/acceso-informacion-publica.
- **Drop:** `data/raw/Cabilderos/` → `python3 scripts/ingest_cabilderos.py`.
- **Future-source lead (probe finding):** the OEG publishes five Zoho Analytics open views —
  *Autorizaciones sobre Contratos (AC)*, *Autorización de Parientes (AP)*, *Autorizaciones Ex
  Servidores (AE)*, *Evaluaciones (EV)*, *Querellas y Resoluciones (QR)* — genuinely useful
  ethics/influence datasets (contract authorizations especially). Browser-context export only;
  candidates for new manual sources or a future headless fetcher.

### prasa — PRASA procurement · **yearly** (stale >400d); CER/CIP siblings **ad_hoc**
- **Portal:** https://www.acueductospr.com/ (HTML only; no export endpoint). Procurement files
  are operator-obtained (subastas/procurement office); CER/CIP/completed-projects PDFs drop into
  `data/raw/PRASA/<cer|cip|completed>/` for `scripts/ingest_prasa_cer.py`.
- **Drop:** `data/raw/PRASA/` → `python3 scripts/ingest_prasa.py`, then
  `python3 scripts/build_prasa_contracts_master.py` (derived vendor master).
- **Note:** PRASA **bond/financial disclosures are already automated** via `emma_bonds`
  (weekly, `scripts/download_emma.py`) — do not duplicate them here.

## Cadence summary

| source | cadence | stale after | drop dir |
|---|---|---|---|
| hud_drgr_authorized | monthly | 45d | `data/manual/hud_drgr/` |
| cor3 | quarterly | 120d | `data/raw/COR3/` |
| pr_cabilderos | quarterly | 120d | `data/raw/Cabilderos/` |
| prasa | yearly | 400d | `data/raw/PRASA/` |
| prasa_cer | ad_hoc | exempt | see registry |

The `source_freshness` gate reports `refresh_source` actions in
`data/manifests/validation_gate_report.csv`; the weekly maintenance workflow
(`.github/workflows/maintenance.yml`) surfaces the report so stale sources are visible without
anyone remembering the calendar.
