"""Build and verify integrity-safe federation offline geospatial packages.

When ``created_at`` is supplied, identical inputs produce byte-identical ZIPs:
members are sorted and written with a fixed ZIP timestamp. Without it, the
manifest records the current UTC time by design.
"""
from __future__ import annotations
import hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from typing import Iterable
from .spatial_core import canonical_json_sha256
PACKAGE_VERSION="fedgeopack/1.0"; ZIP_EPOCH=(1980,1,1,0,0,0)
def _sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
 return h.hexdigest()
def _safe_name(prefix:str,path:Path)->str:
 name=PurePosixPath(prefix)/path.name
 if name.is_absolute() or ".." in name.parts:raise ValueError("unsafe package member")
 return str(name)
def _write_fixed(z:zipfile.ZipFile,name:str,data:bytes)->None:
 info=zipfile.ZipInfo(name,ZIP_EPOCH); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o644<<16; z.writestr(info,data)
def build_package(output:Path|str,*,producer_repo:str,layers:Iterable[Path|str]=(),rasters:Iterable[Path|str]=(),styles:Iterable[Path|str]=(),crs:str="OGC:CRS84",provenance:list[dict]|None=None,investigation:dict|None=None,created_at:str|None=None)->dict:
 out=Path(output); members=[]
 for prefix,items in (("layers",layers),("rasters",rasters),("styles",styles)):
  for raw in items:
   p=Path(raw)
   if not p.is_file():raise FileNotFoundError(p)
   members.append((p,_safe_name(prefix,p),_sha(p)))
 hashes={a:d for _,a,d in members}; layer_rows=[{"layer_id":Path(a).stem,"path":a,"format":Path(a).suffix.lstrip(".").lower(),"sha256":d} for _,a,d in members if a.startswith("layers/")]; raster_rows=[{"layer_id":Path(a).stem,"path":a,"format":"cog" if Path(a).suffix.lower() in {".tif",".tiff"} else Path(a).suffix.lstrip(".").lower(),"sha256":d} for _,a,d in members if a.startswith("rasters/")]
 core={"package_version":PACKAGE_VERSION,"producer_repo":producer_repo,"crs":crs,"layers":layer_rows,"rasters":raster_rows,"styles":[{"path":a,"sha256":d} for _,a,d in members if a.startswith("styles/")],"hashes":hashes,"provenance":provenance or [],"investigation":investigation,"access_class":"PUBLIC"}; core["package_id"]=canonical_json_sha256(core)[:32]; core["created_at"]=created_at or datetime.now(timezone.utc).isoformat(); out.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(out,"w") as z:
  for p,a,_ in sorted(members,key=lambda x:x[1]):_write_fixed(z,a,p.read_bytes())
  _write_fixed(z,"manifest.json",json.dumps(core,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
 return core
def verify_package(path:Path|str)->dict:
 with zipfile.ZipFile(path,"r") as z:
  for name in z.namelist():
   p=PurePosixPath(name)
   if p.is_absolute() or ".." in p.parts:raise ValueError(f"unsafe package member: {name}")
  manifest=json.loads(z.read("manifest.json"))
  if manifest.get("package_version")!=PACKAGE_VERSION:raise ValueError("unsupported package version")
  for name,expected in manifest.get("hashes",{}).items():
   if hashlib.sha256(z.read(name)).hexdigest()!=expected:raise ValueError(f"hash mismatch: {name}")
 return manifest
