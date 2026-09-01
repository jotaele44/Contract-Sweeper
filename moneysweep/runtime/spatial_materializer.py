"""Evidence-safe MoneySweep -> Federation Spatial Feature materialization.

This module intentionally DOES NOT geocode.  It only promotes coordinates that
are already present in source/enriched rows. Municipality-only records remain
non-geometric until an auditable geocoder/parcel source binds them. This closes
the code path for project/asset/flow geometry without fabricating coordinates.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from federation.spatial_core import (
    CONTRACT_VERSION,
    IDENTITY_DEFAULT,
    canonical_json_sha256,
    validate_lon_lat,
)


def _finite(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _confidence(row: Mapping[str, Any]) -> str:
    for key in ("coordinate_confidence", "geo_coordinate_confidence"):
        value = str(row.get(key) or "").upper()
        if value in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}:
            return value
    return "UNKNOWN"


def _combined_confidence(*values: str) -> str:
    rank = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
    return min(values, key=rank.__getitem__)


def point_feature(
    row: Mapping[str, Any],
    *,
    feature_id: str,
    feature_class: str,
    source_id: str,
    domain: str = "capital",
) -> dict | None:
    lat = _finite(row.get("geo_lat", row.get("lat", row.get("latitude"))))
    lon = _finite(row.get("geo_lon", row.get("lon", row.get("longitude"))))
    if lat is None or lon is None:
        return None
    lon, lat = validate_lon_lat(lon, lat)
    manifestation = canonical_json_sha256(dict(row))
    logical = {
        "feature_id": feature_id,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "feature_class": feature_class,
        "domain": domain,
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "feature_id": feature_id,
        "producer_repo": "moneysweep-pr",
        "domain": domain,
        "feature_class": feature_class,
        "geometry": logical["geometry"],
        "bbox": [lon, lat, lon, lat],
        "crs": "OGC:CRS84",
        "altitude": None,
        "valid_time": None,
        "properties": dict(row),
        "geometry_source": source_id,
        "coordinate_method": "SOURCE_REPORTED",
        "coordinate_confidence": _confidence(row),
        "logical_sha256": canonical_json_sha256(logical),
        "source_manifestation_sha256": manifestation,
        "provenance": [{"source_id": source_id, "sha256": manifestation}],
        "evidence_state": "FACT",
        "review_state": "UNREVIEWED",
        "identity_semantics": IDENTITY_DEFAULT,
    }


def flow_feature(
    origin: Mapping[str, Any],
    destination: Mapping[str, Any],
    *,
    feature_id: str,
    source_id: str,
    properties: Mapping[str, Any] | None = None,
) -> dict | None:
    a = point_feature(
        origin,
        feature_id=f"{feature_id}:origin",
        feature_class="flow_endpoint",
        source_id=source_id,
    )
    b = point_feature(
        destination,
        feature_id=f"{feature_id}:destination",
        feature_class="flow_endpoint",
        source_id=source_id,
    )
    if not a or not b:
        return None
    ca, cb = a["geometry"]["coordinates"], b["geometry"]["coordinates"]
    logical = {
        "feature_id": feature_id,
        "geometry": {"type": "LineString", "coordinates": [ca, cb]},
        "feature_class": "contract_flow",
        "domain": "capital",
    }
    manifestation = canonical_json_sha256(
        {
            "origin": dict(origin),
            "destination": dict(destination),
            "properties": dict(properties or {}),
        }
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "feature_id": feature_id,
        "producer_repo": "moneysweep-pr",
        "domain": "capital",
        "feature_class": "contract_flow",
        "geometry": logical["geometry"],
        "bbox": [min(ca[0], cb[0]), min(ca[1], cb[1]), max(ca[0], cb[0]), max(ca[1], cb[1])],
        "crs": "OGC:CRS84",
        "altitude": None,
        "valid_time": None,
        "properties": dict(properties or {}),
        "geometry_source": source_id,
        "coordinate_method": "SOURCE_REPORTED",
        "coordinate_confidence": _combined_confidence(
            a["coordinate_confidence"], b["coordinate_confidence"]
        ),
        "logical_sha256": canonical_json_sha256(logical),
        "source_manifestation_sha256": manifestation,
        "provenance": [{"source_id": source_id, "sha256": manifestation}],
        "evidence_state": "COMPUTED",
        "review_state": "UNREVIEWED",
        "identity_semantics": IDENTITY_DEFAULT,
    }
