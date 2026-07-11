"""Freeze the gap-closure Phase 0 baseline.

One-shot snapshot of the repo's completeness truth *before* the gap-closure
program changes anything. Written once, then frozen: re-running without
``--force`` refuses to overwrite. Only the unresolved-gap ledger mutates after
the freeze (``--update-ledger``), and only its ``status``/``resolved_by``
fields.

Writes (under ``reports/gap_closure/``):
  baseline_manifest.json       — baseline commit, live registry snapshot,
                                 input-artifact hashes, count surfaces
  baseline_source_status.csv   — one row per live source (legacy status view)
  baseline_file_inventory.csv  — classified inventory of data/staging/processed
  baseline_contradictions.md   — evidence-linked contradictions at baseline
  unresolved_gap_ledger.csv    — open gaps; only status/resolved_by flip later

Usage:
  python3 scripts/build_gap_closure_baseline.py            # create (refuses overwrite)
  python3 scripts/build_gap_closure_baseline.py --force    # re-freeze (destructive)
  python3 scripts/build_gap_closure_baseline.py --verify   # internal reconciliation
  python3 scripts/build_gap_closure_baseline.py \
      --update-ledger GAP-009 --ledger-status resolved --resolved-by wave2a
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.audit_materialization_coverage import _is_intermediate, _materiality_tier
from scripts.build_source_recovery_matrix import build_registry_snapshot, build_rows
from scripts.gap_analysis_builder import _file_status, _source_status
from moneysweep.runtime.source_registry import load_source_registry

BASELINE_DIR = "reports/gap_closure"
PROCESSED_SUBDIR = "data/staging/processed"

# Committed artifacts whose bytes define the baseline's inputs.
INPUT_ARTIFACTS = (
    "registries/source_registry.json",
    "reports/materialization_readiness.json",
    "reports/gap_analysis_report.json",
    "reports/source_registry_status.csv",
    "reports/materialization_coverage_audit.json",
    "reports/federation_source_status_reconciliation.json",
    "reports/current_status.json",
    "federation.json",
    "data/manifests/staging_masters.json",
)

LEDGER_FIELDS = (
    "gap_id",
    "source_id",
    "gap_type",
    "description",
    "evidence_path",
    "expected_drop_dir",
    "status",
    "opened_at",
    "resolved_by",
)

SOURCE_STATUS_FIELDS = (
    "source_id",
    "family",
    "required",
    "authentication",
    "path_type",
    "automatable",
    "ready",
    "pipeline_status",
    "local_rows",
    "min_rows",
    "materiality_tier",
    "dropzone_path",
    "first_expected_output",
)

INVENTORY_FIELDS = (
    "relative_path",
    "presence",
    "rows",
    "claimed_by",
    "classification",
)

INVENTORY_CLASSIFICATIONS = frozenset({"claimed", "intermediate", "derived", "orphan", "empty"})

# Datasets the operator holds outside this clone (documented in
# reports/current_status.json completed/blocked notes) plus in-repo defects.
# gap_type vocabulary: dataset_absent | acquired_not_ingested | orphan_output |
# count_drift | intake_path_dead | code_defect | phantom_dropzones |
# stale_docs | nonreproducible_artifact
_LEDGER_SEED: tuple[dict[str, str], ...] = (
    {
        "gap_id": "GAP-001",
        "source_id": "donaciones_pr",
        "gap_type": "dataset_absent",
        "description": (
            "Donaciones_20260320.csv (4,686 CEE campaign-donation rows) was placed in "
            "data/raw/Donaciones/ on the operator machine (2026-07-09 pass) but never "
            "git-tracked (.gitignore allow-list excludes it); absent in this clone."
        ),
        "evidence_path": "reports/current_status.json",
        "expected_drop_dir": "data/raw/Donaciones/",
    },
    {
        "gap_id": "GAP-002",
        "source_id": "pr_cabilderos",
        "gap_type": "dataset_absent",
        "description": (
            "pr_cabilderos_roster_2025-03-26.csv (1,175 lobbyist-client rows) and "
            "pr_cabilderos_certifications_only.csv (23 rows) built on the operator "
            "machine but never git-tracked; the authoritative 81-page "
            "Registro_de_cabilderos_Abril_18_2026_2.pdf also remains unprocessed."
        ),
        "evidence_path": "reports/current_status.json",
        "expected_drop_dir": "data/raw/Cabilderos/",
    },
    {
        "gap_id": "GAP-003",
        "source_id": "cor3",
        "gap_type": "dataset_absent",
        "description": (
            "COR3 (recovery.pr.gov) xlsx exports held outside the repo; the latest "
            "committed cor3 per-source manifest records row_count 0 "
            "(empty_or_header_only)."
        ),
        "evidence_path": "data/manifests/cor3/",
        "expected_drop_dir": "data/raw/COR3/",
    },
    {
        "gap_id": "GAP-004",
        "source_id": "ocpr_contracts",
        "gap_type": "dataset_absent",
        "description": (
            "OCPR consultacontratos contract-registry xlsx snapshot held outside the "
            "repo; scripts/ingest_ocpr_contracts.py dropzone is empty/nonexistent."
        ),
        "evidence_path": "scripts/ingest_ocpr_contracts.py",
        "expected_drop_dir": "data/raw/OCPR_Contracts/",
    },
    {
        "gap_id": "GAP-005",
        "source_id": "oficina_contralor",
        "gap_type": "dataset_absent",
        "description": (
            "Oficina del Contralor audit-report exports held outside the repo; "
            "scripts/ingest_contralor.py dropzone is empty/nonexistent."
        ),
        "evidence_path": "scripts/ingest_contralor.py",
        "expected_drop_dir": "data/raw/Oficina del Contralor/",
    },
    {
        "gap_id": "GAP-006",
        "source_id": "fpds_report_builder",
        "gap_type": "dataset_absent",
        "description": (
            "FPDS Report Builder FY2020-FY2024 xlsx exports (and the Jul-5 "
            "pr_report_builder_master.csv) held outside the repo; "
            "scripts/ingest_report_builder.py finds no inputs in this clone."
        ),
        "evidence_path": "scripts/ingest_report_builder.py",
        "expected_drop_dir": "data/raw/FPDS_Report_Builder/",
    },
    {
        "gap_id": "GAP-007",
        "source_id": "sam_entities",
        "gap_type": "dataset_absent",
        "description": (
            "SAM.gov public monthly extracts (~1.1 GB SAM_PUBLIC_MONTHLY_V2_*.dat) "
            "held outside the repo; scripts/ingest_sam_bulk.py DAT_SEARCH_DIRS "
            "(data/raw/sam) is empty/nonexistent."
        ),
        "evidence_path": "scripts/ingest_sam_bulk.py",
        "expected_drop_dir": "data/raw/sam/",
    },
    {
        "gap_id": "GAP-008",
        "source_id": "usaspending_prime",
        "gap_type": "dataset_absent",
        "description": (
            "USAspending 2026-07-07 PR slice exports (and a ~175MB bulk-award-export "
            "archive cataloged 2026-07-09) held outside the repo; not ingested and "
            "not deduplicated against the committed masters."
        ),
        "evidence_path": "reports/current_status.json",
        "expected_drop_dir": "data/raw/USAspending_Slices/",
    },
    {
        "gap_id": "GAP-009",
        "source_id": "act_transition_contracts",
        "gap_type": "acquired_not_ingested",
        "description": (
            "Committed extract data/raw/act_transition/transition_contracts_extracted.csv "
            "(656 ACT_2020 rows before dedupe) is present but not materialized in this "
            "clone; declared intake paths (data/manual/act_transition/) do not exist."
        ),
        "evidence_path": "data/raw/act_transition/transition_contracts_extracted.csv",
        "expected_drop_dir": "data/raw/act_transition/",
    },
    {
        "gap_id": "GAP-010",
        "source_id": "acuden_2024_transition",
        "gap_type": "acquired_not_ingested",
        "description": (
            "Committed extract holds 1,147 ACUDEN_2024 rows (before dedupe) not "
            "materialized in this clone; declared intake paths "
            "(data/manual/acuden_2024/) do not exist."
        ),
        "evidence_path": "data/raw/act_transition/transition_contracts_extracted.csv",
        "expected_drop_dir": "data/raw/act_transition/",
    },
    {
        "gap_id": "GAP-011",
        "source_id": "",
        "gap_type": "orphan_output",
        "description": (
            "pr_grants_master.csv rows on the operator disk are claimed by no registry "
            "source (orphan_rows 104,280 per the 2026-06-17 committed coverage audit); "
            "registry must either claim or explicitly derive them."
        ),
        "evidence_path": "reports/materialization_coverage_audit.json",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-012",
        "source_id": "",
        "gap_type": "count_drift",
        "description": (
            "federation.json source_truth says 143 total / 98 automatable while the "
            "live registry and reports/materialization_readiness.json say 144 / 99."
        ),
        "evidence_path": "federation.json",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-013",
        "source_id": "",
        "gap_type": "count_drift",
        "description": (
            "reports/federation_source_status_reconciliation.json says 141 total / 95 "
            "automatable / 46 queued (manual_export 39) vs live 144 / 99 / 45 "
            "(manual_export 38)."
        ),
        "evidence_path": "reports/federation_source_status_reconciliation.json",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-014",
        "source_id": "",
        "gap_type": "count_drift",
        "description": (
            "reports/current_status.json materialization_readiness_truth block says "
            "136 total sources while source_registry_current in the same file says 144."
        ),
        "evidence_path": "reports/current_status.json",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-015",
        "source_id": "act_transition_contracts",
        "gap_type": "intake_path_dead",
        "description": (
            "manual_drop_dir data/manual/act_transition/ and data/manual/acuden_2024/ "
            "(source_registry + manual_export_registry) do not exist; actual acquired "
            "files live under data/raw/act_transition/ and data/raw/Vigentes al "
            "Momento de Transición/."
        ),
        "evidence_path": "registries/source_registry.yaml",
        "expected_drop_dir": "data/raw/act_transition/",
    },
    {
        "gap_id": "GAP-016",
        "source_id": "",
        "gap_type": "code_defect",
        "description": (
            "moneysweep/update_controller/policy.py _manual_export_ids reads keys "
            "sources|manual_sources|entries but manual_export_registry.json's real "
            "key is manual_exports — manual-export policy inference is silently empty."
        ),
        "evidence_path": "moneysweep/update_controller/policy.py",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-017",
        "source_id": "",
        "gap_type": "phantom_dropzones",
        "description": (
            "scripts/source_intake_tranche_b.py SOURCE_SPECS point at dropzones that "
            "match nothing on disk and disagree with manual_export_registry (e.g. "
            "data/raw/ACT Transition Contracts)."
        ),
        "evidence_path": "scripts/source_intake_tranche_b.py",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-018",
        "source_id": "",
        "gap_type": "stale_docs",
        "description": (
            "docs/MATERIALIZATION_RUNBOOK.md quotes 124 total / 68 automatable / 56 "
            "queued — a frozen snapshot several registry generations old (live: "
            "144 / 99 / 45)."
        ),
        "evidence_path": "docs/MATERIALIZATION_RUNBOOK.md",
        "expected_drop_dir": "",
    },
    {
        "gap_id": "GAP-019",
        "source_id": "",
        "gap_type": "nonreproducible_artifact",
        "description": (
            "reports/materialization_coverage_audit.json was generated 2026-06-17 "
            "against root /Users/jotaele/Developer/Contract-Sweeper — an operator "
            "machine path — so its local-truth layer cannot be reproduced from this "
            "repo."
        ),
        "evidence_path": "reports/materialization_coverage_audit.json",
        "expected_drop_dir": "",
    },
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _read_json(root: Path, rel: str) -> dict[str, Any]:
    try:
        return json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def artifact_fingerprints(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rel in INPUT_ARTIFACTS:
        p = root / rel
        if p.exists():
            out[rel] = {"sha256": _sha256(p), "size_bytes": p.stat().st_size}
        else:
            out[rel] = {"sha256": "", "size_bytes": 0, "missing": True}
    return out


def count_surfaces(root: Path) -> dict[str, Any]:
    """Every committed place a source count lives, side by side with live truth."""
    readiness = _read_json(root, "reports/materialization_readiness.json")
    federation = _read_json(root, "federation.json").get("source_truth", {})
    reconciliation = _read_json(root, "reports/federation_source_status_reconciliation.json")
    current = _read_json(root, "reports/current_status.json")
    gap = _read_json(root, "reports/gap_analysis_report.json")
    audit = _read_json(root, "reports/materialization_coverage_audit.json")
    live = build_registry_snapshot(load_source_registry(root).get("sources", []))
    return {
        "live_registry": live,
        "materialization_readiness": {
            "total_sources": readiness.get("total_sources"),
            "automatable_total": readiness.get("automatable_total"),
            "queued_excluded_total": readiness.get("queued_excluded_total"),
        },
        "federation_source_truth": {
            "total_sources": federation.get("total_sources"),
            "automatable_total": federation.get("automatable_total"),
            "queued_excluded_total": federation.get("queued_excluded_total"),
        },
        "federation_source_status_reconciliation": {
            "canonical_source_count": reconciliation.get("canonical_source_count"),
            "automatable_total": reconciliation.get("automatable_total"),
            "queued_excluded_total": reconciliation.get("queued_excluded_total"),
        },
        "current_status": {
            "source_registry_current_total": (current.get("source_registry_current", {}) or {}).get(
                "total_sources"
            ),
            "materialization_readiness_truth_total": (
                current.get("materialization_readiness_truth", {}) or {}
            ).get("total_sources"),
        },
        "gap_analysis_report": {
            "total_sources": gap.get("total_sources"),
            "fully_materialized": gap.get("fully_materialized"),
            "coverage_rate": gap.get("coverage_rate"),
        },
        "materialization_coverage_audit": {
            "total_sources": (audit.get("local_truth_summary", {}) or {}).get("total_sources"),
            "fully_materialized": (audit.get("local_truth_summary", {}) or {}).get(
                "fully_materialized"
            ),
            "root": audit.get("root"),
            "generated_at": audit.get("generated_at"),
        },
    }


def build_source_status_rows(root: Path) -> list[dict[str, Any]]:
    """Legacy-view status row per live source (the *pre-repair* control plane)."""
    sources = {s.get("source_id", ""): s for s in load_source_registry(root).get("sources", [])}
    rows: list[dict[str, Any]] = []
    for matrix_row in build_rows():
        sid = matrix_row["source_id"]
        src = sources.get(sid, {})
        expected = src.get("expected_outputs", []) or []
        statuses = [_file_status(root, rel) for rel in expected]
        local_rows = sum(f["row_count"] for f in statuses if f["row_count"] > 0)
        rows.append(
            {
                "source_id": sid,
                "family": matrix_row["family"],
                "required": matrix_row["required"],
                "authentication": matrix_row["authentication"],
                "path_type": matrix_row["path_type"],
                "automatable": matrix_row["automatable"],
                "ready": matrix_row["ready"],
                "pipeline_status": _source_status(root, src),
                "local_rows": local_rows,
                "min_rows": matrix_row["min_rows"],
                "materiality_tier": _materiality_tier(local_rows),
                "dropzone_path": matrix_row["dropzone_path"],
                "first_expected_output": expected[0] if expected else "",
            }
        )
    rows.sort(key=lambda r: r["source_id"])
    return rows


def build_file_inventory(root: Path) -> list[dict[str, Any]]:
    """Classify every processed CSV (on disk, recursively) plus manifest-only entries."""
    declared: dict[str, list[str]] = {}
    declared_names: dict[str, list[str]] = {}
    for s in load_source_registry(root).get("sources", []):
        for o in s.get("expected_outputs", []) or []:
            declared.setdefault(o, []).append(s["source_id"])
            declared_names.setdefault(Path(o).name, []).append(s["source_id"])

    proc = root / PROCESSED_SUBDIR
    rows: list[dict[str, Any]] = []
    seen_rel: set[str] = set()
    if proc.is_dir():
        for p in sorted(proc.rglob("*.csv")):
            rel = p.relative_to(root).as_posix()
            seen_rel.add(rel)
            try:
                with p.open(encoding="utf-8-sig", newline="") as f:
                    n = max(0, sum(1 for _ in f) - 1)
            except OSError:
                n = 0
            claimed_by = declared.get(rel) or declared_names.get(p.name) or []
            in_subdir = p.parent != proc
            if claimed_by:
                classification = "claimed"
            elif _is_intermediate(p.name):
                classification = "intermediate"
            elif in_subdir:
                classification = "derived"
            elif n >= 1:
                classification = "orphan"
            else:
                classification = "empty"
            rows.append(
                {
                    "relative_path": rel,
                    "presence": "disk",
                    "rows": n,
                    "claimed_by": ";".join(sorted(claimed_by)),
                    "classification": classification,
                }
            )
    manifest = _read_json(root, "data/manifests/staging_masters.json").get("files", {})
    for rel in sorted(manifest):
        if rel in seen_rel:
            continue
        name = Path(rel).name
        claimed_by = declared.get(rel) or declared_names.get(name) or []
        row_count = int(manifest[rel].get("row_count", 0))
        if claimed_by:
            classification = "claimed"
        elif _is_intermediate(name):
            classification = "intermediate"
        elif row_count >= 1:
            classification = "orphan"
        else:
            classification = "empty"
        rows.append(
            {
                "relative_path": rel,
                "presence": "manifest_only",
                "rows": row_count,
                "claimed_by": ";".join(sorted(claimed_by)),
                "classification": classification,
            }
        )
    return rows


def build_ledger_rows(opened_at: str) -> list[dict[str, str]]:
    rows = []
    for seed in _LEDGER_SEED:
        rows.append(
            {
                **{k: seed.get(k, "") for k in LEDGER_FIELDS},
                "status": "open",
                "opened_at": opened_at,
                "resolved_by": "",
            }
        )
    return rows


def render_contradictions(surfaces: dict[str, Any], commit: str) -> str:
    live = surfaces["live_registry"]
    fed = surfaces["federation_source_truth"]
    rec = surfaces["federation_source_status_reconciliation"]
    cur = surfaces["current_status"]
    gap = surfaces["gap_analysis_report"]
    audit = surfaces["materialization_coverage_audit"]
    return f"""# Gap-Closure Baseline — Contradiction Ledger

