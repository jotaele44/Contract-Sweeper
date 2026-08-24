"""Bridge legacy and specialized entity namespaces to canonical ``ENT_*`` IDs.

The bridge is deliberately fail-closed. Stable/canonical/committed-alias matches
may resolve to an ``ENT_*`` identity. Normalized-name overlap that is not backed
by the canonical registry remains ``CANDIDATE_NOT_IDENTITY``. Ambiguous matches
remain ``REVIEW`` with every candidate preserved.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from moneysweep.runtime.name_normalization import normalize_name

from .models import ResolutionState
from .resolver import CanonicalEntityIndex


@dataclass(frozen=True)
class NamespaceBridgeRecord:
    source_namespace: str
    source_record_id: str
    source_name: str
    normalized_name: str
    bridge_status: str
    canonical_entity_id: str | None
    canonical_name: str | None
    match_method: str | None
    candidates: tuple[str, ...] = ()
    source_path: str = ""
    source_row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = list(self.candidates)
        return payload


def bridge_name(
    index: CanonicalEntityIndex,
    *,
    source_namespace: str,
    source_record_id: str,
    source_name: str,
    source_path: str = "",
    source_row: int | None = None,
) -> NamespaceBridgeRecord:
    """Bridge a source name through canonical names/committed aliases only."""
    target = index.resolve(source_name)
    if target.resolution_state is ResolutionState.RESOLVED:
        return NamespaceBridgeRecord(
            source_namespace=source_namespace,
            source_record_id=source_record_id,
            source_name=source_name,
            normalized_name=normalize_name(source_name),
            bridge_status="RESOLVED",
            canonical_entity_id=target.canonical_entity_id,
            canonical_name=target.canonical_name,
            match_method=target.match_method,
            candidates=(),
            source_path=source_path,
            source_row=source_row,
        )
    if target.resolution_state is ResolutionState.REVIEW:
        status = "REVIEW"
    else:
        status = "CANDIDATE_NOT_IDENTITY"
    return NamespaceBridgeRecord(
        source_namespace=source_namespace,
        source_record_id=source_record_id,
        source_name=source_name,
        normalized_name=normalize_name(source_name),
        bridge_status=status,
        canonical_entity_id=None,
        canonical_name=None,
        match_method=target.match_method,
        candidates=target.candidates,
        source_path=source_path,
        source_row=source_row,
    )


def bridge_csv(
    index: CanonicalEntityIndex,
    *,
    path: Path,
    namespace: str,
    name_fields: Iterable[str],
    id_fields: Iterable[str] = (),
) -> list[NamespaceBridgeRecord]:
    if not path.exists():
        return []
    name_fields = tuple(name_fields)
    id_fields = tuple(id_fields)
    out: list[NamespaceBridgeRecord] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        for source_row, row in enumerate(csv.DictReader(handle), start=2):
            name = next(
                (str(row.get(field) or "").strip() for field in name_fields if row.get(field)), ""
            )
            if not name:
                continue
            record_id = next(
                (str(row.get(field) or "").strip() for field in id_fields if row.get(field)), ""
            )
            if not record_id:
                record_id = f"row:{source_row}"
            out.append(
                bridge_name(
                    index,
                    source_namespace=namespace,
                    source_record_id=record_id,
                    source_name=name,
                    source_path=str(path),
                    source_row=source_row,
                )
            )
    return out


def bridge_prepa_graph(index: CanonicalEntityIndex, path: Path) -> list[NamespaceBridgeRecord]:
    """Bridge a PREPA Title III graph JSON produced by the specialized module."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[NamespaceBridgeRecord] = []
    for node in payload.get("nodes") or []:
        name = str(node.get("raw_name") or node.get("normalized_name") or "").strip()
        source_id = str(node.get("entity_id") or "").strip()
        if not name:
            continue
        out.append(
            bridge_name(
                index,
                source_namespace="prepa_titleiii",
                source_record_id=source_id or name,
                source_name=name,
                source_path=str(path),
            )
        )
    return out


def unresolved_collisions(records: Iterable[NamespaceBridgeRecord]) -> list[NamespaceBridgeRecord]:
    """Return only bridge records requiring explicit human adjudication."""
    return [record for record in records if record.bridge_status == "REVIEW"]
