#!/usr/bin/env python3
"""Generate dashboard/src/lib/snapshot.json for the offline (VITE_OFFLINE) export.

The standalone `file://` build cannot fetch, so `dashboard/src/lib/api.js` resolves
each endpoint from an embedded snapshot keyed by request path (query string
stripped). This script drives the real FastAPI app in-process via TestClient and
dumps those paths, so `npm run build:export` ships a dashboard with data baked in
instead of empty fallbacks.

Usage (from repo root):
    python scripts/gen_dashboard_snapshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))  # allow `import server...` regardless of CWD

from fastapi.testclient import TestClient

from server.backend.main import app

# Paths mirror the query-string-stripped keys api.js looks up in the snapshot.
PATHS = ["/health", "/contracts", "/entities", "/edges", "/municipalities", "/stats"]

OUT = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "lib" / "snapshot.json"


def main() -> None:
    client = TestClient(app)
    snapshot: dict[str, object] = {}
    for path in PATHS:
        res = client.get(path)
        res.raise_for_status()
        snapshot[path] = res.json()
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    counts = {p: (len(v) if isinstance(v, list) else 1) for p, v in snapshot.items()}
    print(f"wrote {OUT.relative_to(Path.cwd())}  {counts}")


if __name__ == "__main__":
    main()
