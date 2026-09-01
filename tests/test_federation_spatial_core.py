import math

import pytest

from federation.spatial_core import (
    TrackPoint4D,
    bbox_distance_m,
    canonical_json_sha256,
    geodesic_distance_m,
    point_in_bbox,
    segment_metrics_4d,
)


def test_geodesic_pr_scale():
    distance = geodesic_distance_m(-66.0, 18.0, -66.0, 19.0)
    assert 110_000 < distance < 112_000


def test_geodesic_coincident_and_near_antipodal_pairs_are_finite():
    assert geodesic_distance_m(-66.0, 18.0, -66.0, 18.0) == 0.0
    distance = geodesic_distance_m(0.0, 0.0, 179.9999, 0.0)
    assert math.isfinite(distance)
    assert 20_000_000 < distance < 20_020_000


def test_bbox_distance_and_membership():
    box = (-67.0, 18.0, -66.0, 19.0)
    assert point_in_bbox(-66.5, 18.5, box)
    assert bbox_distance_m(-66.5, 18.5, box) == 0
    assert bbox_distance_m(-65.5, 18.5, box) > 50_000


@pytest.mark.parametrize(
    ("lon", "lat"),
    [(181.0, 18.0), (-66.0, 91.0), (math.nan, 18.0), (-66.0, math.inf)],
)
def test_geodesic_rejects_invalid_coordinates(lon, lat):
    with pytest.raises(ValueError):
        geodesic_distance_m(lon, lat, -66.0, 18.0)


def test_hash_is_canonical():
    assert canonical_json_sha256({"b": 2, "a": 1}) == canonical_json_sha256({"a": 1, "b": 2})


def test_4d_metrics():
    a = TrackPoint4D(-66.0, 18.0, 100.0, 0.0)
    b = TrackPoint4D(-66.0, 18.01, 200.0, 10.0)
    metrics = segment_metrics_4d(a, b)
    assert metrics["horizontal_m"] > 1000
    assert metrics["vertical_m"] == 100
    assert metrics["distance_3d_m"] > metrics["horizontal_m"]


def test_4d_metrics_reject_time_reversal():
    with pytest.raises(ValueError, match="non-decreasing"):
        segment_metrics_4d(
            TrackPoint4D(-66.0, 18.0, epoch_s=10.0),
            TrackPoint4D(-66.0, 18.01, epoch_s=9.0),
        )