Baseline commit: `{commit}`. Live registry truth at this commit:
**{live["source_count"]} sources** (`source_ids_sha256 {live["source_ids_sha256"][:16]}…`).
Each finding cites the committed evidence. Resolution targets reference the
gap-closure commit sequence; open items live in `unresolved_gap_ledger.csv`.

## 1. Four committed source counts disagree ({fed["total_sources"]}/{rec["canonical_source_count"]}/{cur["materialization_readiness_truth_total"]}/{live["source_count"]})

| Surface | Total sources | Automatable |
| --- | ---: | ---: |
| live registry / `reports/materialization_readiness.json` | {surfaces["materialization_readiness"]["total_sources"]} | {surfaces["materialization_readiness"]["automatable_total"]} |
| `federation.json` → `source_truth` | {fed["total_sources"]} | {fed["automatable_total"]} |
| `reports/federation_source_status_reconciliation.json` | {rec["canonical_source_count"]} | {rec["automatable_total"]} |
| `reports/current_status.json` → `materialization_readiness_truth` | {cur["materialization_readiness_truth_total"]} | — |

`reports/current_status.json` contradicts itself: `source_registry_current`
says {cur["source_registry_current_total"]} while `materialization_readiness_truth` says
{cur["materialization_readiness_truth_total"]}. Only `materialization_readiness.json` and the
`source_registry_current` block are test-pinned; the other three surfaces are
frozen snapshots with no gate. **Resolved by phase1a** (values + drift gate).

