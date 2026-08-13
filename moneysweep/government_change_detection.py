"""Bounded discovery of government organizational-change candidates.

Lexical hits are discovery only. They never establish identity or binding legal
change and must be adjudicated through ``moneysweep.government_changes`` before
promotion.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

DETECTOR_VERSION = "government_change_phrase_scan_v1"
SCOPE_CLAIM = "BOUNDED_NOT_EXHAUSTIVE"
PATTERN_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "government_organization_change_patterns.json"
)


def _load_patterns(path: Path = PATTERN_CONFIG) -> dict[str, tuple[str, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "government_organization_change_patterns_v1":
        raise ValueError("unsupported organization-change pattern schema")
    if payload.get("detector_version") != DETECTOR_VERSION:
        raise ValueError("pattern detector_version does not match runtime")
    rows = payload.get("patterns")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("organization-change patterns must be a non-empty object")
    return {
        str(event_type): tuple(str(pattern) for pattern in patterns)
        for event_type, patterns in rows.items()
    }


PATTERNS = _load_patterns()


def detect_candidates(
    *, text: str, source_assertion_id: str, affected_entity_id: str
) -> list[dict]:
    """Return deterministic lexical candidates; never promote them to events."""
    if not isinstance(text, str) or not text:
        return []
    if not source_assertion_id or not affected_entity_id:
        raise ValueError("source_assertion_id and affected_entity_id are required")

    found: list[dict] = []
    for event_type, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = match.group(0)
                identity = (
                    f"{source_assertion_id}|{affected_entity_id}|{event_type}|"
                    f"{match.start()}|{match.end()}|{raw}"
                )
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
                found.append(
                    {
                        "candidate_id": f"GCHC_{digest}",
                        "affected_entity_id": affected_entity_id,
                        "candidate_event_type": event_type,
                        "source_assertion_id": source_assertion_id,
                        "raw_match": raw,
                        "start": match.start(),
                        "end": match.end(),
                        "detector_version": DETECTOR_VERSION,
                        "scope_claim": SCOPE_CLAIM,
                        "certification_state": "CANDIDATE_NOT_IDENTITY",
                    }
                )
    return sorted(
        found,
        key=lambda row: (row["start"], row["end"], row["candidate_event_type"]),
    )


def candidate_types(rows: Iterable[dict]) -> set[str]:
    return {str(row["candidate_event_type"]) for row in rows}
