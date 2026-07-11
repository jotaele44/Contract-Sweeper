"""Dropzone scaffolding: every declared drop location exists on disk and every
producer's hardcoded dropzone constant agrees with the registries.

Guards against the wave2b-repaired defect class: three different files
declaring three different dropzones for the same source (baseline
contradictions 7/8), and dropzones that match nothing on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ingest_act_transition import COMMITTED_EXTRACT, PDF_ARCHIVE_DIR
from scripts.ingest_donaciones import RAW_DIR_NAME as DONACIONES_DIR
from scripts.ingest_ocpr_contracts import RAW_DIR_NAME as OCPR_DIR
from scripts.source_intake_tranche_b import SOURCE_SPECS
from moneysweep.update_controller.policy import _manual_export_entries

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _registry_drop_dirs() -> dict[str, str]:
    reg = json.loads((ROOT / "registries" / "source_registry.json").read_text(encoding="utf-8"))
    return {
        s["source_id"]: s["manual_drop_dir"]
        for s in reg.get("sources", [])
        if s.get("manual_drop_dir")
    }


def test_every_manual_export_drop_dir_exists():
    entries = _manual_export_entries(ROOT)
    assert entries, "manual_export_registry parsed empty — key regression (contradiction 10)"
    missing = {
        sid: e["expected_drop_dir"]
        for sid, e in entries.items()
        if not (ROOT / e["expected_drop_dir"]).is_dir()
    }
    assert not missing, f"declared dropzones with no directory on disk: {missing}"


def test_every_registry_manual_drop_dir_exists():
    missing = {
        sid: drop for sid, drop in _registry_drop_dirs().items() if not (ROOT / drop).is_dir()
    }
    assert not missing, f"registry manual_drop_dir with no directory on disk: {missing}"


def test_manual_export_and_source_registry_agree_on_drop_dirs():
    """When both registries declare a dropzone for a source, they must agree."""
    entries = _manual_export_entries(ROOT)
    registry = _registry_drop_dirs()
    disagreements = {}
    for sid, entry in entries.items():
        declared = entry["expected_drop_dir"].rstrip("/")
        canonical = (registry.get(sid) or "").rstrip("/")
        if canonical and declared != canonical:
            disagreements[sid] = (canonical, declared)
    assert not disagreements, f"source_registry vs manual_export_registry: {disagreements}"


def test_tranche_b_specs_point_at_declared_dropzones():
    """Tranche-B specs for registry-declared sources must use the same
    dropzone as the registries (no more phantom 'ACT Transition Contracts')."""
    entries = _manual_export_entries(ROOT)
    registry = _registry_drop_dirs()
    for spec in SOURCE_SPECS.values():
        declared = (entries.get(spec.source_id) or {}).get("expected_drop_dir") or registry.get(
            spec.source_id
        )
        if declared:
            assert spec.dropzone.rstrip("/") == declared.rstrip("/"), (
                f"{spec.source_id}: tranche-b dropzone {spec.dropzone!r} != declared {declared!r}"
            )
        # Every spec's dropzone must exist on disk, declared or not.
        assert (ROOT / spec.dropzone).is_dir(), (
            f"{spec.source_id}: tranche-b dropzone {spec.dropzone!r} does not exist"
        )


def test_ingest_script_constants_match_declarations():
    entries = _manual_export_entries(ROOT)
    assert DONACIONES_DIR.rstrip("/") == entries["donaciones_pr"]["expected_drop_dir"].rstrip("/")
    assert (ROOT / OCPR_DIR).is_dir(), "ingest_ocpr_contracts dropzone missing on disk"
    # ACT/ACUDEN: the committed extract lives inside the declared dropzone, and
    # the PDF archive dir exists with both source PDFs.
    act_drop = entries["act_transition_contracts"]["expected_drop_dir"].rstrip("/")
    assert COMMITTED_EXTRACT.startswith(act_drop)
    archive = ROOT / PDF_ARCHIVE_DIR
    assert archive.is_dir()
    assert any(archive.glob("ACT*.pdf")) and any(archive.glob("ACUDES*.pdf"))


def test_dropzones_carry_operator_readme():
    """wave2b dropzones ship operator instructions (tracked via .gitignore
    re-include); .gitkeep makes the empty dir committable."""
    for rel in (
        "data/raw/Donaciones",
        "data/raw/Cabilderos",
        "data/raw/COR3",
        "data/raw/OCPR_Contracts",
        "data/raw/Oficina del Contralor",
        "data/raw/sam",
        "data/raw/FPDS_Report_Builder",
        "data/raw/USAspending_Slices",
        "data/raw/PRASA",
    ):
        d = ROOT / rel
        assert (d / ".gitkeep").exists(), f"{rel}/.gitkeep missing"
        assert (d / "README.md").exists(), f"{rel}/README.md missing"
