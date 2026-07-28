"""Deterministic identifiers for Case Manager records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_ID_KINDS = {
    "case", "case_evidence", "claim", "claim_evidence", "case_entity",
    "case_event", "contradiction", "lead", "finding", "case_snapshot", "audit_event",
}


def deterministic_id(kind: str, *parts: Any, length: int = 24) -> str:
    """Return an idempotent identifier from normalized semantic parts.

    Inputs are JSON-normalized so identical logical payloads yield identical IDs.
    """
    if kind not in _ID_KINDS:
        raise ValueError(f"unsupported id kind: {kind}")
    if not 16 <= length <= 64:
        raise ValueError("length must be between 16 and 64")
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{kind}_{digest}"


def is_deterministic_id(value: str, kind: str) -> bool:
    return bool(re.fullmatch(rf"{re.escape(kind)}_[0-9a-f]{{16,64}}", value))
