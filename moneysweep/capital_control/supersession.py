from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .models import HoldingObservation


@dataclass(frozen=True)
class SupersessionResult:
    active: tuple[HoldingObservation, ...]
    superseded: tuple[HoldingObservation, ...]


def apply_supersession(observations: Iterable[HoldingObservation]) -> SupersessionResult:
    rows = tuple(observations)
    by_id = {row.observation_id: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate observation_id")

    source_record_keys: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.source_id, row.source_record_id)
        if key in source_record_keys:
            raise ValueError("duplicate source_id/source_record_id")
        source_record_keys.add(key)

    superseded_ids: set[str] = set()
    for row in rows:
        if row.supersedes_observation_id:
            target = by_id.get(row.supersedes_observation_id)
            if target is None:
                raise ValueError("supersession target not found")
            if target.observation_id == row.observation_id:
                raise ValueError("observation cannot supersede itself")
            if target.issuer_id != row.issuer_id or target.holder_id != row.holder_id:
                raise ValueError("supersession cannot cross holder or issuer identity")
            superseded_ids.add(target.observation_id)

    active = tuple(row for row in rows if row.observation_id not in superseded_ids and row.amendment_status != "SUPERSEDED")
    superseded = tuple(
        replace(row, identity_status="SUPERSEDED") if row.identity_status != "SUPERSEDED" else row
        for row in rows
        if row.observation_id in superseded_ids or row.amendment_status == "SUPERSEDED"
    )
    return SupersessionResult(active=active, superseded=superseded)