## 2. "6 fully materialized" vs "58 fully materialized" — both committed

`reports/gap_analysis_report.json` (2026-07-10) reports
**{gap["fully_materialized"]} fully materialized of {gap["total_sources"]}**
(coverage {gap["coverage_rate"]}), computed against a clean checkout plus the
committed staging manifest. `reports/materialization_coverage_audit.json`
({audit["generated_at"]}) reports **{audit["fully_materialized"]} of
{audit["total_sources"]}** — computed against the operator's working tree,
where the gitignored masters exist, and against an older 136-source registry.
Different filesystem truth AND different denominator, presented side by side
with no reconciliation note. **Addressed by phase1c** (regeneration at this
commit + explicit view labels).

## 3. The coverage audit is not reproducible from this repo

`reports/materialization_coverage_audit.json` records
`root: {audit["root"]}` — an operator-machine path. None of its
`local_rows` figures can be recomputed from this clone. **Addressed by
phase1c** (regenerate against the repo tree; local view separated from
operator view).

## 4. 104,280 orphan rows invisible to the registry

The same audit records `orphan_rows: 104280` — `pr_grants_master.csv` rows on
the operator disk claimed by **no** registry source (`inventory_processed_files`
docstring documents the drift class). Real data, structurally invisible to
registry-driven accounting. **Open: GAP-011.**

