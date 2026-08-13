from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from moneysweep.government_changes import ChangeEventError, evaluate_events

ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = ROOT / "data" / "derived" / "government_organization_change_events.json"
CANDIDATES_PATH = (
    ROOT / "data" / "staging" / "processed" / "government_organization_change_candidates.json"
)
router = APIRouter(tags=["government-changes"])


def _load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    payload = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    rows = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("change event ledger must be a list or an events object")
    return rows


def _load_candidates() -> list[dict]:
    if not CANDIDATES_PATH.exists():
        return []
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    rows = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("change candidate ledger must contain a candidates array")
    return rows


@router.get("/government-changes")
def list_changes(
    entity_id: str | None = None,
    severity: str | None = None,
    alerts_only: bool = False,
):
    try:
        rows = evaluate_events(_load_events())
    except (OSError, json.JSONDecodeError, ValueError, ChangeEventError) as exc:
        raise HTTPException(500, f"change ledger invalid: {exc}") from exc
    if entity_id:
        rows = [row for row in rows if row.get("affected_entity_id") == entity_id]
    if severity:
        rows = [row for row in rows if row["derived"]["severity"] == severity.upper()]
    if alerts_only:
        rows = [row for row in rows if row["derived"]["alert"]]
    return rows


@router.get("/government-changes/candidates")
def list_change_candidates(entity_id: str | None = None):
    try:
        rows = _load_candidates()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(500, f"change candidate ledger invalid: {exc}") from exc
    if entity_id:
        rows = [row for row in rows if row.get("affected_entity_id") == entity_id]
    return rows


@router.get("/government-changes/summary")
def change_summary():
    rows = list_changes()
    candidates = list_change_candidates()
    counts = {f"S{i}": 0 for i in range(5)}
    for row in rows:
        counts[row["derived"]["severity"]] += 1
    return {
        "events": len(rows),
        "candidates": len(candidates),
        "alerts": sum(1 for row in rows if row["derived"]["alert"]),
        "binding": sum(1 for row in rows if row["derived"]["binding"]),
        "bySeverity": counts,
        "ledgerPresent": EVENTS_PATH.exists(),
        "candidateLedgerPresent": CANDIDATES_PATH.exists(),
    }
