"""Ingest the DTOP STIP/TIP roadway-project table into RoadWatch project rows.

Reads an operator-dropped STIP/TIP export (a CSV under
``data/manual/stip_tip_projects/``) and emits the RoadWatch project table at
``data/staging/processed/pr_stip_tip_projects.csv`` — the projects input consumed
by ``scripts/build_roadwatch_corridor_join.py`` (joined onto the segment network
by ``route_id`` + km overlap).

CSV-primary ingest (important)
------------------------------
The upstream STIP/TIP tables are distributed as **PDF** (DTOP, e.g. Amendment 5 /
FY2023-26), normally parsed with Tabula/Camelot/pdfplumber. Those tools emit CSV,
so this producer ingests the **operator's PDF->CSV export** rather than parsing the
PDF here: no in-repo STIP PDF sample exists to pin a positional table-column
mapping against, and a blind parser would be guesswork. A PDF-native ``pdfplumber``
branch is a documented follow-up (needs a real sample). Mirrors the sibling
``scripts/ingest_dtop_centerline_lrs.py``.

Join-scoped validation (important)
----------------------------------
``schemas/infrastructure_projects.schema.json`` requires non-empty ``latitude``,
``longitude``, ``start_date`` and ``completion_date``, but a route-corridor STIP
project is a *route + km extent*, not a point asset, and often carries no dates.
Those fields are therefore left **blank when the export lacks them — never
fabricated**. Emission is gated on the identity/join subset this source genuinely
provides (``REQUIRED_FIELDS``); rows missing any of those are held (counted
``held_invalid``, not emitted). Emitted rows are ``infrastructure_projects``-shaped
plus the extra ``route_id``/``km_start``/``km_end`` columns the join keys on
(permitted by the schema's ``additionalProperties: true``).

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

SOURCE_ID = "stip_tip_projects"
DEFAULT_DROP_DIR = "data/manual/stip_tip_projects"
DEFAULT_OUTPUT = "data/staging/processed/pr_stip_tip_projects.csv"
SCHEMA_PATH = "schemas/infrastructure_projects.schema.json"

# Row shape of schemas/infrastructure_projects.schema.json (17 fields, in schema
# order), then the extra join keys the corridor builder reads (allowed by the
# schema's additionalProperties: true).
OUTPUT_COLUMNS = [
    "source_id",
    "source_file",
    "project_id",
    "project_name",
    "asset_type",
    "owner_agency",
    "municipality",
    "status",
    "amount",
    "funding_program",
    "start_date",
    "completion_date",
    "latitude",
    "longitude",
    "raw_text_excerpt",
    "evidence_tier",
    "confidence",
    "route_id",
    "km_start",
    "km_end",
]

# Identity/join fields this source genuinely provides; a row missing any is held
# (held_invalid). Deliberately narrower than the schema's 17 required fields —
# point geometry (latitude/longitude) and dates are excluded because a route-
# corridor project legitimately lacks them (see the module docstring).
REQUIRED_FIELDS = [
    "project_id",
    "project_name",
    "route_id",
    "municipality",
    "funding_program",
    "amount",
    "evidence_tier",
    "confidence",
]


def _uid(prefix: str, *parts: str) -> str:
    """Deterministic id: ``prefix`` + first 16 hex of sha256 over the ``|``-joined
    parts, each stripped and lowercased first, so records differing only in
    capitalization collapse to the same id."""
    key = "|".join(part.strip().lower() for part in parts)
    return f"{prefix}{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def _get(row: dict[str, str], *keys: str) -> str:
    """First non-empty value among ``keys`` (defensive column-name mapping)."""
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _norm_km(km_start: str, km_end: str) -> tuple[str, str]:
    """Return ``(km_start, km_end)`` only if both parse as float with ``end > start``.

    A half-present, reversed, or non-numeric range is a data-quality problem, not a
    genuine measured extent — collapse it to blanks so the row reads as a route-only
    project (the corridor join skips a stated-but-malformed range entirely).
    """
    try:
        if float(km_end) > float(km_start):
            return km_start.strip(), km_end.strip()
    except (TypeError, ValueError):
        pass
    return "", ""


def _resolve_input(explicit: Path | None, root: Path, logger: logging.Logger) -> Path | None:
    """Newest ``*.csv`` in the operator drop dir, or the explicit path if given.

    "Newest" is by modification time (``st_mtime``), with the filename as a
    deterministic tiebreaker.
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


