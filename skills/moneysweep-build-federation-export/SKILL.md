---
name: moneysweep-build-federation-export
description: >-
  Build or test MoneySweep's canonical producer export package for the
  federation. Use when the user asks to build, package, or test the canonical
  export. Runs the authoritative export entry point in test mode by default
  (offline), reports streams, manifest, hashes, counts, schemas, and the
  compatibility result — and refuses production/promotion output without explicit
  user authorization or when synthetic and live data would mix.
default_mode: offline_write
allowed_modes: [offline_write, promotion]
command_ids: [export_canonical]
owner_repo: jotaele44/moneysweep-pr
---

# moneysweep-build-federation-export

Orchestrates the canonical export; it does not reimplement packaging, ID
minting, or schema shaping. The authority is `export_canonical`
(`python3 scripts/federation_export.py --mode test`), the Hub export entry point;
the canonical-v1 bridge `moneysweep/federation/canonical_v1_bridge.py` is the
underlying library. This skill selects the mode, interprets the manifest, and
enforces the promotion gate.

## When this fires
Build / test / package the canonical producer export package requests.

## When this does NOT fire (boundary)
- Deciding whether the package is promotable → `moneysweep-assess-promotion-readiness`.
- Checking the local contract against the shared PRII/Hub contract →
  `prii-check-producer-contract`.
- Cross-producer aggregation or correlation → `thehub-pr`.

## Procedure
1. Default (offline_write, test mode): run `export_canonical`
   (`python3 scripts/federation_export.py --mode test`).
2. Read the emitted manifest — package_id, mode, per-stream files, sha256 hashes,
   record counts, schemas, compatibility result. Report them; do not recompute.
3. Promotion (production) mode is gated: run it ONLY with explicit user
   authorization. Without it, stay in test mode and report the block.
4. Contract-lineage note: `scripts/build_export_package.py` still carries a
   historical "spiderweb-pr / query-hub" consumer descriptor. Flag it as a
   lineage item for `prii-check-producer-contract`; do not act on it here.

## Required outputs
- mode used (test vs production); per-stream file list with sha256 + record
  counts; manifest package_id and schemas; the compatibility result;
- explicit go/no-go for promotion and any lineage flags raised.

## Stop conditions
- Production mode requested without promotion authorization → STOP; stay in test
  mode and surface the gate.
- Synthetic/test and live records would mix in one package → STOP; never build a
  production package from mixed data.

## Evidence & result envelope
Emit `{status, commands_considered, commands_run, artifacts, blockers,
contradictions, next_safe_action}`. Report secrets by name only. Do not claim a
package is production-ready; that decision belongs to
`moneysweep-assess-promotion-readiness`.
