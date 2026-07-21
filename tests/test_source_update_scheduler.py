from __future__ import annotations

import pytest

from moneysweep.update_controller.models import UpdatePlanItem
from moneysweep.update_controller.scheduler import (
    execution_lane_key,
    group_wave_by_lane,
    topological_waves,
)

pytestmark = pytest.mark.unit


def _item(source_id: str, *, order: int, depends_on=(), trigger="schedule"):
    return UpdatePlanItem(
        source_id=source_id,
        trigger_type=trigger,
        due=True,
        reason="test",
        enabled=True,
        order_index=order,
        depends_on=list(depends_on),
    )


def test_topological_waves_keep_dependencies_in_later_waves():
    items = [
        _item("root_a", order=0),
        _item("root_b", order=1),
        _item("child", order=2, depends_on=("root_a",)),
        _item("leaf", order=3, depends_on=("child", "root_b")),
    ]
    assert [[item.source_id for item in wave] for wave in topological_waves(items)] == [
        ["root_a", "root_b"],
        ["child"],
        ["leaf"],
    ]


def test_topological_waves_reject_cycle():
    items = [
        _item("a", order=0, depends_on=("b",)),
        _item("b", order=1, depends_on=("a",)),
    ]
    with pytest.raises(ValueError, match="dependency cycle"):
        topological_waves(items)


def test_same_host_and_drop_sources_share_serial_lanes():
    a = _item("a", order=0)
    b = _item("b", order=1)
    drop = _item("drop", order=2, trigger="file_drop")
    registry = {
        "a": {"endpoint_url": "https://api.usaspending.gov/a"},
        "b": {"endpoint_url": "https://api.usaspending.gov/b"},
        "drop": {},
    }
    assert execution_lane_key(a, registry["a"]) == execution_lane_key(b, registry["b"])
    assert execution_lane_key(drop, {}) == "file-drop"
    lanes = group_wave_by_lane([a, b, drop], registry)
    assert sorted(len(lane) for lane in lanes) == [1, 2]
