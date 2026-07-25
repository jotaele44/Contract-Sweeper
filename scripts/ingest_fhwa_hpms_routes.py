"""Ingest FHWA HPMS route geometry for Puerto Rico into RoadWatch segment rows.

Live-fetches the FHWA Highway Performance Monitoring System (HPMS) route network
from the FHWA ArcGIS REST service and emits roadwatch_segment-shaped reference rows
at ``data/staging/processed/pr_hpms_routes.csv``. HPMS is a **secondary route
geometry authority** (role ``roadwatch_route_reference``): its ``route_id`` +
stationing cross-check the DTOP centerline LRS. The current corridor-join builder
does not yet consume this table — it stands alone until a future PR folds HPMS into
segment-building.

Config bindings (operator-confirmed; important)
-----------------------------------------------
The exact PR HPMS ArcGIS **layer path** under the service root and its **field
names** cannot be verified from this environment (no network), so ``LAYER_QUERY_URL``
and the ``normalize`` field mapping are documented, operator-confirmable defaults —
not fabricated live schemas. The ArcGIS ``resultOffset``/``exceededTransferLimit``
pagination mechanic below is real and exercised by the mocked-HTTP tests; the
operator confirms the layer id + ``outFields`` against the live service.

Cell_ID boundary (important)
----------------------------
``roadwatch_segment.schema.json`` requires a non-empty ``Cell_ID``, but this repo has
no coordinate->Cell_ID resolver (see ``scripts/ingest_dtop_centerline_lrs.py``). Rows
without a resolved ``Cell_ID`` are **held** (counted ``held_unresolved``, not emitted)
per the documented staging rule. A raw HPMS response carries no Cell_ID, so this
producer is inert on emission until an upstream spatial join runs — the fetch/parse
mechanics and the hold boundary are what ship here.

No local files consumed; live egress only (returns EMPTY with no network).
``run(root)->dict`` + ``main(argv)->int``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from scripts.config import PROJECT_ROOT, setup_logging
except Exception:  # pragma: no cover
    PROJECT_ROOT = Path(__file__).resolve().parents[1]

    def setup_logging(log_name: str, log_dir: Path | None = None) -> logging.Logger:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
        return logging.getLogger(log_name)


from moneysweep.validation.canonical_v1_schema import validate_row  # noqa: E402

SOURCE_ID = "fhwa_hpms_routes"
USER_AGENT = "ContractSweeper/1.0 (PR federal spending research)"
# Service root from the overlay endpoint_url. The exact PR HPMS FeatureServer layer
# path + outFields are operator-confirmed against the live service (see docstring).
SERVICE_ROOT = "https://geo.dot.gov/server/rest/services/Hosted"
LAYER_QUERY_URL = f"{SERVICE_ROOT}/HPMS_Full_PR/FeatureServer/0/query"
# Puerto Rico state FIPS is 72; HPMS carries it in state_code (server-side filter).
PR_WHERE = "state_code = 72"
PAGE_SIZE = 1000
DEFAULT_CRS = "EPSG:4326"
DEFAULT_OUTPUT = "data/staging/processed/pr_hpms_routes.csv"
SCHEMA_PATH = "schemas/roadwatch_segment.schema.json"

HTTP_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = (2.0, 4.0, 8.0)

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


def _sleep(seconds: float) -> None:
    """Sleep seam so tests can neutralize retry/rate-limit backoff."""
    time.sleep(seconds)


def _session() -> requests.Session:
    """Session factory — the seam mocked in tests."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def _fetch_page(session: requests.Session, params: dict, logger: logging.Logger) -> dict | None:
    """GET one ArcGIS page as JSON, with retry; ``None`` on 4xx / exhaustion."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(LAYER_QUERY_URL, params=params, timeout=HTTP_TIMEOUT)
            if resp.status_code == 429:
                logger.warning("  Rate limited — sleeping 60s")
                _sleep(60)
                continue
            if 400 <= resp.status_code < 500:
                logger.warning("  HTTP %s for %s", resp.status_code, LAYER_QUERY_URL)
                return None
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt < MAX_RETRIES - 1:
                _sleep(RETRY_BACKOFF[attempt])
            else:
                logger.warning("  All %d attempts failed: %s", MAX_RETRIES, exc)
    return None


def _fetch_all(session: requests.Session, logger: logging.Logger) -> list[dict[str, str]] | None:
    """Page the ArcGIS layer via resultOffset until exceededTransferLimit clears.

    Returns the list of raw ``attributes`` dicts, or ``None`` if a page fetch fails
    (no network / API error) — the caller treats ``None`` as EMPTY.
    """
    records: list[dict[str, str]] = []
    offset = 0
    while True:
        params = {
            "f": "json",
            "where": PR_WHERE,
            "outFields": "*",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "returnGeometry": "false",
        }
        data = _fetch_page(session, params, logger)
        if data is None:
            return None
        features = data.get("features", [])
        records.extend({k: str(v) for k, v in f.get("attributes", {}).items()} for f in features)
        if not features or not data.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE
    return records


def _uid(prefix: str, *parts: str) -> str:
    """Deterministic id: ``prefix`` + first 16 hex of sha256 over the ``|``-joined
    parts, each stripped and lowercased first (case-normalized dedup)."""
    key = "|".join(part.strip().lower() for part in parts)
    return f"{prefix}{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def _get(row: dict[str, str], *keys: str) -> str:
    """First non-empty value among ``keys`` (defensive column-name mapping)."""
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "None"):
            return str(value).strip()
    return ""


def _is_pr(row: dict[str, str]) -> bool:
    """Keep only Puerto Rico rows (state FIPS 72)."""
    state = _get(row, "state_code", "STATE_CODE", "state", "STATE")
    return state in ("72", "72.0") or state.upper() in ("PR", "PUERTO RICO")


def normalize(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Map raw HPMS attributes to intermediate roadwatch rows, PR-filtered.

    Field names follow the documented, operator-confirmable HPMS mapping (see the
    module docstring); ``_get`` accepts common aliases so a confirmed schema variant
    does not silently drop data.
    """
    rows: list[dict[str, str]] = []
    for record in records:
        if not _is_pr(record):
            continue
        route_id = _get(record, "route_id", "ROUTE_ID", "route", "route_number")
        km_start = _get(record, "begin_point", "bmp", "BEGIN_POINT", "km_start")
        km_end = _get(record, "end_point", "emp", "END_POINT", "km_end")
        rows.append(
            {
                "route_id": route_id,
                "km_start": km_start,
                "km_end": km_end,
                "route_class": _get(record, "route_class", "f_system", "functional_class"),
                "direction": _get(record, "direction", "DIRECTION"),
                "municipality": _get(record, "municipality", "county_name", "municipio"),
                "geometry_ref": _get(record, "objectid", "OBJECTID", "route_id") or route_id,
                # A raw HPMS response has no Cell_ID; carried only if a spatial-join
                # column is present (normally absent -> the row is held downstream).
                "Cell_ID": _get(record, "Cell_ID", "cell_id"),
            }
        )
    return rows


