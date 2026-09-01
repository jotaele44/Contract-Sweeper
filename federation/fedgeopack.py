"""Build and verify integrity-safe federation offline geospatial packages.

When ``created_at`` is supplied, identical inputs produce byte-identical ZIPs:
members are sorted and written with a fixed ZIP timestamp. Without it, the
manifest records the current UTC time by design.
"""

from __future__ import annotations
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from .spatial_core import canonical_json_sha256

PACKAGE_VERSION = "fedgeopack/1.0"
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MAX_MEMBER_BYTES = 2 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(prefix: str, path: Path) -> str:
    name = PurePosixPath(prefix) / path.name
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("unsafe package member")
    return str(name)


def _write_fixed(z: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    z.writestr(info, data)


def _manifest_id(manifest: dict) -> str:
    core = {
        key: value for key, value in manifest.items() if key not in {"package_id", "created_at"}
    }
    return canonical_json_sha256(core)[:32]


def _load_manifest(data: bytes) -> dict:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate manifest key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant in manifest: {value}")

    try:
        manifest = json.loads(data, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    return manifest


def build_package(
    output: Path | str,
    *,
    producer_repo: str,
    layers: Iterable[Path | str] = (),
    rasters: Iterable[Path | str] = (),
    styles: Iterable[Path | str] = (),
    crs: str = "OGC:CRS84",
    provenance: list[dict] | None = None,
    investigation: dict | None = None,
    created_at: str | None = None,
) -> dict:
    out = Path(output)
    members = []
    for prefix, items in (("layers", layers), ("rasters", rasters), ("styles", styles)):
        for raw in items:
            p = Path(raw)
            if not p.is_file():
                raise FileNotFoundError(p)
            members.append((p, _safe_name(prefix, p), _sha(p)))
    archive_names = [archive_name for _, archive_name, _ in members]
    if len(archive_names) != len(set(archive_names)):
        raise ValueError("duplicate package member path")
    hashes = {a: d for _, a, d in members}
    layer_rows = [
        {
            "layer_id": Path(a).stem,
            "path": a,
            "format": Path(a).suffix.lstrip(".").lower(),
            "sha256": d,
        }
        for _, a, d in members
        if a.startswith("layers/")
    ]
    raster_rows = [
        {
            "layer_id": Path(a).stem,
            "path": a,
            "format": "cog"
            if Path(a).suffix.lower() in {".tif", ".tiff"}
            else Path(a).suffix.lstrip(".").lower(),
            "sha256": d,
        }
        for _, a, d in members
        if a.startswith("rasters/")
    ]
    core = {
        "package_version": PACKAGE_VERSION,
        "producer_repo": producer_repo,
        "crs": crs,
        "layers": layer_rows,
        "rasters": raster_rows,
        "styles": [{"path": a, "sha256": d} for _, a, d in members if a.startswith("styles/")],
        "hashes": hashes,
        "provenance": provenance or [],
        "investigation": investigation,
        "access_class": "PUBLIC",
    }
    core["package_id"] = _manifest_id(core)
    core["created_at"] = created_at or datetime.now(timezone.utc).isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        for p, a, _ in sorted(members, key=lambda x: x[1]):
            _write_fixed(z, a, p.read_bytes())
        _write_fixed(
            z,
            "manifest.json",
            json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
        )
    return core


def verify_package(path: Path | str) -> dict:
    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate package member path")
        if names.count("manifest.json") != 1:
            raise ValueError("package must contain exactly one manifest.json")
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"unsafe package member: {name}")
        infos = z.infolist()
        if any(info.file_size > MAX_MEMBER_BYTES for info in infos):
            raise ValueError("package member exceeds size limit")
        if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
            raise ValueError("package exceeds total size limit")
        manifest = _load_manifest(z.read("manifest.json"))
        if manifest.get("package_version") != PACKAGE_VERSION:
            raise ValueError("unsupported package version")
        package_id = manifest.get("package_id")
        if not isinstance(package_id, str) or package_id != _manifest_id(manifest):
            raise ValueError("package_id does not match canonical manifest identity")
        hashes = manifest.get("hashes")
        if not isinstance(hashes, dict):
            raise ValueError("manifest hashes must be an object")
        expected_members = set(hashes) | {"manifest.json"}
        if set(names) != expected_members:
            raise ValueError("package members do not match manifest hashes")
        for name, expected in hashes.items():
            if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                raise ValueError(f"invalid manifest hash: {name}")
            if hashlib.sha256(z.read(name)).hexdigest() != expected:
                raise ValueError(f"hash mismatch: {name}")
    return manifest
