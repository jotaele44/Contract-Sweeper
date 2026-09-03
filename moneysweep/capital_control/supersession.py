from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .models import HoldingObservation


@dataclass(frozen=True)
class SupersessionResult:
    active: tuple[HoldingObservation, ...]
    superseded: tuple[HoldingObservation, ...]


def _assert_no_supersession_cycle(by_id: dict[str, HoldingObservation]) -> None:
    for start_id in by_id:
        seen: set[str] = set()
        cursor = start_id
        while cursor in by_id:
            if cursor in seen:
                raise ValueError("supersession cycle detected")
            seen.add(cursor)
            parent = by_id[cursor].supersedes_observation_id
            if parent is None:
                break
            cursor = parent


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

    _assert_no_supersession_cycle(by_id)

    superseded_ids: set[str] = set()
    for row in rows:
        if row.amendment_status == "SUPERSEDED":
            raise ValueError(
                "source rows must express supersession from the replacement observation"
            )
        if row.supersedes_observation_id:
            target = by_id.get(row.supersedes_observation_id)
            if target is None:
                raise ValueError("supersession target not found")
            if target.observation_id == row.observation_id:
                raise ValueError("observation cannot supersede itself")
            if target.issuer_id != row.issuer_id or target.holder_id != row.holder_id:
                raise ValueError("supersession cannot cross holder or issuer identity")
            if (
                target.security_id != row.security_id
                or target.security_class_raw != row.security_class_raw
            ):
                raise ValueError("supersession cannot cross security identity")
            if target.position_class != row.position_class:
                raise ValueError("supersession cannot cross position class")
            if (row.as_of_date, row.report_date) < (target.as_of_date, target.report_date):
                raise ValueError("superseding observation cannot predate target")
            superseded_ids.add(target.observation_id)

    active = tuple(row for row in rows if row.observation_id not in superseded_ids)
    superseded = tuple(
        replace(row, amendment_status="SUPERSEDED")
        for row in rows
        if row.observation_id in superseded_ids
    )
    return SupersessionResult(active=active, superseded=superseded)
