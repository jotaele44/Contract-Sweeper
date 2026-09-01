import json
import shutil
from pathlib import Path

from scripts.validate_federation_spatial import validate

REPO_ROOT = Path(__file__).resolve().parents[1]


def _spatial_root(tmp_path: Path) -> Path:
    shutil.copy2(REPO_ROOT / "federation.spatial.json", tmp_path / "federation.spatial.json")
    shutil.copytree(REPO_ROOT / "schemas", tmp_path / "schemas")
    (tmp_path / "reports").mkdir()
    shutil.copy2(
        REPO_ROOT / "reports/federation_spatial_impact_v1.json",
        tmp_path / "reports/federation_spatial_impact_v1.json",
    )
    manifest = json.loads((tmp_path / "federation.spatial.json").read_text(encoding="utf-8"))
    paths = list(manifest["domain_extensions"])
    paths.extend(manifest["storage"][key] for key in ("postgis_migration", "mvt_migration"))
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return tmp_path


def test_spatial_validator_accepts_repository_contract() -> None:
    assert validate(REPO_ROOT) == []


def test_spatial_validator_rejects_path_escape(tmp_path: Path) -> None:
    root = _spatial_root(tmp_path)
    path = root / "federation.spatial.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["contracts"]["feature"] = "../outside.schema.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert any("escapes repository root" in problem for problem in validate(root))


def test_spatial_validator_rejects_impact_report_schema_drift(tmp_path: Path) -> None:
    root = _spatial_root(tmp_path)
    path = root / "reports/federation_spatial_impact_v1.json"
    impact = json.loads(path.read_text(encoding="utf-8"))
    impact["backward_compatible"] = "yes"
    path.write_text(json.dumps(impact), encoding="utf-8")
    assert any("spatial impact report schema violation" in problem for problem in validate(root))


def test_spatial_validator_rejects_missing_domain_extension(tmp_path: Path) -> None:
    root = _spatial_root(tmp_path)
    (root / "federation/spatial_core.py").unlink()
    assert any("missing domain extension" in problem for problem in validate(root))
