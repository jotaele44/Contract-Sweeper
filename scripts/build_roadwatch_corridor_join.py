"""Build the RoadWatch corridor-join candidate ledger.

Maps STIP/TIP roadway projects onto the RoadWatch roadway-segment network via
route + km-station measures, emitting the derived corridor-join ledger
(``data/staging/processed/roadwatch_corridor_join_candidates.csv``). Each row is
a **manual-review candidate** (``review_status = pending``) until an analyst
accepts it; a valid ``Cell_ID`` on both sides is required before cross-repo
promotion (see docs/ROADWATCH_CORRIDOR_MAPPING.md, docs/SPATIAL_OVERLAY_JOIN_RULES.md).

Inputs (staged CSVs; produced by the upstream RoadWatch producers):
  * segments — ``data/staging/processed/pr_roadwatch_segments.csv``
    (roadwatch_segment rows: segment_uid, route_id, km_start, km_end, Cell_ID, ...)
  * projects — ``data/staging/processed/pr_stip_tip_projects.csv``
    (infrastructure_projects rows: project_id, project_name, route_id, funding, ...)

This builder is pure computation over local files — no network. Modelled on
``scripts/build_legislative_links.py`` (the legislative_fiscal_link_candidates
ledger). It carries the segment's ``Cell_ID`` onto each join row; it does not
resolve geometry itself.

Pause-lock note: writes only the candidate ledger under
``data/staging/processed/``; every row is ``pending`` (materializes no promoted
facts).
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


SOURCE_ID = "roadwatch_corridor_join"
DEFAULT_SEGMENTS = "data/staging/processed/pr_roadwatch_segments.csv"
DEFAULT_PROJECTS = "data/staging/processed/pr_stip_tip_projects.csv"
DEFAULT_OUTPUT = "data/staging/processed/roadwatch_corridor_join_candidates.csv"

# Row shape of schemas/roadwatch_corridor_join.schema.json (staging = all strings).
OUTPUT_COLUMNS = [
    "source_id",
    "source_file",
    "join_id",
    "project_id",
    "project_name",
    "segment_uid",
    "route_id",
    "km_start",
    "km_end",
    "overlap_pct",
    "join_method",
    "geo_reason_code",
    "Cell_ID",
    "municipality",
    "funding_program",
    "amount",
    "evidence_tier",
    "confidence",
    "review_status",
    "raw_text_excerpt",
]

# Minimum segment overlap (%) to keep a route_km_measure candidate
# (docs/ROADWATCH_CORRIDOR_MAPPING.md §5 QA gate).
MIN_OVERLAP_PCT = 20.0


def _uid(prefix: str, *parts: str) -> str:
    """Deterministic id: ``prefix`` + first 16 hex of sha256 over ``|``-joined parts."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:16]}"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            rows.append({key: str(value or "") for key, value in row.items()})
    return rows


def _get(row: dict[str, str], *keys: str) -> str:
    """First non-empty value among ``keys`` (defensive column-name mapping)."""
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _overlap_pct(
    seg_start: float, seg_end: float, prj_start: float, prj_end: float
) -> float | None:
    """Percent of the segment length covered by the project km extent, or None."""
    seg_len = seg_end - seg_start
    if seg_len <= 0:
        return None
    lo, hi = max(seg_start, prj_start), min(seg_end, prj_end)
    covered = max(0.0, hi - lo)
    return 100.0 * covered / seg_len


def _confidence(join_method: str, overlap_pct: float | None) -> str:
    if join_method == "route_km_measure":
        if overlap_pct is not None and overlap_pct >= 60.0:
            return "0.70"
        return "0.50"
    return "0.30"  # route_only_promoted