def _length_km(km_start: str, km_end: str) -> str:
    try:
        return f"{float(km_end) - float(km_start):g}"
    except (TypeError, ValueError):
        return ""


def build_segment(row: dict[str, str]) -> dict[str, str]:
    """Map one normalized HPMS row to a roadwatch_segment row (all strings)."""
    route_id = row.get("route_id", "")
    km_start = row.get("km_start", "")
    km_end = row.get("km_end", "")
    direction = row.get("direction", "") or "unknown"
    return {
        "source_id": SOURCE_ID,
        "source_file": LAYER_QUERY_URL,
        "segment_uid": _uid("seg_", route_id, km_start, km_end, direction),
        "route_id": route_id,
        "route_class": row.get("route_class", "") or "unknown",
        "direction": direction,
        "km_start": km_start,
        "km_end": km_end,
        "length_km": _length_km(km_start, km_end),
        "municipality": row.get("municipality", ""),
        "Cell_ID": row.get("Cell_ID", ""),
        "geometry_ref": row.get("geometry_ref", "")
        or (f"hpms:{route_id}:{km_start}-{km_end}" if route_id else ""),
        "crs": DEFAULT_CRS,
        "raw_text_excerpt": (f"HPMS {route_id} km {km_start}-{km_end}".strip() if route_id else ""),
        "evidence_tier": "T2_operational_secondary",
        "confidence": "0.55",
    }


def build_segments(
    rows: list[dict[str, str]],
    schema: dict[str, Any],
    logger: logging.Logger,
) -> tuple[list[dict[str, str]], int, int]:
    """Return (emitted segments, held_unresolved, held_invalid), DTOP-style hold."""
    emitted: list[dict[str, str]] = []
    held_unresolved = 0
    held_invalid = 0
    seen: set[str] = set()

    for row in rows:
        seg = build_segment(row)
        if not seg["Cell_ID"]:
            held_unresolved += 1
            continue
        errors = validate_row(seg, schema)
        if errors:
            held_invalid += 1
            logger.warning(
                "fhwa_hpms_routes: dropping segment %s (route %s): %s",
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


def _write_output(out: Path, segments: list[dict[str, str]]) -> None:
    """Write the segment CSV (header always written, even for zero rows)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(segments)


def run(root: Path | None = None, output_path: str = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("ingest_fhwa_hpms_routes", log_dir=root / "data" / "logs")
    out = root / output_path

    records = _fetch_all(_session(), logger)
    if not records:
        logger.warning("fhwa_hpms_routes: no records fetched (no network or empty response)")
        _write_output(out, [])
        return {"status": "EMPTY", "rows": 0, "held_unresolved": 0, "output": str(out)}

    schema = json.loads((Path(PROJECT_ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))
    segments, held_unresolved, held_invalid = build_segments(normalize(records), schema, logger)

    _write_output(out, segments)
    logger.info(
        "fhwa_hpms_routes: %d emitted, %d held_unresolved (no Cell_ID), %d held_invalid",
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
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    print(json.dumps(run(output_path=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
