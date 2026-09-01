import json
import shutil
from pathlib import Path

from scripts.validate_haf_contract import CONTRACT, validate

REPO_ROOT = Path(__file__).resolve().parents[1]


def _contract_root(tmp_path: Path) -> Path:
    (tmp_path / CONTRACT.parent).mkdir(parents=True)
    shutil.copy2(REPO_ROOT / CONTRACT, tmp_path / CONTRACT)
    shutil.copy2(REPO_ROOT / "federation.json", tmp_path / "federation.json")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/federation_export.py").write_text("", encoding="utf-8")
    return tmp_path


def test_haf_contract_accepts_complete_repository_binding(tmp_path: Path) -> None:
    assert validate(_contract_root(tmp_path), "jotaele44/moneysweep-pr") == []


def test_haf_contract_rejects_false_canonical_export_claim(tmp_path: Path) -> None:
    root = _contract_root(tmp_path)
    contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    contract["canonical_export_required"] = False
    (root / CONTRACT).write_text(json.dumps(contract), encoding="utf-8")
    assert any(
        "canonical_export_required" in error for error in validate(root, "jotaele44/moneysweep-pr")
    )


def test_haf_contract_rejects_missing_native_contract(tmp_path: Path) -> None:
    root = _contract_root(tmp_path)
    (root / "federation.json").unlink()
    assert "native_contract does not resolve to a file" in validate(root, "jotaele44/moneysweep-pr")
