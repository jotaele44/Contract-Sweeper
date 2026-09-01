"""Federation Spatial Core v1: deterministic WGS84 geometry primitives."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

CONTRACT_VERSION = "federation-spatial-contract/1.0"
IDENTITY_DEFAULT = "CANDIDATE_NOT_IDENTITY"
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_B = (1 - WGS84_F) * WGS84_A


def validate_lon_lat(lon: float, lat: float) -> tuple[float, float]:
    lon = float(lon)
    lat = float(lat)
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError("coordinates must be finite")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError(f"invalid WGS84 coordinate: {(lon, lat)}")
    return lon, lat


def _validate_bbox(bbox: Sequence[float]) -> tuple[float, float, float, float]:
    if len(bbox) != 4:
        raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")
    min_lon, min_lat = validate_lon_lat(float(bbox[0]), float(bbox[1]))
    max_lon, max_lat = validate_lon_lat(float(bbox[2]), float(bbox[3]))
    if min_lon > max_lon or min_lat > max_lat:
        raise ValueError("bbox minimums must not exceed maximums")
    return min_lon, min_lat, max_lon, max_lat


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lon1, lat1 = validate_lon_lat(lon1, lat1)
    lon2, lat2 = validate_lon_lat(lon2, lat2)
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371008.8 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))


def geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return ellipsoidal WGS84 distance; fall back for non-convergent pairs."""
    lon1, lat1 = validate_lon_lat(lon1, lat1)
    lon2, lat2 = validate_lon_lat(lon2, lat2)
    if (lon1, lat1) == (lon2, lat2):
        return 0.0

    p1, p2 = map(math.radians, (lat1, lat2))
    u1 = math.atan((1 - WGS84_F) * math.tan(p1))
    u2 = math.atan((1 - WGS84_F) * math.tan(p2))
    longitude_delta = math.radians(lon2 - lon1)
    lam = longitude_delta

    for _ in range(200):
        sin_lam = math.sin(lam)
        cos_lam = math.cos(lam)
        sin_sigma = math.hypot(
            math.cos(u2) * sin_lam,
            math.cos(u1) * math.sin(u2) - math.sin(u1) * math.cos(u2) * cos_lam,
        )
        if sin_sigma == 0:
            return 0.0
        cos_sigma = math.sin(u1) * math.sin(u2) + math.cos(u1) * math.cos(u2) * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = math.cos(u1) * math.cos(u2) * sin_lam / sin_sigma
        cos_sq_alpha = 1 - sin_alpha**2
        cos_2sigma_m = (
            0.0 if cos_sq_alpha == 0 else cos_sigma - 2 * math.sin(u1) * math.sin(u2) / cos_sq_alpha
        )
        c = WGS84_F / 16 * cos_sq_alpha * (4 + WGS84_F * (4 - 3 * cos_sq_alpha))
        next_lam = longitude_delta + (1 - c) * WGS84_F * sin_alpha * (
            sigma + c * sin_sigma * (cos_2sigma_m + c * cos_sigma * (-1 + 2 * cos_2sigma_m**2))
        )
        if abs(next_lam - lam) < 1e-12:
            break
        lam = next_lam
    else:
        return _haversine_m(lon1, lat1, lon2, lat2)

    reduced = cos_sq_alpha * (WGS84_A**2 - WGS84_B**2) / WGS84_B**2
    coef_a = 1 + reduced / 16384 * (4096 + reduced * (-768 + reduced * (320 - 175 * reduced)))
    coef_b = reduced / 1024 * (256 + reduced * (-128 + reduced * (74 - 47 * reduced)))
    delta_sigma = (
        coef_b
        * sin_sigma
        * (
            cos_2sigma_m
            + coef_b
            / 4
            * (
                cos_sigma * (-1 + 2 * cos_2sigma_m**2)
                - coef_b / 6 * cos_2sigma_m * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos_2sigma_m**2)
            )
        )
    )
    return WGS84_B * coef_a * (sigma - delta_sigma)


def point_in_bbox(lon: float, lat: float, bbox: Sequence[float]) -> bool:
    lon, lat = validate_lon_lat(lon, lat)
    min_lon, min_lat, max_lon, max_lat = _validate_bbox(bbox)
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def bbox_distance_m(lon: float, lat: float, bbox: Sequence[float]) -> float:
    lon, lat = validate_lon_lat(lon, lat)
    min_lon, min_lat, max_lon, max_lat = _validate_bbox(bbox)
    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
        return 0.0
    near_lon = min(max(lon, min_lon), max_lon)
    near_lat = min(max(lat, min_lat), max_lat)
    return geodesic_distance_m(lon, lat, near_lon, near_lat)


@dataclass(frozen=True)
class TrackPoint4D:
    lon: float
    lat: float
    altitude_m: float | None = None
    epoch_s: float | None = None

    def __post_init__(self) -> None:
        lon, lat = validate_lon_lat(self.lon, self.lat)
        object.__setattr__(self, "lon", lon)
        object.__setattr__(self, "lat", lat)
        for field in ("altitude_m", "epoch_s"):
            value = getattr(self, field)
            if value is not None:
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(f"{field} must be finite")
                object.__setattr__(self, field, value)


def segment_metrics_4d(a: TrackPoint4D, b: TrackPoint4D) -> dict[str, float | None]:
    horizontal = geodesic_distance_m(a.lon, a.lat, b.lon, b.lat)
    vertical = (
        None
        if a.altitude_m is None or b.altitude_m is None
        else float(b.altitude_m) - float(a.altitude_m)
    )
    distance_3d = math.hypot(horizontal, vertical or 0.0)
    elapsed = (
        None if a.epoch_s is None or b.epoch_s is None else float(b.epoch_s) - float(a.epoch_s)
    )
    if elapsed is not None and elapsed < 0:
        raise ValueError("track time must be non-decreasing")
    speed = None if elapsed in (None, 0.0) else distance_3d / elapsed
    return {
        "horizontal_m": horizontal,
        "vertical_m": vertical,
        "distance_3d_m": distance_3d,
        "elapsed_s": elapsed,
        "speed_mps": speed,
    }
