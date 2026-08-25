"""Local-only data-ingestion and materialization control plane.

This router never promotes uploaded files directly into canonical data. Offline
files are preserved byte-for-byte in the writable workspace with provenance
receipts; source-specific producers must then materialize them. API producers
reuse the registry-driven runner and keep source failures explicit.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from desktop.workspace import bootstrap_workspace, resource_root
from moneysweep.runtime.source_registry import load_source_registry, source_by_id
from scripts.run_automatable_sources import run as run_automatable

router = APIRouter(prefix="/materialization", tags=["materialization"])

API_KEY_NAMES = (
    "CENSUS_API_KEY",
    "EIA_API_KEY",
    "FAC_API_KEY",
    "FEC_API_KEY",
    "FINANCIALDATA_API_KEY",
    "FRED_API_KEY",
    "HIGHERGOV_API_KEY",
    "OPENSTATES_API_KEY",
    "SAM_API_KEY",
)


class ApiRunRequest(BaseModel):
    source: str | None = None
    family: str | None = None
    dry_run: bool = False


def _workspace() -> Path:
    return bootstrap_workspace()


def _load_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _manual_registry() -> dict[str, dict[str, Any]]:
    path = resource_root() / "registries" / "manual_export_registry.yaml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(item.get("source_id")): item
        for item in payload.get("manual_exports", [])
        if item.get("source_id")
    }


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _manual_target(source_id: str, raw_filename: str) -> tuple[Path, dict[str, Any]]:
    manual = _manual_registry().get(source_id)
    if manual is None:
        raise HTTPException(404, f"source {source_id!r} is not a registered manual export")
    drop_dir = str(manual.get("expected_drop_dir") or "").strip()
    if not drop_dir:
        raise HTTPException(409, f"manual source {source_id!r} has no expected_drop_dir")

    root = _workspace()
    target_dir = (root / drop_dir).resolve()
    if not _within(root, target_dir):
        raise HTTPException(409, "manual drop directory escapes the MoneySweep workspace")
    target_dir.mkdir(parents=True, exist_ok=True)

    basename = Path(raw_filename).name or "upload.bin"
    return target_dir / basename, manual


@router.get("/status")
def materialization_status():
    root = _workspace()
    resources = resource_root()
    readiness = _load_json_if_present(resources / "reports" / "materialization_readiness.json")
    production = _load_json_if_present(resources / "data" / "exports" / "production_status.json")
    registry = load_source_registry(resources)
    manual = _manual_registry()
    return {
        "workspace": str(root),
        "dataRoot": str(root / "data"),
        "resourceRoot": str(resources),
        "registeredSources": len(registry.get("sources", [])),
        "manualExportSources": len(manual),
        "readiness": readiness,
        "production": production,
        "apiKeys": {name: bool(os.environ.get(name)) for name in API_KEY_NAMES},
        "secretsReturned": False,
    }


@router.get("/sources")
def materialization_sources():
    resources = resource_root()
    manual = _manual_registry()
    rows = []
    for source in load_source_registry(resources).get("sources", []):
        sid = str(source.get("source_id") or "")
        manual_entry = manual.get(sid)
        rows.append(
            {
                "sourceId": sid,
                "family": source.get("family"),
                "authentication": source.get("authentication"),
                "required": bool(source.get("required")),
                "producerScript": source.get("producer_script"),
                "expectedOutputs": source.get("expected_outputs") or [],
                "manualDropDir": manual_entry.get("expected_drop_dir") if manual_entry else None,
                "manualFilenamePattern": (
                    manual_entry.get("expected_filename_pattern") if manual_entry else None
                ),
            }
        )
    return rows


@router.post("/offline/upload")
async def upload_offline_file(
    source_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Preserve one operator-supplied file in its registered workspace dropzone."""
    if source_by_id(source_id, resource_root()) is None:
        raise HTTPException(404, f"unknown source_id {source_id!r}")

    raw_filename = file.filename or "upload.bin"
    target, manual = _manual_target(source_id, raw_filename)
    temp = target.parent / f".ingest-{uuid.uuid4().hex}.tmp"
    h = hashlib.sha256()
    total = 0
    try:
        with temp.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                h.update(chunk)
                out.write(chunk)
    finally:
        await file.close()

    digest = h.hexdigest()
    classification = "NEW_PAYLOAD"
    if target.exists():
        existing_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if existing_hash == digest:
            temp.unlink(missing_ok=True)
            classification = "BYTE_IDENTICAL_EXISTING"
        else:
            suffix = target.suffix
            stem = target.name[: -len(suffix)] if suffix else target.name
            target = target.with_name(f"{stem}__sha256_{digest[:12]}{suffix}")
            temp.replace(target)
            classification = "DISTINCT_PAYLOADS_SAME_FILENAME"
    else:
        temp.replace(target)

    root = _workspace()
    receipt = {
        "schema_version": "1.0.0",
        "source_id": source_id,
        "raw_filename": raw_filename,
        "stored_relative_path": target.relative_to(root).as_posix(),
        "bytes": total,
        "sha256": digest,
        "classification": classification,
        "expected_filename_pattern": manual.get("expected_filename_pattern"),
        "received_utc": datetime.now(timezone.utc).isoformat(),
        "promotion_state": "STAGED_NOT_PROMOTED",
    }
    receipt_dir = root / "receipts" / "offline_ingest" / source_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{digest}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


@router.post("/offline/{source_id}/run")
def run_offline_source(source_id: str):
    """Invoke the registered producer for a staged manual/offline source."""
    resources = resource_root()
    if source_by_id(source_id, resources) is None:
        raise HTTPException(404, f"unknown source_id {source_id!r}")
    # The explicit source selection bypasses the automatable-only filter. No
    # egress probe is required because this path is for already-downloaded data.
    result = run_automatable(root=_workspace(), source=source_id, require_egress=False)
    return result


@router.post("/api/run")
def run_api_sources(request: ApiRunRequest):
    """Run one or more registry-classified API/producer sources with egress gating."""
    if request.source and source_by_id(request.source, resource_root()) is None:
        raise HTTPException(404, f"unknown source_id {request.source!r}")
    return run_automatable(
        root=_workspace(),
        source=request.source,
        family=request.family,
        dry_run=request.dry_run,
        require_egress=not request.dry_run,
    )
