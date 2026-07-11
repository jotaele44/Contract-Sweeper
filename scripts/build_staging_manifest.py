"""Build a committed row-count manifest for the gitignored staging masters.

The materialized masters under ``data/staging/processed/*.csv`` are gitignored
(too large to commit — ``pr_grants_master.csv`` alone is ~143 MB, and the
``size-guard`` gate caps tracked files at 5 MiB). That means a clean CI checkout
sees zero rows and the committed coverage reports read 0%, even though the data
exists locally.

This manifest records ``{row_count, sha256, size_bytes, generated_at}`` per
processed CSV under ``data/manifests/staging_masters.json`` (which IS tracked).
``gap_analysis_builder._file_status`` falls back to this manifest when a declared
output is absent, so committed reports reflect real coverage without committing
the bulk data.

Merge semantics (default): entries for files that are absent locally are
PRESERVED from the committed manifest — a partial checkout (e.g. this repo's
deny-all ``data/`` gitignore) must never erase another environment's recorded
holdings. Files present locally are re-measured and updated. Pass ``--prune``
to intentionally drop entries whose files are absent.

    python3 scripts/build_staging_manifest.py            # merge (safe default)
    python3 scripts/build_staging_manifest.py --prune    # rebuild from disk only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "staging" / "processed"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "staging_masters.json"


def _csv_row_count(path: Path) -> int:
    """Data rows (excluding the header); -1 if unreadable.

    Uses csv.reader so quoted multi-line fields are counted correctly.
    """
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except OSError:
        return -1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _existing_files(root: Path) -> dict[str, dict]:
    path = root / "data" / "manifests" / "staging_masters.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        return {}


def build_manifest(root: Path = PROJECT_ROOT, *, prune: bool = False) -> dict:
    processed = root / "data" / "staging" / "processed"
    # Merge default: start from the committed entries so a partial checkout
    # never erases holdings recorded elsewhere; --prune rebuilds from disk only.
    files: dict[str, dict] = {} if prune else dict(_existing_files(root))
    for p in sorted(processed.glob("*.csv")):
        rel = p.relative_to(root).as_posix()
        files[rel] = {
            "row_count": _csv_row_count(p),
            "sha256": _sha256(p),
            "size_bytes": p.stat().st_size,
        }
    return {
        "schema_version": "staging_masters_v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Row counts for the gitignored data/staging/processed masters. "
            "Committed source of truth for coverage reports in a clean checkout "
            "(the CSVs themselves are too large to track — see size-guard). "
            "Regenerate with scripts/build_staging_manifest.py after a data refresh."
        ),
        "files": {rel: files[rel] for rel in sorted(files)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="drop manifest entries whose files are absent locally "
        "(default merges: absent files keep their committed entries)",
    )
    args = parser.parse_args(argv)
    manifest = build_manifest(PROJECT_ROOT, prune=args.prune)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    n = len(manifest["files"])
    total = sum(v["row_count"] for v in manifest["files"].values() if v["row_count"] > 0)
    print(f"wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} — {n} files, {total:,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
