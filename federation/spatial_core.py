"""Federation Spatial Core v1: deterministic WGS84 geometry primitives."""
from __future__ import annotations
import hashlib, json, math
from dataclasses import dataclass
from typing import Any, Sequence
CONTRACT_VERSION="federation-spatial-contract/1.0"; IDENTITY_DEFAULT="CANDIDATE_NOT_IDENTITY"
WGS84_A=6378137.0; WGS84_F=1/298.257223563; WGS84_B=(1-WGS84_F)*WGS84_A

def validate_lon_lat(lon:float,lat:float)->tuple[float,float]:
    lon,lat=float(lon),float(lat)
    if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90: raise ValueError(f"invalid WGS84 coordinate: {(lon,lat)}")
    return lon,lat

def canonical_json_sha256(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def _haversine_m(lon1,lat1,lon2,lat2):
    lon1,lat1=validate_lon_lat(lon1,lat1); lon2,lat2=validate_lon_lat(lon2,lat2); p1,p2=map(math.radians,(lat1,lat2)); dp=p2-p1; dl=math.radians(lon2-lon1); h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 6371008.8*2*math.atan2(math.sqrt(h),math.sqrt(max(0,1-h)))

def geodesic_distance_m(lon1:float,lat1:float,lon2:float,lat2:float)->float:
    lon1,lat1=validate_lon_lat(lon1,lat1); lon2,lat2=validate_lon_lat(lon2,lat2)
    if (lon1,lat1)==(lon2,lat2): return 0.0
    p1,p2=map(math.radians,(lat1,lat2)); U1=math.atan((1-WGS84_F)*math.tan(p1)); U2=math.atan((1-WGS84_F)*math.tan(p2)); L=math.radians(lon2-lon1); lam=L
    for _ in range(200):
        sl,cl=math.sin(lam),math.cos(lam); ss=math.sqrt((math.cos(U2)*sl)**2+(math.cos(U1)*math.sin(U2)-math.sin(U1)*math.cos(U2)*cl)**2)
        if ss==0:return 0.0
        cs=math.sin(U1)*math.sin(U2)+math.cos(U1)*math.cos(U2)*cl; sigma=math.atan2(ss,cs); sa=math.cos(U1)*math.cos(U2)*sl/ss; c2a=1-sa*sa; c2sm=0.0 if c2a==0 else cs-2*math.sin(U1)*math.sin(U2)/c2a; C=WGS84_F/16*c2a*(4+WGS84_F*(4-3*c2a)); nxt=L+(1-C)*WGS84_F*sa*(sigma+C*ss*(c2sm+C*cs*(-1+2*c2sm*c2sm)))
        if abs(nxt-lam)<1e-12: lam=nxt; break
        lam=nxt
    else:return _haversine_m(lon1,lat1,lon2,lat2)
    u2=c2a*(WGS84_A**2-WGS84_B**2)/(WGS84_B**2); A=1+u2/16384*(4096+u2*(-768+u2*(320-175*u2))); B=u2/1024*(256+u2*(-128+u2*(74-47*u2))); ds=B*ss*(c2sm+B/4*(cs*(-1+2*c2sm*c2sm)-B/6*c2sm*(-3+4*ss*ss)*(-3+4*c2sm*c2sm))); return WGS84_B*A*(sigma-ds)

def point_in_bbox(lon:float,lat:float,bbox:Sequence[float])->bool:
    validate_lon_lat(lon,lat); min_lon,min_lat,max_lon,max_lat=map(float,bbox); return min_lon<=lon<=max_lon and min_lat<=lat<=max_lat

def bbox_distance_m(lon:float,lat:float,bbox:Sequence[float])->float:
    if point_in_bbox(lon,lat,bbox): return 0.0
    min_lon,min_lat,max_lon,max_lat=map(float,bbox); return geodesic_distance_m(lon,lat,min(max(lon,min_lon),max_lon),min(max(lat,min_lat),max_lat))

@dataclass(frozen=True)
class TrackPoint4D: lon:float; lat:float; altitude_m:float|None=None; epoch_s:float|None=None

def segment_metrics_4d(a:TrackPoint4D,b:TrackPoint4D)->dict[str,float|None]:
    h=geodesic_distance_m(a.lon,a.lat,b.lon,b.lat); v=None if a.altitude_m is None or b.altitude_m is None else b.altitude_m-a.altitude_m; d=math.hypot(h,v or 0.0); t=None if a.epoch_s is None or b.epoch_s is None else b.epoch_s-a.epoch_s; return {"horizontal_m":h,"vertical_m":v,"distance_3d_m":d,"elapsed_s":t,"speed_mps":None if not t or t<=0 else d/t}
