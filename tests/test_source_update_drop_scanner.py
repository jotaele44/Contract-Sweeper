"""Drop-scanner tests for the source update controller."""

from __future__ import annotations

import pytest

from moneysweep.update_controller.drop_scanner import (
    has_new_drop,
    mark_consumed,
    scan_source,
)
from moneysweep.update_controller.models import SourceUpdatePolicy

pytestmark = pytest.mark.unit


def _pol(root_rel="drops") -> SourceUpdatePolicy:
    return SourceUpdatePolicy(
        source_id="beta",
        trigger_type="file_drop",
        enabled=True,
        runner="scripts/ingest_beta.py",
        freshness_sla_hours=2880,
        timeout_minutes=60,
        max_retries=1,
        empty_result_policy="preserve_previous",
        watch_paths=[root_rel],
        filename_patterns=["*.csv"],
        dedupe_method="sha256",
    )


@pytest.fixture()
def dropdir(tmp_path):
    d = tmp_path / "drops"
    d.mkdir()
    return tmp_path


def test_new_file_detected(dropdir):
    (dropdir / "drops" / "a.csv").write_text("x,y\n1,2\n")
    cands = scan_source(_pol(), root=dropdir, consumed_path=dropdir / "consumed.json")
    assert len(cands) == 1
    assert cands[0].is_new is True


def test_same_hash_ignored_after_consumed(dropdir):
    (dropdir / "drops" / "a.csv").write_text("x,y\n1,2\n")
    consumed = dropdir / "consumed.json"
    cands = scan_source(_pol(), root=dropdir, consumed_path=consumed)
    mark_consumed("beta", cands[0].sha256, root=dropdir, consumed_path=consumed)
    again = scan_source(_pol(), root=dropdir, consumed_path=consumed)
    assert again[0].is_new is False
    assert has_new_drop(_pol(), root=dropdir, consumed_path=consumed) is False


def test_changed_content_redetected(dropdir):
    f = dropdir / "drops" / "a.csv"
    f.write_text("x,y\n1,2\n")
    consumed = dropdir / "consumed.json"
    c1 = scan_source(_pol(), root=dropdir, consumed_path=consumed)
    mark_consumed("beta", c1[0].sha256, root=dropdir, consumed_path=consumed)
    f.write_text("x,y\n9,9\n")  # content change → new hash
    c2 = scan_source(_pol(), root=dropdir, consumed_path=consumed)
    assert c2[0].is_new is True


def test_failed_ingestion_does_not_consume(dropdir):
    (dropdir / "drops" / "a.csv").write_text("x,y\n1,2\n")
    consumed = dropdir / "consumed.json"
    # simulate: we scan but do NOT mark_consumed (ingestion failed)
    scan_source(_pol(), root=dropdir, consumed_path=consumed)
    again = scan_source(_pol(), root=dropdir, consumed_path=consumed)
    assert again[0].is_new is True  # still eligible


def test_unsupported_extension_ignored(dropdir):
    (dropdir / "drops" / "note.txt").write_text("ignore me")
    cands = scan_source(_pol(), root=dropdir, consumed_path=dropdir / "consumed.json")
    assert cands == []


def test_symlink_escape_rejected(dropdir, tmp_path):
    outside = tmp_path.parent / "outside_secret.csv"
    outside.write_text("secret\n")
    link = dropdir / "drops" / "link.csv"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unsupported on this platform")
    cands = scan_source(_pol(), root=dropdir, consumed_path=dropdir / "consumed.json")
    assert all(not c.path.endswith("link.csv") for c in cands)