def build_project(row: dict[str, str], source_file: str) -> dict[str, str]:
    """Map one operator STIP/TIP row to an infrastructure_projects row (all strings).

    Point-geometry and date fields are carried from the export when present and left
    blank otherwise — never fabricated (see the module docstring).
    """
    route_id = _get(row, "route_id", "route", "ROUTE_ID")
    project_name = _get(row, "project_name", "name", "title", "PROJECT_NAME")
    km_start, km_end = _norm_km(
        _get(row, "km_start", "from_km", "KM_START"),
        _get(row, "km_end", "to_km", "KM_END"),
    )
    project_id = _get(row, "project_id", "id", "PROJECT_ID") or (
        _uid("stip_", route_id, km_start, km_end, project_name) if route_id else ""
    )
    return {
        "source_id": SOURCE_ID,
        "source_file": source_file,
        "project_id": project_id,
        "project_name": project_name,
        "asset_type": _get(row, "asset_type", "asset") or "roadway",
        "owner_agency": _get(row, "owner_agency", "agency", "owner") or "DTOP",
        "municipality": _get(row, "municipality", "municipio", "MUNICIPALITY"),
        "status": _get(row, "status", "STATUS") or "programmed",
        "amount": _get(row, "amount", "amount_numeric", "amount_raw", "cost", "AMOUNT"),
        "funding_program": _get(row, "funding_program", "program", "fund", "FUNDING_PROGRAM"),
        # Left blank when absent — a route-corridor project is not a point/dated asset.
        "start_date": _get(row, "start_date", "start", "START_DATE"),
        "completion_date": _get(row, "completion_date", "end_date", "COMPLETION_DATE"),
        "latitude": _get(row, "latitude", "lat", "LATITUDE"),
        "longitude": _get(row, "longitude", "lon", "lng", "LONGITUDE"),
        "raw_text_excerpt": _get(row, "raw_text_excerpt", "notes", "raw")
        or (f"{project_name} on {route_id}".strip() if project_name or route_id else ""),
        "evidence_tier": _get(row, "evidence_tier") or "T2_operational_secondary",
        "confidence": _get(row, "confidence") or "0.60",
        "route_id": route_id,
        "km_start": km_start,
        "km_end": km_end,
    }


def build_projects(
    rows: list[dict[str, str]],
    source_file: str,
    schema: dict[str, Any],
    logger: logging.Logger,
) -> tuple[list[dict[str, str]], int]:
    """Return (emitted projects, held_invalid).

    A row missing any REQUIRED_FIELDS value is held_invalid (logged, not emitted).
    ``validate_row`` runs against the full schema to surface any type/format problem
    on the fields present, but does not gate emission on the schema's point-geometry
    / date fields (those are legitimately blank for route-corridor projects).
    """
    emitted: list[dict[str, str]] = []
    held_invalid = 0
    seen: set[str] = set()

    for row in rows:
        proj = build_project(row, source_file)
        missing = [f for f in REQUIRED_FIELDS if not proj[f]]
        if missing:
            held_invalid += 1
            logger.warning(
                "stip_tip_projects: holding project %s (route %s): missing %s",
                proj["project_id"] or "?",
                proj["route_id"] or "?",
                ", ".join(missing),
            )
            continue
        # Surface type/format problems on the fields that are present (empty cells
        # are treated as absent by validate_row, so blank lat/lon/dates do not fail).
        for message in validate_row(proj, schema):
            if message.startswith("missing required field"):
                continue  # gated by REQUIRED_FIELDS above, not the full 17
            logger.warning("stip_tip_projects: project %s: %s", proj["project_id"], message)
        if proj["project_id"] in seen:
            continue
        seen.add(proj["project_id"])
        emitted.append(proj)

    emitted.sort(key=lambda r: (r["route_id"], r["project_id"]))
    return emitted, held_invalid


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def _write_output(out: Path, projects: list[dict[str, str]]) -> None:
    """Write the projects CSV (header always written, even for zero rows)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(projects)


def run(
    root: Path | None = None,
    input_path: Path | None = None,
    output_path: str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("ingest_stip_tip_projects", log_dir=root / "data" / "logs")

    out = root / output_path
    source = _resolve_input(input_path, root, logger)
    if source is None or not source.exists():
        logger.warning("No STIP/TIP export found in %s/%s", root, DEFAULT_DROP_DIR)
        # Clear any stale artifact from a prior run so the downstream join builder
        # never reads projects an absent export no longer backs (header-only file).
        _write_output(out, [])
        return {"status": "EMPTY", "rows": 0, "held_invalid": 0, "output": str(out)}

    # The schema is a committed repo artifact (lives with the code), not a data-root
    # file — resolve it from PROJECT_ROOT so an isolated data ``root`` still validates.
    schema = json.loads((Path(PROJECT_ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))
    projects, held_invalid = build_projects(_read_csv(source), source.name, schema, logger)

    _write_output(out, projects)

    logger.info(
        "roadwatch stip/tip projects: %d emitted, %d held_invalid",
        len(projects),
        held_invalid,
    )
    return {
        "status": "OK" if projects else "EMPTY",
        "rows": len(projects),
        "held_invalid": held_invalid,
        "output": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Operator STIP/TIP CSV.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    print(json.dumps(run(input_path=args.input, output_path=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
