#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import hashlib
import json
import shutil
from pathlib import Path

root = Path.cwd()
src = root / "exports" / "centinelas_intake" / "project_fiscal_assertions.jsonl"
pkg = root / "data" / "exports" / "canonical_v1_federation"
dest = pkg / "project_fiscal_assertions.jsonl"

if not src.exists() or not src.read_text(encoding="utf-8").strip():
    raise SystemExit(0)

pkg.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dest)
manifest_path = pkg / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
files = [
    row
    for row in manifest.get("files", [])
    if row.get("stream") != "project_fiscal_assertions"
]
count = sum(1 for line in dest.read_text(encoding="utf-8").splitlines() if line.strip())
sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
files.append(
    {
        "filename": dest.name,
        "stream": "project_fiscal_assertions",
        "record_count": count,
        "sha256": sha256,
        "schema_id": "project_fiscal_assertion/v1",
    }
)
manifest["files"] = files
digest = hashlib.sha256(
    (
        "|".join(
            f"{row['filename']}:{row['sha256']}"
            for row in sorted(files, key=lambda row: str(row["filename"]))
        )
        + f"|{manifest.get('mode', 'test')}"
    ).encode("utf-8")
).hexdigest()[:32]
manifest["package_id"] = f"pkg_{digest}"
manifest_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
