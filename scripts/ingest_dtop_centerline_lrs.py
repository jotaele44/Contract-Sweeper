"""Ingest the DTOP/ACT roadway centerline LRS into RoadWatch segment rows.

Reads an operator-dropped DTOP/ACT centerline export (a CSV under
``data/manual/dtop_centerline_lrs/``) and emits the RoadWatch roadway-segment
network at ``data/staging/processed/pr_roadwatch_segments.csv`` — the exact input
consumed by ``scripts/build_roadwatch_corridor_join.py``.

Cell_ID boundary (important)
----------------------------
``roadwatch_segment.schema.json`` requires a non-empty ``Cell_ID``, but this repo
has **no coordinate->Cell_ID resolver** and the PR baseline grid
(``registry/spatial/pr_grid_full_cell_index_saturated.csv``) is a pixel raster
with no CRS/geotransform, so a real-world roadway location cannot be resolved to a
cell in-repo. Per the design (``docs/ROADWATCH_CORRIDOR_MAPPING.md`` §5/§8,
``docs/SPATIAL_OVERLAY_JOIN_RULES.md``: "records with coordinates but no resolved
cell remain in staging"), cell resolution is an operator/GIS step. This producer
therefore **carries ``Cell_ID`` through from the operator export**: rows that
already carry a resolved ``Cell_ID`` (and validate) are emitted; rows without one
are **held** (counted, not emitted) until the upstream spatial join is computed.

Pure computation over local files — no network. ``run(root)->dict`` +
``main(argv)->int``, mirroring ``scripts/build_legislative_links.py``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from scripts.config import PROJECT_ROOT, setup_logging
except Exception:  # pragma: no cover
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

    def setup_logging(log_name: str, log_dir: Path | None = None) -> logging.Logger:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
        return logging.getLogger(log_name)


from moneysweep.validation.canonical_v1_schema import validate_row  # noqa: E402

SOURCE_ID = "dtop_centerline_lrs"
DEFAULT_DROP_DIR = "data/manual/dtop_centerline_lrs"
DEFAULT_OUTPUT = "data/staging/processed/pr_roadwatch_segments.csv"
SCHEMA_PATH = "schemas/roadwatch_segment.schema.json"

# Row shape of schemas/roadwatch_segment.schema.json (staging = all strings).
OUTPUT_COLUMNS = [
    "source_id",
    "source_file",
    "segment_uid",
    "route_id",
    "route_class",
    "direction",
    "km_start",
    "km_end",
    "length_km",
    "municipality",
    "Cell_ID",
    "geometry_ref",
    "crs",
    "raw_text_excerpt",
    "evidence_tier",
    "confidence",
]

DEFAULT_CRS = "EPSG:32161"  # NAD83 PR/VI, the LRS's common CRS (overlay note)


def _uid(prefix: str, *parts: str) -> str:
    """Deterministic id: ``prefix`` + first 16 hex of sha256 over ``|``-joined parts."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:16]}"


def _get(row: dict[str, str], *keys: str) -> str:
    """First non-empty value among ``keys`` (defensive column-name mapping)."""
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _length_km(km_start: str, km_end: str) -> str:
    try:
        return f"{float(km_end) - float(km_start):g}"
    except (TypeError, ValueError):
        return ""


def _resolve_input(explicit: Path | None, root: Path, logger: logging.Logger) -> Path | None:
    """Newest ``*.csv`` in the operator drop dir, or the explicit path if given."""
    if explicit is not None:
        return explicit
    drop = root / DEFAULT_DROP_DIR
    if not drop.exists():
        return None
    csvs = sorted((p for p in drop.iterdir() if p.suffix.lower() == ".csv"), reverse=True)
    if not csvs:
        return None
    if len(csvs) > 1:
        logger.warning("Multiple CSVs in %s; using %s", drop, csvs[0].name)
    return csvs[0]