## 5. current_status says Donaciones/Cabilderos were "placed" — not in git

`reports/current_status.json` (2026-07-09 pass) records
`data/raw/Donaciones/Donaciones_20260320.csv` (4,686 rows) and
`data/raw/Cabilderos/pr_cabilderos_roster_2025-03-26.csv` (1,175 rows) as
placed and validated — but the same file's blocked-items note admits those
directories are **not covered by .gitignore's allow-list**, so the files were
never tracked and are absent in this clone. Acquisition happened; preservation
did not. **Open: GAP-001, GAP-002 (dropzones scaffolded by wave2b).**

## 6. Governance: ingestion is both forbidden and the declared next step

`docs/BLOCKED_PHASES_AND_UNFREEZE_RULES.md` (R4.9Z era) lists "source
ingestion" as forbidden while paused; `reports/current_status.json` sets
`next_command: TRANCHE_B_MANUAL_SOURCE_INGESTION` and
`docs/TRANCHE_B_MANUAL_SOURCE_INGESTION_PREP.md` scopes ACT/ACUDEN as its P0.
Resolution adopted here: the gap-closure program executes the sanctioned
Tranche-B *diagnostic* path — offline materialization of operator-delivered,
already-committed files, no downloads, no production promotion;
`production_status=NON_PRODUCTION_DIAGNOSTIC` and `phase_7_8_blocked=True`
are untouched.

