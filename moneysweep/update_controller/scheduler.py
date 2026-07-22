"""Dependency-safe batching helpers for concurrent source updates."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from moneysweep.update_controller.models import UpdatePlanItem


def execution_lane_key(item: UpdatePlanItem, registry_entry: dict[str, Any]) -> str:
    """Return the serialization lane for a source.

    Sources sharing an upstream hostname run sequentially to avoid multiplying
    rate-limit pressure. File-drop consumers also share one lane because they
    can touch the same intake/consumed manifests. Local producers remain
    independent unless the registry gives them a shared endpoint.
    """
    if item.trigger_type in {"file_drop", "on_drop"}:
        return "file-drop"
    endpoint = str(registry_entry.get("endpoint_url") or "").strip()
    hostname = urlparse(endpoint).hostname
    if hostname:
        return f"host:{hostname.lower()}"
    return f"local:{item.source_id}"


def topological_waves(items: Iterable[UpdatePlanItem]) -> list[list[UpdatePlanItem]]:
    """Partition a plan into deterministic waves with no intra-wave dependency."""
    remaining = {item.source_id: item for item in items}
    waves: list[list[UpdatePlanItem]] = []
    completed: set[str] = set()

    while remaining:
        ready = [
            item
            for item in remaining.values()
            if all(dep not in remaining or dep in completed for dep in item.depends_on)
        ]
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise ValueError(f"dependency cycle in selected update plan: {cycle}")
        ready.sort(key=lambda item: (item.order_index, item.source_id))
        waves.append(ready)
        for item in ready:
            completed.add(item.source_id)
            del remaining[item.source_id]

    return waves


def group_wave_by_lane(
    wave: Iterable[UpdatePlanItem], registry: dict[str, dict[str, Any]]
) -> list[list[UpdatePlanItem]]:
    """Group a wave into stable serial lanes ready for a worker pool."""
    lanes: dict[str, list[UpdatePlanItem]] = {}
    for item in wave:
        key = execution_lane_key(item, registry.get(item.source_id, {}))
        lanes.setdefault(key, []).append(item)
    return [lanes[key] for key in sorted(lanes)]