def build_segment(row: dict[str, str], source_file: str) -> dict[str, str]:
    """Map one operator centerline row to a roadwatch_segment row (all strings)."""
    route_id = _get(row, "route_id", "route", "ROUTE_ID")
    km_start = _get(row, "km_start", "from_km", "KM_START")
    km_end = _get(row, "km_end", "to_km", "KM_END")
    direction = _get(row, "direction", "DIRECTION") or "unknown"
    return {
        "source_id": SOURCE_ID,
        "source_file": source_file,
        "segment_uid": _uid("seg_", route_id, km_start, km_end, direction),
        "route_id": route_id,
        "route_class": _get(row, "route_class", "class", "ROUTE_CLASS") or "unknown",
        "direction": direction,
        "km_start": km_start,
        "km_end": km_end,
        "length_km": _get(row, "length_km") or _length_km(km_start, km_end),
        "municipality": _get(row, "municipality", "municipio", "MUNICIPALITY"),
        # Carried from the operator export; see the module docstring's Cell_ID boundary.
        "Cell_ID": _get(row, "Cell_ID", "cell_id", "CELL_ID"),
        "geometry_ref": _get(row, "geometry_ref", "geom_ref")
        or (f"dtop_centerline_lrs:{route_id}:{km_start}-{km_end}" if route_id else ""),
        "crs": _get(row, "crs", "CRS") or DEFAULT_CRS,
        "raw_text_excerpt": _get(row, "raw_text_excerpt", "notes", "raw")
        or (f"{route_id} km {km_start}-{km_end}".strip() if route_id else ""),
        "evidence_tier": _get(row, "evidence_tier") or "T2_operational_secondary",
        "confidence": _get(row, "confidence") or "0.60",
    }


def build_segments(
    rows: list[dict[str, str]],
    source_file: str,
    schema: dict[str, Any],
    logger: logging.Logger,
) -> tuple[list[dict[str, str]], int, int]:
    """Return (emitted segments, held_unresolved, held_invalid).

    A row missing only ``Cell_ID`` is *held_unresolved* (the documented
    staging state — awaiting the upstream spatial join). A row that fails
    validation for any other reason is *held_invalid* and logged.
    """
    emitted: list[dict[str, str]] = []
    held_unresolved = 0
    held_invalid = 0
    seen: set[str] = set()

    for row in rows:
        seg = build_segment(row, source_file)
        if not seg["Cell_ID"]:
            held_unresolved += 1
            continue
        errors = validate_row(seg, schema)
        if errors:
            held_invalid += 1
            logger.warning(
                "dtop_centerline_lrs: dropping segment %s (route %s): %s",
                seg["segment_uid"],
                seg["route_id"] or "?",
                errors[0],
            )
            continue
        if seg["segment_uid"] in seen:
            continue
        seen.add(seg["segment_uid"])
        emitted.append(seg)

    emitted.sort(key=lambda r: (r["route_id"], r["km_start"], r["km_end"]))
    return emitted, held_unresolved, held_invalid


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def run(
    root: Path | None = None,
    input_path: Path | None = None,
    output_path: str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("ingest_dtop_centerline_lrs", log_dir=root / "data" / "logs")

    source = _resolve_input(input_path, root, logger)
    if source is None or not source.exists():
        logger.warning("No DTOP centerline export found in %s/%s", root, DEFAULT_DROP_DIR)
        return {"status": "EMPTY", "rows": 0, "held_unresolved": 0, "held_invalid": 0}

    # The schema is a committed repo artifact (lives with the code), not a
    # data-root file — resolve it from PROJECT_ROOT so an isolated data ``root``
    # (e.g. a test tmp dir) still validates.
    schema = json.loads((Path(PROJECT_ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))
    segments, held_unresolved, held_invalid = build_segments(
        _read_csv(source), source.name, schema, logger
    )

    out = root / output_path
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(segments)

    logger.info(
        "roadwatch segments: %d emitted, %d held_unresolved (no Cell_ID), %d held_invalid",
        len(segments),
        held_unresolved,
        held_invalid,
    )
    return {
        "status": "OK" if segments else "EMPTY",
        "rows": len(segments),
        "held_unresolved": held_unresolved,
        "held_invalid": held_invalid,
        "output": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Operator centerline CSV.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    print(json.dumps(run(input_path=args.input, output_path=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