def build_candidates(
    segments: list[dict[str, str]],
    projects: list[dict[str, str]],
    source_file: str,
) -> list[dict[str, str]]:
    """Join projects onto segments by route_id + km measure; return candidate rows."""
    by_route: dict[str, list[dict[str, str]]] = {}
    for seg in segments:
        route = _get(seg, "route_id")
        if route:
            by_route.setdefault(route, []).append(seg)

    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    for prj in projects:
        route = _get(prj, "route_id")
        if not route or route not in by_route:
            continue
        project_id = _get(prj, "project_id", "id")
        project_name = _get(prj, "project_name", "name", "title")
        p_start_s = _get(prj, "km_start")
        p_end_s = _get(prj, "km_end")
        p_start = float(p_start_s) if p_start_s.replace(".", "", 1).lstrip("-").isdigit() else None
        p_end = float(p_end_s) if p_end_s.replace(".", "", 1).lstrip("-").isdigit() else None
        has_km = p_start is not None and p_end is not None and p_end > p_start

        for seg in by_route[route]:
            segment_uid = _get(seg, "segment_uid")
            cell_id = _get(seg, "Cell_ID", "cell_id")
            if not segment_uid or not cell_id:
                continue  # every row must carry both for a valid, promotable candidate

            if has_km:
                assert p_start is not None and p_end is not None  # guarded by has_km
                s_start_s, s_end_s = _get(seg, "km_start"), _get(seg, "km_end")
                try:
                    pct = _overlap_pct(float(s_start_s), float(s_end_s), p_start, p_end)
                except ValueError:
                    pct = None
                if pct is None or pct < MIN_OVERLAP_PCT:
                    continue
                join_method = "route_km_measure"
                geo_reason_code = "roadwatch_route_km_overlap"
                overlap_pct = f"{pct:.1f}"
                km_start, km_end = p_start_s, p_end_s
            else:
                pct = None
                join_method = "route_only_promoted"
                geo_reason_code = "roadwatch_route_only_no_km"
                overlap_pct = "0"
                km_start, km_end = "", ""

            join_id = _uid("cj_", project_id, segment_uid)
            if join_id in seen:
                continue
            seen.add(join_id)

            candidates.append(
                {
                    "source_id": SOURCE_ID,
                    "source_file": source_file,
                    "join_id": join_id,
                    "project_id": project_id,
                    "project_name": project_name,
                    "segment_uid": segment_uid,
                    "route_id": route,
                    "km_start": km_start,
                    "km_end": km_end,
                    "overlap_pct": overlap_pct,
                    "join_method": join_method,
                    "geo_reason_code": geo_reason_code,
                    "Cell_ID": cell_id,
                    "municipality": _get(seg, "municipality") or _get(prj, "municipality"),
                    "funding_program": _get(prj, "funding_program", "program"),
                    "amount": _get(prj, "amount", "amount_numeric", "amount_raw"),
                    "evidence_tier": _get(prj, "evidence_tier") or "T2_operational_secondary",
                    "confidence": _confidence(join_method, pct),
                    "review_status": "pending",
                    "raw_text_excerpt": _get(prj, "raw_text_excerpt")
                    or f"{project_name} on {route}".strip(),
                }
            )

    candidates.sort(key=lambda r: (r["route_id"], r["project_id"], r["segment_uid"]))
    return candidates


def run(
    root: Path | None = None,
    segments_path: str = DEFAULT_SEGMENTS,
    projects_path: str = DEFAULT_PROJECTS,
    output_path: str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("build_roadwatch_corridor_join", log_dir=root / "data" / "logs")
    segments = _read_csv(root / segments_path)
    projects = _read_csv(root / projects_path)
    candidates = build_candidates(segments, projects, source_file=projects_path)

    out = root / output_path
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(candidates)

    logger.info(
        "roadwatch corridor join candidates: %d rows (%d segments x %d projects)",
        len(candidates),
        len(segments),
        len(projects),
    )
    return {
        "status": "OK" if candidates else "EMPTY",
        "rows": len(candidates),
        "output": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", default=DEFAULT_SEGMENTS)
    parser.add_argument("--projects", default=DEFAULT_PROJECTS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run(segments_path=args.segments, projects_path=args.projects, output_path=args.output),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