## 7. ACT/ACUDEN declared intake paths do not exist

`registries/source_registry.yaml` declares `manual_drop_dir:
data/manual/act_transition/` and `data/manual/acuden_2024/`;
`registries/manual_export_registry.yaml` mirrors them. Neither directory
exists; the acquired files actually live in `data/raw/act_transition/` and
`data/raw/Vigentes al Momento de Transición/`. Only the producer's committed-
extract fallback tier works. **Resolved by wave2a.**

## 8. Tranche-B intake script points at phantom dropzones

`scripts/source_intake_tranche_b.py` SOURCE_SPECS reference dropzones like
`data/raw/ACT Transition Contracts` that match nothing on disk and disagree
with `manual_export_registry.yaml`. **Resolved by wave2a/wave2b.**

## 9. Runbook quotes a registry three generations old

`docs/MATERIALIZATION_RUNBOOK.md` states 124 total / 68 automatable / 56
queued; live truth is {live["source_count"]} / {surfaces["materialization_readiness"]["automatable_total"]} / {surfaces["materialization_readiness"]["queued_excluded_total"]}. **Resolved by phase1a**
(replace frozen figures with a pointer to the generated report).

## 10. Manual-export policy inference reads the wrong key

`moneysweep/update_controller/policy.py::_manual_export_ids` looks for
`sources|manual_sources|entries` in `manual_export_registry.json`, whose real
top-level key is `manual_exports` — the function always returns empty, so
manual-export sources get no policy inference. **Resolved by wave2b.**

