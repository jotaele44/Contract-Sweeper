"""Materialize bounded organization-change candidates from validated source updates.

The source-update controller calls this module only after a producer output has
passed its normal output and atomicity gates. Source bindings are explicit in
``config/government_organization_change_monitor.json``; no source name, file
name, or proximity heuristic is used to infer a canonical entity.

Candidate and adjudicated-event ledgers remain separate. Candidate snapshots are
append-only observations and always remain ``CANDIDATE_NOT_IDENTITY``. Promotion
to the event ledger is a separate validation step using ``evaluate_events``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from moneysweep.government_change_detection import (
    DETECTOR_VERSION,
    SCOPE_CLAIM,
    detect_candidates,
)
from moneysweep.government_changes import evaluate_events

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path("config/government_organization_change_monitor.json")
DEFAULT_CANDIDATE_LEDGER = Path(
    "data/staging/processed/government_organization_change_candidates.json"
)
DEFAULT_EVENT_LEDGER = Path("data/derived/government_organization_change_events.json")
MAX_TEXT_BYTES = 5_000_000


class ChangeMaterializationError(ValueError):
    """Raised when monitor configuration or a bound source output is invalid."""


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path, default: Mapping[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ChangeMaterializationError(f"expected object at {path}")
    return payload


def load_monitor_config(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    path = root / CONFIG_PATH
    payload = _load_json(path, {})
    if payload.get("schema_version") != "government_organization_change_monitor_v1":
        raise ChangeMaterializationError("unsupported organization-change monitor schema")
    if payload.get("detector_version") != DETECTOR_VERSION:
        raise ChangeMaterializationError("monitor detector_version does not match runtime")
    if payload.get("scope_claim") != SCOPE_CLAIM:
        raise ChangeMaterializationError("monitor scope_claim does not match runtime")
    bindings = payload.get("bindings")
    if not isinstance(bindings, list):
        raise ChangeMaterializationError("bindings must be an array")
    return payload


def _binding_for(config: Mapping[str, Any], source_id: str) -> dict[str, Any] | None:
    matches = [
        row
        for row in config.get("bindings", [])
        if isinstance(row, dict) and row.get("source_id") == source_id
    ]
    if len(matches) > 1:
        raise ChangeMaterializationError(f"duplicate monitor binding for {source_id}")
    return matches[0] if matches else None


def _read_bound_text(root: Path, output: Mapping[str, Any]) -> tuple[str, str]:
    rel = output.get("path")
    if not isinstance(rel, str) or not rel:
        raise ChangeMaterializationError("bound output path is required")
    path = root / rel
    if not path.is_file():
        raise ChangeMaterializationError(f"bound output missing: {rel}")
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise ChangeMaterializationError(f"bound output exceeds {MAX_TEXT_BYTES} bytes: {rel}")
    encoding = output.get("encoding", "utf-8")
    if encoding != "utf-8":
        raise ChangeMaterializationError("only explicit UTF-8 text bindings are supported")
    return rel, path.read_text(encoding="utf-8")


def _snapshot_id(source_id: str, output_path: str, output_sha256: str) -> str:
    raw = f"{source_id}|{output_path}|{output_sha256}"
    return "GCHS_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def materialize_validated_source_update(
    *,
    source_id: str,
    run_id: str,
    output_hashes: Mapping[str, str | None],
    root: Path | None = None,
) -> dict[str, Any]:
    """Scan one explicitly bound validated source manifestation.

    This function never writes the adjudicated event ledger. It records immutable
    source-manifestation snapshots and lexical candidates only.
    """
    root = root or REPO_ROOT
    config = load_monitor_config(root)
    binding = _binding_for(config, source_id)
    if binding is None:
        return {"status": "NOT_CONFIGURED", "source_id": source_id, "candidates": 0}

    entity_id = binding.get("affected_entity_id")
    if not isinstance(entity_id, str) or not entity_id.startswith("GOV_"):
        raise ChangeMaterializationError(
            f"binding for {source_id} requires explicit affected_entity_id"
        )
    source_assertion_id = binding.get("source_assertion_id")
    if not isinstance(source_assertion_id, str) or not source_assertion_id:
        raise ChangeMaterializationError(
            f"binding for {source_id} requires explicit source_assertion_id"
        )
    outputs = binding.get("text_outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ChangeMaterializationError(f"binding for {source_id} requires non-empty text_outputs")

    candidate_rel = Path(config.get("candidate_ledger") or DEFAULT_CANDIDATE_LEDGER)
    ledger_path = root / candidate_rel
    ledger = _load_json(
        ledger_path,
        {
            "schema_version": "government_organization_change_candidates_v1",
            "scope_claim": SCOPE_CLAIM,
            "snapshots": [],
            "candidates": [],
        },
    )
    snapshots = ledger.setdefault("snapshots", [])
    candidates = ledger.setdefault("candidates", [])
    if not isinstance(snapshots, list) or not isinstance(candidates, list):
        raise ChangeMaterializationError("candidate ledger arrays are malformed")

    existing_snapshots = {row.get("snapshot_id") for row in snapshots if isinstance(row, dict)}
    existing_candidates = {row.get("candidate_id") for row in candidates if isinstance(row, dict)}
    added_candidates = 0
    added_snapshots = 0

    for output in outputs:
        if not isinstance(output, dict):
            raise ChangeMaterializationError("text_outputs items must be objects")
        rel, text = _read_bound_text(root, output)
        output_sha = output_hashes.get(rel)
        if not output_sha:
            raise ChangeMaterializationError(
                f"validated output hash unavailable for bound output: {rel}"
            )
        snapshot_id = _snapshot_id(source_id, rel, output_sha)
        if snapshot_id in existing_snapshots:
            continue

        found = detect_candidates(
            text=text,
            source_assertion_id=source_assertion_id,
            affected_entity_id=entity_id,
        )
        candidate_ids: list[str] = []
        for candidate in found:
            candidate_ids.append(candidate["candidate_id"])
            if candidate["candidate_id"] in existing_candidates:
                continue
            candidates.append(
                {
                    **candidate,
                    "source_id": source_id,
                    "source_output_path": rel,
                    "source_output_sha256": output_sha,
                }
            )
            existing_candidates.add(candidate["candidate_id"])
            added_candidates += 1

        snapshots.append(
            {
                "snapshot_id": snapshot_id,
                "source_id": source_id,
                "run_id": run_id,
                "source_output_path": rel,
                "source_output_sha256": output_sha,
                "candidate_ids": sorted(candidate_ids),
                "detector_version": DETECTOR_VERSION,
                "scope_claim": SCOPE_CLAIM,
                "certification_state": "AUDIT_ONLY",
            }
        )
        existing_snapshots.add(snapshot_id)
        added_snapshots += 1

    candidates.sort(key=lambda row: row.get("candidate_id", ""))
    snapshots.sort(key=lambda row: row.get("snapshot_id", ""))
    _atomic_json(ledger_path, ledger)
    return {
        "status": "MATERIALIZED",
        "source_id": source_id,
        "snapshots_added": added_snapshots,
        "candidates_added": added_candidates,
        "candidates": len(candidates),
    }


def materialize_event_ledger(
    events: Iterable[Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate and atomically materialize the adjudicated event universe."""
    root = root or REPO_ROOT
    config = load_monitor_config(root)
    rows = evaluate_events(events)
    event_rel = Path(config.get("event_ledger") or DEFAULT_EVENT_LEDGER)
    payload = {
        "schema_version": "government_organization_change_events_v1",
        "events": [{key: value for key, value in row.items() if key != "derived"} for row in rows],
    }
    _atomic_json(root / event_rel, payload)
    return {
        "status": "MATERIALIZED",
        "events": len(rows),
        "binding": sum(1 for row in rows if row["derived"]["binding"]),
        "alerts": sum(1 for row in rows if row["derived"]["alert"]),
    }
