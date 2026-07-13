#!/usr/bin/env python3
"""Generate dashboard/src/lib/snapshot.json for the offline (VITE_OFFLINE) export.

The standalone `file://` build cannot fetch, so `dashboard/src/lib/api.js` resolves
each endpoint from an embedded snapshot keyed by request path (query string
stripped). This script calls the backend's endpoint functions directly (they are
plain functions returning JSON-safe data) and dumps those paths, so
`npm run build:export` ships a dashboard with data baked in instead of empty
fallbacks. Calling the functions directly avoids the FastAPI TestClient, which
would pull in a test-only `httpx` dependency the runtime install doesn't declare.

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

from server.backend import main as backend  # noqa: E402

# Map each snapshot key (the query-string-stripped path api.js looks up) to the
# backend endpoint function that produces it. Defaults yield the unfiltered set.
ENDPOINTS = {
    "/health": backend.health,
    "/contracts": backend.contracts,
    "/entities": backend.entities,
    "/edges": backend.edges,
    "/municipalities": backend.municipalities,
    "/stats": backend.stats,
}

OUT = _ROOT / "dashboard" / "src" / "lib" / "snapshot.json"


def main() -> None:
    snapshot = {path: fn() for path, fn in ENDPOINTS.items()}
    OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    counts = {p: (len(v) if isinstance(v, list) else 1) for p, v in snapshot.items()}
    print(f"wrote {OUT.relative_to(Path.cwd())}  {counts}")


if __name__ == "__main__":
    main()
