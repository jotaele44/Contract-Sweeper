from moneysweep.runtime.spatial_materializer import flow_feature, point_feature


def test_point_requires_real_coordinates():
    assert point_feature({"municipality":"San Juan"},feature_id="x",feature_class="project",source_id="src") is None


def test_point_materializes_source_reported_geometry():
    f=point_feature({"geo_lat":18.45,"geo_lon":-66.1,"geo_attribution_confidence":"exact_name"},feature_id="p1",feature_class="project",source_id="src")
    assert f is not None
    assert f["geometry"]["coordinates"]==[-66.1,18.45]
    assert f["identity_semantics"]=="CANDIDATE_NOT_IDENTITY"
    assert f["coordinate_method"]=="SOURCE_REPORTED"


def test_flow_requires_both_endpoints():
    a={"geo_lat":18.45,"geo_lon":-66.1}; b={"geo_lat":18.1,"geo_lon":-66.5}
    f=flow_feature(a,b,feature_id="contract:1",source_id="award")
    assert f is not None and f["geometry"]["type"]=="LineString"
    assert flow_feature(a,{},feature_id="contract:2",source_id="award") is None
