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
are **held** (counted ``held_unresolved``, not emitted) until the upstream spatial
join is computed. A non-empty ``Cell_ID`` that is not a member of the committed
baseline grid is treated as an operator typo and **held** (``held_unknown_cell``)
rather than emitted — otherwise the bad id would reach the corridor ledger and
corrupt its spatial attribution.

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
GRID_PATH = "registry/spatial/pr_grid_full_cell_index_saturated.csv"

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
    """Deterministic id per docs/ROADWATCH_CORRIDOR_MAPPING.md §4.

    ``prefix`` + first 16 hex of sha256 over the ``|``-joined parts, each part
    stripped and lowercased first (the documented convention) so that records
    differing only in capitalization (``PR-52`` vs ``pr-52``, ``both`` vs
    ``BOTH``) hash to the same id and dedup correctly.
    """
    key = "|".join(part.strip().lower() for part in parts)
    return f"{prefix}{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


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
    """Newest ``*.csv`` in the operator drop dir, or the explicit path if given.

    "Newest" is by modification time (``st_mtime``), with the filename as a
    deterministic tiebreaker — sorting lexicographically by name would ingest a
    stale ``z_export.csv`` over a freshly dropped ``a_export.csv``.
    """
    if explicit is not None:
        return explicit
    drop = root / DEFAULT_DROP_DIR
    if not drop.exists():
        return None
    csvs = [p for p in drop.iterdir() if p.suffix.lower() == ".csv"]
    if not csvs:
        return None
    csvs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    if len(csvs) > 1:
        logger.warning("Multiple CSVs in %s; using newest by mtime: %s", drop, csvs[0].name)
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
    valid_cells: set[str],
    logger: logging.Logger,
) -> tuple[list[dict[str, str]], int, int, int]:
    """Return (emitted segments, held_unresolved, held_invalid, held_unknown_cell).

    A row missing only ``Cell_ID`` is *held_unresolved* (the documented staging
    state — awaiting the upstream spatial join). A row carrying a non-empty
    ``Cell_ID`` that is not a member of the committed baseline grid is
    *held_unknown_cell* (an operator typo — emitting it would corrupt the
    corridor ledger's spatial attribution). A row that fails schema validation
    for any other reason is *held_invalid*. All held rows are logged, never
    emitted.
    """
    emitted: list[dict[str, str]] = []
    held_unresolved = 0
    held_invalid = 0
    held_unknown_cell = 0
    seen: set[str] = set()

    for row in rows:
        seg = build_segment(row, source_file)
        cell = seg["Cell_ID"]
        if not cell:
            held_unresolved += 1
            continue
        if valid_cells and cell not in valid_cells:
            held_unknown_cell += 1
            logger.warning(
                "dtop_centerline_lrs: Cell_ID %r (route %s) is not in the baseline "
                "grid; holding segment",
                cell,
                seg["route_id"] or "?",
            )
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
    return emitted, held_unresolved, held_invalid, held_unknown_cell


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def _load_valid_cells() -> set[str]:
    """Cell_IDs present in the committed PR baseline grid.

    The grid is a committed repo artifact (``registry/spatial/``), so it is
    resolved from PROJECT_ROOT like the schema. Returns an empty set if the grid
    is absent (a broken checkout) — membership validation is then skipped rather
    than holding every row.
    """
    path = Path(PROJECT_ROOT) / GRID_PATH
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {(row.get("Cell_ID") or "").strip() for row in csv.DictReader(handle)}


def _write_output(out: Path, segments: list[dict[str, str]]) -> None:
    """Write the segment CSV (header always written, even for zero rows)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(segments)


def run(
    root: Path | None = None,
    input_path: Path | None = None,
    output_path: str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("ingest_dtop_centerline_lrs", log_dir=root / "data" / "logs")

    out = root / output_path
    source = _resolve_input(input_path, root, logger)
    if source is None or not source.exists():
        logger.warning("No DTOP centerline export found in %s/%s", root, DEFAULT_DROP_DIR)
        # Clear any stale artifact from a prior run so the downstream join builder
        # never reads segments an absent export no longer backs (header-only file).
        _write_output(out, [])
        return {
            "status": "EMPTY",
            "rows": 0,
            "held_unresolved": 0,
            "held_invalid": 0,
            "held_unknown_cell": 0,
            "output": str(out),
        }

    # The schema and baseline grid are committed repo artifacts (they live with
    # the code), not data-root files — resolve them from PROJECT_ROOT so an
    # isolated data ``root`` (e.g. a test tmp dir) still validates.
    schema = json.loads((Path(PROJECT_ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))
    valid_cells = _load_valid_cells()
    segments, held_unresolved, held_invalid, held_unknown_cell = build_segments(
        _read_csv(source), source.name, schema, valid_cells, logger
    )

    _write_output(out, segments)

    logger.info(
        "roadwatch segments: %d emitted, %d held_unresolved (no Cell_ID), "
        "%d held_unknown_cell, %d held_invalid",
        len(segments),
        held_unresolved,
        held_unknown_cell,
        held_invalid,
    )
    return {
        "status": "OK" if segments else "EMPTY",
        "rows": len(segments),
        "held_unresolved": held_unresolved,
        "held_invalid": held_invalid,
        "held_unknown_cell": held_unknown_cell,
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
