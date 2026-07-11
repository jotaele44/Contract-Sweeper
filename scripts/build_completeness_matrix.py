"""Multi-dimensional completeness matrix — one status vector per source.

The gap-closure control plane's main report (phase 1.2): for every source in
the live registry, the seven status dimensions plus materiality label from
``moneysweep/validation/completeness.py``, joined with the readiness
classifier's path types and the unresolved-gap ledger's acquisition evidence.

Deterministic and byte-identical on re-run (no timestamps; inputs are the
committed registries, manifests, and ledger — the same clean-checkout fallback
discipline as ``gap_analysis_builder``), so CI can regenerate and diff.

Outputs:
  reports/completeness_matrix.csv    — per-source status vectors
  reports/completeness_matrix.json   — dimension roll-ups

Usage:
  python3 scripts/build_completeness_matrix.py [--root /path/to/repo]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_gap_closure_baseline import BASELINE_DIR
from scripts.build_source_recovery_matrix import build_rows
from scripts.gap_analysis_builder import _file_status, _source_status
from moneysweep.runtime.source_registry import load_source_registry
from moneysweep.validation.completeness import (
    StatusVector,
    compute_status_vector,
    load_coverage_contracts,
    manifest_profile,
)
from moneysweep.validation.source_coverage import FIXTURE_TOKENS

OUT_CSV = "reports/completeness_matrix.csv"
OUT_JSON = "reports/completeness_matrix.json"

CSV_FIELDS = (
    "source_id",
    "family",
    "required",
    "path_type",
    "wired_status",
    "acquisition_status",
    "materialization_status",
    "coverage_status",
    "reconciliation_status",
    "freshness_status",
    "certification_status",
    "materiality_label",
    "has_contract",
    "local_rows",
    "min_rows",
    "fixture_signal",
    "dropzone_path",
    "coverage_reasons",
)


def _ledger_acquisition_hints(root: Path) -> dict[str, str]:
    """acquisition_status overrides from open unresolved-gap ledger rows.

    Only ``dataset_absent`` / ``acquired_not_ingested`` rows carry acquisition
    semantics, and a hint never overrides a source that already has local rows
    (an open gap may be *incremental* — e.g. new slices for an already-
    materialized lane).
    """
    path = root / BASELINE_DIR / "unresolved_gap_ledger.csv"
    hints: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "open" or not row.get("source_id"):
                    continue
                if row.get("gap_type") == "dataset_absent":
                    hints[row["source_id"]] = "not_acquired"
                elif row.get("gap_type") == "acquired_not_ingested":
                    hints[row["source_id"]] = "acquired_not_ingested"
    except OSError:
        pass
    return hints


def _fixture_signal(root: Path, producer_script: str) -> bool:
    """Advisory-only substring scan of the producer for fixture tokens.

    Deliberately NOT fed into materiality/certification: the token scan is
    noisy (any script mentioning "sample" trips it). Authoritative fixture
    blocking lives in the evaluator's ``fixture_detected`` gate and the
    production-status validator; this column just surfaces where to look.
    """
    if not producer_script:
        return False
    path = root / producer_script
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    return any(tok in text for tok in FIXTURE_TOKENS)


def build_matrix(root: Path) -> list[dict[str, Any]]:
    sources = {s.get("source_id", ""): s for s in load_source_registry(root).get("sources", [])}
    contracts = load_coverage_contracts(root)
    hints = _ledger_acquisition_hints(root)

    out: list[dict[str, Any]] = []
    for matrix_row in build_rows(root):
        sid = matrix_row["source_id"]
        src = sources.get(sid, {})
        expected = src.get("expected_outputs", []) or []
        statuses = [_file_status(root, rel) for rel in expected]
        local_rows = sum(f["row_count"] for f in statuses if f["row_count"] > 0)
        materialization = _source_status(root, src, statuses)

        contract = contracts.get(sid)
        profile = manifest_profile(root, sid) if contract else {}
        observed_total: float | None = None
        monetary = (contract or {}).get("monetary_reconciliation") or {}
        if monetary.get("amount_field"):
            observed_total = (profile.get("monetary_totals") or {}).get(monetary["amount_field"])

        acquisition = hints.get(sid) if local_rows == 0 else None
        vector: StatusVector = compute_status_vector(
            src,
            path_type=matrix_row["path_type"],
            materialization_status=materialization,
            local_rows=local_rows,
            contract=contract,
            field_completeness_pct=profile.get("field_completeness_pct") or None,
            observed_monetary_total=observed_total,
            acquisition_status=acquisition,
        )
        out.append(
            {
                "source_id": sid,
                "family": matrix_row["family"],
                "required": matrix_row["required"],
                "path_type": matrix_row["path_type"],
                **{k: v for k, v in vector.as_dict().items() if k not in ("source_id",)},
                "local_rows": local_rows,
                "min_rows": matrix_row["min_rows"],
                "fixture_signal": _fixture_signal(root, src.get("producer_script", "")),
                "dropzone_path": matrix_row["dropzone_path"],
            }
        )
    out.sort(key=lambda r: r["source_id"])
    return out


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _counts(field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in rows:
            key = str(r[field])
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    return {
        "schema_version": "completeness_matrix_v1",
        "total_sources": len(rows),
        "contracted_sources": sum(1 for r in rows if r["has_contract"]),
        "by_wired_status": _counts("wired_status"),
        "by_acquisition_status": _counts("acquisition_status"),
        "by_materialization_status": _counts("materialization_status"),
        "by_coverage_status": _counts("coverage_status"),
        "by_reconciliation_status": _counts("reconciliation_status"),
        "by_certification_status": _counts("certification_status"),
        "by_materiality_label": _counts("materiality_label"),
        "outputs": [OUT_CSV, OUT_JSON],
    }


def render_csv(rows: list[dict[str, Any]]) -> str:
    """Deterministic CSV serialization (used for byte-identity gating)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(CSV_FIELDS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def render_json(summary: dict[str, Any]) -> str:
    return json.dumps(summary, indent=2) + "\n"


def write_outputs(root: Path) -> dict[str, Any]:
    rows = build_matrix(root)
    summary = build_summary(rows)
    csv_path = root / OUT_CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(render_csv(rows), encoding="utf-8", newline="")
    (root / OUT_JSON).write_text(render_json(summary), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    summary = write_outputs(Path(args.root))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
