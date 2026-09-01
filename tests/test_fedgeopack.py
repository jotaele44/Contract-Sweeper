import json
import zipfile

import pytest

from federation.fedgeopack import build_package, verify_package


def test_pinned_build_is_byte_reproducible(tmp_path):
    layer = tmp_path / "layer.geojson"
    layer.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    a = tmp_path / "a.fedgeopack"
    b = tmp_path / "b.fedgeopack"
    kw = {
        "producer_repo": "moneysweep-pr",
        "layers": [layer],
        "created_at": "2026-08-31T00:00:00+00:00",
    }
    ma = build_package(a, **kw)
    mb = build_package(b, **kw)
    assert ma["package_id"] == mb["package_id"]
    assert a.read_bytes() == b.read_bytes()
    assert verify_package(a)["package_id"] == ma["package_id"]


def test_verify_rejects_zip_slip_member(tmp_path):
    bad = tmp_path / "bad.fedgeopack"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil", b"x")
        z.writestr("manifest.json", '{"package_version":"fedgeopack/1.0","hashes":{}}')
    with pytest.raises(ValueError, match="unsafe package member"):
        verify_package(bad)


def test_build_rejects_duplicate_member_paths(tmp_path):
    first = tmp_path / "first" / "layer.geojson"
    second = tmp_path / "second" / "layer.geojson"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate package member path"):
        build_package(tmp_path / "bad.fedgeopack", producer_repo="test", layers=[first, second])


def test_verify_rejects_unmanifested_member(tmp_path):
    package = tmp_path / "extra.fedgeopack"
    build_package(
        package,
        producer_repo="moneysweep-pr",
        created_at="2026-08-31T00:00:00+00:00",
    )
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("extra.txt", b"not declared")

    with pytest.raises(ValueError, match="do not match manifest"):
        verify_package(package)


def test_verify_rejects_duplicate_archive_members(tmp_path):
    package = tmp_path / "duplicate.fedgeopack"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("manifest.json", "{}")

    with pytest.raises(ValueError, match="duplicate package member path"):
        verify_package(package)


def test_verify_rejects_tampered_package_identity(tmp_path):
    layer = tmp_path / "layer.geojson"
    layer.write_text("{}", encoding="utf-8")
    source = tmp_path / "source.fedgeopack"
    build_package(
        source,
        producer_repo="moneysweep-pr",
        layers=[layer],
        created_at="2026-08-31T00:00:00+00:00",
    )
    tampered = tmp_path / "tampered.fedgeopack"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(tampered, "w") as rewritten:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "manifest.json":
                manifest = json.loads(data)
                manifest["package_id"] = "0" * 32
                data = json.dumps(manifest).encode()
            rewritten.writestr(info, data)
    with pytest.raises(ValueError, match="package_id"):
        verify_package(tampered)


def test_verify_rejects_duplicate_manifest_keys(tmp_path):
    package = tmp_path / "duplicate-key.fedgeopack"
    manifest = '{"package_version":"fedgeopack/1.0","package_version":"fedgeopack/1.0"}'
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", manifest)
    with pytest.raises(ValueError, match="duplicate manifest key"):
        verify_package(package)
