from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping, Protocol, Any


class SourceAdapter(Protocol):
    """Adapter contract: acquisition is source-specific; canonicalization is not."""

    def iter_records(self) -> Iterable[Mapping[str, Any]]:
        ...

    def source_manifest(self) -> Mapping[str, Any]:
        ...


def stable_observation_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash only identity-defining observation fields using canonical JSON serialization."""
    canonical = {
        key: payload.get(key)
        for key in (
            "holder_id",
            "issuer_id",
            "security_id",
            "security_class_raw",
            "position_class",
            "as_of_date",
            "report_date",
            "source_id",
            "source_record_id",
        )
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
