"""Contract-finance export adapter — emit the SpiderWeb consumer bundle.

SpiderWeb's ``readiness/contract_finance_layer.py`` scores a 4-file bundle:

    contract_awards.geojson
    financial_flows.geojson
    municipality_funding_density.csv
    contract_finance_ingest_report.json

Nothing in this repo produced those files before — the handoff was hand-managed.
This adapter closes that gap. It reuses the existing row-level geo reasoning
(``scripts/run_contract_finance_geo_reasoning.py``) to classify award/transaction
rows to Puerto Rico municipalities, then projects them into the GeoJSON feature
shape SpiderWeb's scorer reads (``properties``: ``record_id``, ``entity_id``,
``amount``, ``date``, ``municipality_code``, ``municipality_name``,
``feature_type``, ``source_layer``, ``source_id``), aggregates a clean
per-municipality density, and writes an ingest report that surfaces the
**Centinelas pre-official** contribution for downstream provenance.

Inputs come from wherever the geo reasoner reads them: an ``--export-dir`` of
export streams (``funding_awards.jsonl`` / ``transactions.jsonl`` — e.g. the
Centinelas candidates from ``scripts/ingest_centinelas_signals.py``) and/or the
canonical masters under ``--processed-dir``.

Usage:
  python3 scripts/build_contract_finance_bundle.py --export-dir exports/centinelas_intake
  python3 scripts/build_contract_finance_bundle.py --processed-dir tests/fixtures/sample_master_inputs
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_contract_finance_geo_reasoning import (  # noqa: E402
    DEFAULT_CROSSWALK,
    DEFAULT_PROCESSED_DIR,
    _read_csv,
    run as run_geo_reasoning,
)

EXPORT_CONTRACT_VERSION = "1.2.0"
PRODUCER = "moneysweep-pr"
CENTINELAS_SOURCE_ID = "centinelas-pr"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "contract_finance"

CONTRACT_AWARDS = "contract_awards.geojson"
FINANCIAL_FLOWS = "financial_flows.geojson"
MUNICIPALITY_DENSITY = "municipality_funding_density.csv"
INGEST_REPORT = "contract_finance_ingest_report.json"
REQUIRED_OUTPUTS = (CONTRACT_AWARDS, FINANCIAL_FLOWS, MUNICIPALITY_DENSITY, INGEST_REPORT)

DENSITY_COLUMNS = ["municipality_code", "municipality_name", "total_amount", "record_count"]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and result not in (float("inf"), float("-inf")) else default


def _feature(row: dict[str, str], feature_type: str) -> dict[str, Any]:
    """Project one geo-reasoned row into a SpiderWeb-consumable GeoJSON feature.

    Geometry is null — the finance record is placed by municipality (the scorer
    keys on ``municipality_code``); MoneySweep carries no point geometry itself.
    """
    return {
        "type": "Feature",
        "geometry": None,
        "properties": {
            "record_id": row.get("record_id", ""),
            "entity_id": row.get("recipient", ""),
            "amount": _num(row.get("amount")),
            "date": row.get("event_date", ""),
            "municipality_code": row.get("municipality_code_canonical", ""),
            "municipality_name": row.get("municipality_name_canonical", ""),
            "feature_type": feature_type,
            "source_layer": "contract_finance",
            "source_id": row.get("source_dataset", ""),
            "geo_resolution_reason": row.get("geo_resolution_reason", ""),
            "geo_confidence": _num(row.get("geo_confidence")),
        },
    }


def _write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": features,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _density(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Aggregate a clean per-municipality density (one row per municipality_code)."""
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"municipality_name": "", "total_amount": 0.0, "record_count": 0}
    )
    for row in rows:
        code = row.get("municipality_code_canonical") or "UNKNOWN"
        g = groups[code]
        g["municipality_name"] = row.get("municipality_name_canonical") or g["municipality_name"]
        g["total_amount"] += _num(row.get("amount"))
        g["record_count"] += 1
    out = []
    for code, g in groups.items():
        out.append(
            {
                "municipality_code": code,
                "municipality_name": g["municipality_name"],
                "total_amount": round(g["total_amount"], 2),
                "record_count": g["record_count"],
            }
        )
    out.sort(key=lambda r: (-r["total_amount"], r["municipality_code"]))
    return out


def _write_density(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DENSITY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_bundle(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    export_dir: str | Path | None = None,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    crosswalk_path: str | Path = DEFAULT_CROSSWALK,
    build_crosswalk: bool = False,
) -> dict[str, Any]:
    """Produce the SpiderWeb 4-file contract-finance bundle. Returns the ingest report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Reuse the existing row-level geo reasoner (into a scratch dir so we don't
    # disturb its committed artifacts unless the caller targets that dir).
    with tempfile.TemporaryDirectory() as scratch:
        geo_summary = run_geo_reasoning(
            processed_dir=processed_dir,
            output_dir=scratch,
            export_dir=export_dir,
            crosswalk_path=crosswalk_path,
            build_crosswalk=build_crosswalk,
        )
        rows = _read_csv(Path(scratch) / "contract_finance_geo_rows.csv")

    awards = [_feature(r, "contract_award") for r in rows if r.get("record_type") == "award"]
    flows = [_feature(r, "financial_flow") for r in rows if r.get("record_type") != "award"]

    _write_geojson(output_dir / CONTRACT_AWARDS, awards)
    _write_geojson(output_dir / FINANCIAL_FLOWS, flows)
    _write_density(output_dir / MUNICIPALITY_DENSITY, _density(rows))

    by_source: dict[str, int] = defaultdict(int)
    for r in rows:
        by_source[r.get("source_dataset") or "unknown"] += 1
    centinelas_rows = [r for r in rows if r.get("source_dataset") == CENTINELAS_SOURCE_ID]
    centinelas_located = sum(1 for r in centinelas_rows if r.get("municipality_code_canonical"))

    report = {
        "producer": PRODUCER,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_mode": geo_summary.get("input_mode"),
        "record_count": len(rows),
        "award_count": len(awards),
        "flow_count": len(flows),
        "by_source_id": dict(sorted(by_source.items())),
        "centinelas_pre_official": {
            "candidate_count": len(centinelas_rows),
            "located_count": centinelas_located,
        },
        "outputs": list(REQUIRED_OUTPUTS),
    }
    (output_dir / INGEST_REPORT).write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--export-dir",
        default=None,
        help="Export-stream dir (funding_awards.jsonl / transactions.jsonl).",
    )
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR))
    parser.add_argument("--crosswalk", default=str(DEFAULT_CROSSWALK))
    parser.add_argument("--build-crosswalk", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_bundle(
        args.output_dir,
        export_dir=args.export_dir,
        processed_dir=args.processed_dir,
        crosswalk_path=args.crosswalk,
        build_crosswalk=args.build_crosswalk,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
