"""Ingest FHWA National Bridge Inventory (NBI) structures for Puerto Rico.

Live-fetches the FHWA NBI delimited file and emits roadwatch_segment-shaped
reference rows at ``data/staging/processed/pr_nbi_bridges.csv``. NBI supplies
**point structures** (a route + a single milepost/measure + lat/long) that anchor
bridge-scoped projects to the nearest RoadWatch segment (future join_method
``nbi_structure_point``). Role ``roadwatch_structure_reference``; the current
corridor-join builder does not yet consume this table — it stands alone.

Config bindings (operator-confirmed; important)
-----------------------------------------------
The exact per-state NBI **file URL** and its **column names** vary by publication
year and cannot be verified from this environment (no network), so ``NBI_URL`` and
the ``normalize`` field mapping are documented, operator-confirmable defaults — not
fabricated live schemas. The delimited fetch + PR filter + point->segment encoding
below are real and exercised by the mocked-HTTP tests.

Point -> zero-length segment encoding
-------------------------------------
A bridge is a point, but the output schema is roadwatch_segment (a km-stationed
slice), so each structure is encoded as a zero-length segment: ``km_start == km_end``
= the structure milepost, ``length_km = "0"``, ``geometry_ref`` = the NBI structure
number. Latitude/longitude are carried as extra columns (allowed by the schema's
``additionalProperties: true``) for the future ``nbi_structure_point`` snap.

Cell_ID boundary (important)
----------------------------
``roadwatch_segment.schema.json`` requires a non-empty ``Cell_ID`` and this repo has
no coordinate->Cell_ID resolver, so rows without a resolved cell are **held**
(counted ``held_unresolved``, not emitted). A raw NBI file carries no Cell_ID, so
this producer is inert on emission until an upstream spatial join runs.

No local files consumed; live egress only (returns EMPTY with no network).
``run(root)->dict`` + ``main(argv)->int``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import sys
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

SOURCE_ID = "fhwa_nbi_bridges"
USER_AGENT = "ContractSweeper/1.0 (PR federal spending research)"
# The exact per-state/year NBI file URL is operator-confirmed (see docstring); the
# overlay endpoint_url (https://www.fhwa.dot.gov/bridge/nbi.cfm) is the landing page.
NBI_URL = "https://www.fhwa.dot.gov/bridge/nbi/2024/delimited/PR24.txt"
HTTP_TIMEOUT = 60
DEFAULT_CRS = "EPSG:4326"
DEFAULT_OUTPUT = "data/staging/processed/pr_nbi_bridges.csv"
SCHEMA_PATH = "schemas/roadwatch_segment.schema.json"

# Row shape of schemas/roadwatch_segment.schema.json, then lat/long extras (allowed
# by additionalProperties: true) for the future nbi_structure_point snap.
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
    "latitude",
    "longitude",
]


def _session() -> requests.Session:
    """Session factory — the seam mocked in tests."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/plain"})
    return s


def _fetch_text(session: requests.Session, logger: logging.Logger) -> str | None:
    """GET the NBI delimited file body, or ``None`` on any failure (no network)."""
    try:
        resp = session.get(NBI_URL, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("fhwa_nbi_bridges: fetch failed: %s", exc)
        return None


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
    """Keep only Puerto Rico structures (NBI state code 72)."""
    state = _get(row, "STATE_CODE_001", "state_code", "STATE", "state")
    return state in ("72", "072", "72.0") or state.upper() in ("PR", "PUERTO RICO")


def _parse_delimited(text: str) -> list[dict[str, str]]:
    """Parse the NBI delimited body into raw dict rows."""
    return [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(io.StringIO(text))]


def normalize(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Map raw NBI records to intermediate roadwatch rows, PR-filtered.

    Field names follow the documented, operator-confirmable NBI item mapping; ``_get``
    accepts common aliases so a confirmed year variant does not silently drop data.
    """
    rows: list[dict[str, str]] = []
    for record in records:
        if not _is_pr(record):
            continue
        milepost = _get(record, "KILOPOINT_011", "milepost", "km", "measure")
        rows.append(
            {
                "route_id": _get(record, "ROUTE_NUMBER_005D", "route_id", "route", "ROUTE"),
                "milepost": milepost,
                "municipality": _get(record, "COUNTY_CODE_003", "municipality", "county"),
                "geometry_ref": _get(
                    record, "STRUCTURE_NUMBER_008", "structure_number", "structure_id"
                ),
                "latitude": _get(record, "LAT_016", "latitude", "lat"),
                "longitude": _get(record, "LONG_017", "longitude", "long", "lon"),
                # A raw NBI file has no Cell_ID; carried only if present (else held).
                "Cell_ID": _get(record, "Cell_ID", "cell_id"),
            }
        )
    return rows


def build_segment(row: dict[str, str]) -> dict[str, str]:
    """Map one normalized NBI structure to a zero-length roadwatch_segment row."""
    route_id = row.get("route_id", "")
    milepost = row.get("milepost", "")
    direction = "unknown"
    return {
        "source_id": SOURCE_ID,
        "source_file": NBI_URL,
        "segment_uid": _uid("seg_", route_id, milepost, milepost, direction),
        "route_id": route_id,
        "route_class": "unknown",
        "direction": direction,
        "km_start": milepost,
        "km_end": milepost,  # point structure -> zero-length segment
        "length_km": "0",
        "municipality": row.get("municipality", ""),
        "Cell_ID": row.get("Cell_ID", ""),
        "geometry_ref": row.get("geometry_ref", "")
        or (f"nbi:{route_id}:{milepost}" if route_id else ""),
        "crs": DEFAULT_CRS,
        "raw_text_excerpt": (
            f"NBI structure {row.get('geometry_ref', '')} on {route_id} km {milepost}".strip()
            if route_id
            else ""
        ),
        "evidence_tier": "T2_operational_secondary",
        "confidence": "0.55",
        "latitude": row.get("latitude", ""),
        "longitude": row.get("longitude", ""),
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
                "fhwa_nbi_bridges: dropping structure %s (route %s): %s",
                seg["geometry_ref"] or "?",
                seg["route_id"] or "?",
                errors[0],
            )
            continue
        if seg["segment_uid"] in seen:
            continue
        seen.add(seg["segment_uid"])
        emitted.append(seg)

    emitted.sort(key=lambda r: (r["route_id"], r["km_start"], r["geometry_ref"]))
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
    logger = setup_logging("ingest_fhwa_nbi_bridges", log_dir=root / "data" / "logs")
    out = root / output_path

    text = _fetch_text(_session(), logger)
    if not text:
        logger.warning("fhwa_nbi_bridges: no data fetched (no network or empty response)")
        _write_output(out, [])
        return {"status": "EMPTY", "rows": 0, "held_unresolved": 0, "output": str(out)}

    schema = json.loads((Path(PROJECT_ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))
    rows = normalize(_parse_delimited(text))
    segments, held_unresolved, held_invalid = build_segments(rows, schema, logger)

    _write_output(out, segments)
    logger.info(
        "fhwa_nbi_bridges: %d emitted, %d held_unresolved (no Cell_ID), %d held_invalid",
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
