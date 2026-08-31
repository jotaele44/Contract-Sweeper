import zipfile
import pytest
from federation.fedgeopack import build_package, verify_package

def test_pinned_build_is_byte_reproducible(tmp_path):
 layer=tmp_path/"layer.geojson"; layer.write_text('{"type":"FeatureCollection","features":[]}',encoding="utf-8"); a=tmp_path/"a.fedgeopack"; b=tmp_path/"b.fedgeopack"; kw={"producer_repo":"moneysweep-pr","layers":[layer],"created_at":"2026-08-31T00:00:00+00:00"}; ma=build_package(a,**kw); mb=build_package(b,**kw); assert ma["package_id"]==mb["package_id"]; assert a.read_bytes()==b.read_bytes(); assert verify_package(a)["package_id"]==ma["package_id"]
def test_verify_rejects_zip_slip_member(tmp_path):
 bad=tmp_path/"bad.fedgeopack"
 with zipfile.ZipFile(bad,"w") as z: z.writestr("../evil",b"x"); z.writestr("manifest.json",'{"package_version":"fedgeopack/1.0","hashes":{}}')
 with pytest.raises(ValueError,match="unsafe package member"): verify_package(bad)