## 11. Queued-source breakdowns disagree by one

`reports/federation_source_status_reconciliation.json` records
`queued_excluded_total: {rec["queued_excluded_total"]}` (manual_export 39);
`reports/materialization_readiness.json` records
`{surfaces["materialization_readiness"]["queued_excluded_total"]}` (manual_export 38). Same registry, different
snapshots. **Resolved by phase1a.**
"""


def write_baseline(root: Path, *, force: bool = False) -> dict[str, Any]:
    out_dir = root / BASELINE_DIR
    manifest_path = out_dir / "baseline_manifest.json"
    if manifest_path.exists() and not force:
        raise SystemExit(
            f"{manifest_path} already exists — the baseline is frozen. "
            "Use --force to re-freeze (destructive) or --update-ledger for ledger flips."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    commit = _git_head(root)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    surfaces = count_surfaces(root)
    status_rows = build_source_status_rows(root)
    inventory = build_file_inventory(root)
    ledger = build_ledger_rows(generated_at)

    with (out_dir / "baseline_source_status.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(SOURCE_STATUS_FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(status_rows)

    with (out_dir / "baseline_file_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(INVENTORY_FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(inventory)

    with (out_dir / "unresolved_gap_ledger.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(LEDGER_FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(ledger)

    (out_dir / "baseline_contradictions.md").write_text(
        render_contradictions(surfaces, commit), encoding="utf-8"
    )

    manifest = {
        "schema_version": "gap_closure_baseline_v1",
        "baseline_commit": commit,
        "generated_at": generated_at,
        "registry": surfaces["live_registry"],
        "count_surfaces": surfaces,
        "input_artifacts": artifact_fingerprints(root),
        "source_status_rows": len(status_rows),
        "file_inventory": {
            "rows": len(inventory),
            "disk_files": sum(1 for r in inventory if r["presence"] == "disk"),
            "manifest_only_files": sum(1 for r in inventory if r["presence"] == "manifest_only"),
            "orphan_files": sum(1 for r in inventory if r["classification"] == "orphan"),
        },
        "ledger": {
            "rows": len(ledger),
            "open": sum(1 for r in ledger if r["status"] == "open"),
        },
        "outputs": [
            f"{BASELINE_DIR}/baseline_manifest.json",
            f"{BASELINE_DIR}/baseline_source_status.csv",
            f"{BASELINE_DIR}/baseline_file_inventory.csv",
            f"{BASELINE_DIR}/baseline_contradictions.md",
            f"{BASELINE_DIR}/unresolved_gap_ledger.csv",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def read_ledger(root: Path) -> list[dict[str, str]]:
    path = root / BASELINE_DIR / "unresolved_gap_ledger.csv"
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def update_ledger(root: Path, gap_id: str, status: str, resolved_by: str) -> None:
    rows = read_ledger(root)
    hit = [r for r in rows if r["gap_id"] == gap_id]
    if not hit:
        raise SystemExit(f"unknown gap_id {gap_id!r}")
    for r in hit:
        r["status"] = status
        r["resolved_by"] = resolved_by
    path = root / BASELINE_DIR / "unresolved_gap_ledger.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(LEDGER_FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def verify_baseline(root: Path) -> list[str]:
    """Internal reconciliation of the frozen baseline artifacts."""
    errors: list[str] = []
    out_dir = root / BASELINE_DIR
    manifest = _read_json(root, f"{BASELINE_DIR}/baseline_manifest.json")
    if not manifest:
        return [f"{BASELINE_DIR}/baseline_manifest.json missing or unreadable"]
    for rel in manifest.get("outputs", []):
        if not (root / rel).exists():
            errors.append(f"declared output missing: {rel}")

    with (out_dir / "baseline_source_status.csv").open(encoding="utf-8", newline="") as f:
        status_rows = list(csv.DictReader(f))
    if len(status_rows) != manifest.get("source_status_rows"):
        errors.append(
            f"source-status rows {len(status_rows)} != manifest "
            f"{manifest.get('source_status_rows')}"
        )
    if len(status_rows) != manifest.get("registry", {}).get("source_count"):
        errors.append(
            f"source-status rows {len(status_rows)} != baseline registry count "
            f"{manifest.get('registry', {}).get('source_count')}"
        )
    ids = [r["source_id"] for r in status_rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate source_id in baseline_source_status.csv")

    with (out_dir / "baseline_file_inventory.csv").open(encoding="utf-8", newline="") as f:
        inv_rows = list(csv.DictReader(f))
    bad = {r["classification"] for r in inv_rows} - INVENTORY_CLASSIFICATIONS
    if bad:
        errors.append(f"unknown inventory classifications: {sorted(bad)}")
    if len(inv_rows) != manifest.get("file_inventory", {}).get("rows"):
        errors.append("file-inventory row count disagrees with manifest")

    ledger = read_ledger(root)
    if len(ledger) != manifest.get("ledger", {}).get("rows"):
        errors.append("ledger row count disagrees with manifest")
    gap_ids = [r["gap_id"] for r in ledger]
    if len(gap_ids) != len(set(gap_ids)):
        errors.append("duplicate gap_id in ledger")
    for r in ledger:
        if r["status"] not in {"open", "resolved", "rejected"}:
            errors.append(f"{r['gap_id']}: invalid status {r['status']!r}")
        if r["status"] != "open" and not r["resolved_by"]:
            errors.append(f"{r['gap_id']}: non-open status without resolved_by")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    p.add_argument("--force", action="store_true", help="re-freeze over an existing baseline")
    p.add_argument("--verify", action="store_true", help="verify internal reconciliation")
    p.add_argument("--update-ledger", metavar="GAP_ID", help="flip one ledger row's status")
    p.add_argument("--ledger-status", default="resolved", choices=["open", "resolved", "rejected"])
    p.add_argument("--resolved-by", default="", help="commit ref / phase that resolved the gap")
    a = p.parse_args(argv)
    root = Path(a.root)

    if a.update_ledger:
        if a.ledger_status != "open" and not a.resolved_by:
            p.error("--resolved-by is required when resolving/rejecting a gap")
        update_ledger(root, a.update_ledger, a.ledger_status, a.resolved_by)
        print(f"ledger: {a.update_ledger} -> {a.ledger_status} ({a.resolved_by})")
        return 0
    if a.verify:
        errors = verify_baseline(root)
        for e in errors:
            print(f"VERIFY FAIL: {e}")
        print("baseline verify: " + ("FAIL" if errors else "OK"))
        return 1 if errors else 0

    manifest = write_baseline(root, force=a.force)
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in (
                    "baseline_commit",
                    "registry",
                    "source_status_rows",
                    "file_inventory",
                    "ledger",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
