#!/usr/bin/env python3
"""Append MoneySweep project fiscal assertions to the existing Hub package.

The stream is additive and producer-specific. Hub validation still verifies its
bytes and row count; project identity adjudication happens only in TheHub.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "exports" / "centinelas_intake" / "project_fiscal_assertions.jsonl"
PKG = ROOT / "data" / "exports" / "canonical_v1_federation"
DEST = PKG / "project_fiscal_assertions.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not SRC.exists() or not SRC.read_text(encoding="utf-8").strip():
        return 0
    PKG.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DEST)
    manifest_path = PKG / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = [f for f in manifest.get("files", []) if f.get("stream") != "project_fiscal_assertions"]
    count = sum(1 for line in DEST.read_text(encoding="utf-8").splitlines() if line.strip())
    files.append(
        {
            "filename": DEST.name,
            "stream": "project_fiscal_assertions",
            "record_count": count,
            "sha256": sha256(DEST),
            "schema_id": "project_fiscal_assertion/v1",
        }
    )
    manifest["files"] = files
    digest = hashlib.sha256(
        (
            "|".join(
                f"{f['filename']}:{f['sha256']}" for f in sorted(files, key=lambda x: str(x["filename"]))
            )
            + f"|{manifest.get('mode', 'test')}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    manifest["package_id"] = f"pkg_{digest}"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
