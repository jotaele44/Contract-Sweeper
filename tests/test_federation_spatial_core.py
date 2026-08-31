from federation.spatial_core import TrackPoint4D,bbox_distance_m,canonical_json_sha256,geodesic_distance_m,point_in_bbox,segment_metrics_4d

def test_geodesic_pr_scale():
 d=geodesic_distance_m(-66.0,18.0,-66.0,19.0); assert 110_000<d<112_000

def test_bbox_distance_and_membership():
 box=(-67.0,18.0,-66.0,19.0); assert point_in_bbox(-66.5,18.5,box); assert bbox_distance_m(-66.5,18.5,box)==0; assert bbox_distance_m(-65.5,18.5,box)>50_000

def test_hash_is_canonical(): assert canonical_json_sha256({"b":2,"a":1})==canonical_json_sha256({"a":1,"b":2})

def test_4d_metrics():
 a=TrackPoint4D(-66.0,18.0,100.0,0.0); b=TrackPoint4D(-66.0,18.01,200.0,10.0); m=segment_metrics_4d(a,b); assert m["horizontal_m"]>1000; assert m["vertical_m"]==100; assert m["distance_3d_m"]>m["horizontal_m"]
