from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts import build_source_drop_manifest as manifest


def test_source_drop_manifest_records_hash_rows_and_stage_copy(tmp_path: Path, monkeypatch):
    source = tmp_path / "external" / "rows.csv"
    source.parent.mkdir(parents=True)
    source.write_text("name,amount\nA,1\nB,2\n", encoding="utf-8")
    repo = tmp_path / "repo"
    monkeypatch.setattr(manifest, "REPO_ROOT", repo)
    monkeypatch.setattr(
        manifest,
        "DROP_SOURCES",
        [
            {
                "source_id": "oce",
                "classification": "FOUND",
                "inclusion_decision": "stage_for_existing_dropzone",
                "path": source,
                "target_relpath": "data/raw/OCE/rows.csv",
                "blocker": "test blocker",
            }
        ],
    )

    records = manifest.build_records(stage=True)
    assert records[0]["logical_rows"] == 2
    assert records[0]["staged"] is True
    assert (repo / "data/raw/OCE/rows.csv").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )

    out = tmp_path / "out"
    manifest.write_outputs(records, out, stage=True)
    payload = json.loads((out / "moneysweep_source_drop_manifest.json").read_text())
    assert payload["arithmetic"]["total"] == 1
    with (out / "moneysweep_source_drop_manifest.csv").open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle))[0]["source_id"] == "oce"
