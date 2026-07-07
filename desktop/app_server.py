"""Same-origin ASGI app for the desktop wrapper.

Reuses the repo's existing FastAPI backend and additionally serves the built
Vite frontend from the same port, so the desktop app needs exactly one local
server and no CORS. API routes keep priority because they were registered on
the app before the catch-all below.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.responses import FileResponse  # noqa: E402
from server.backend.main import app  # noqa: E402

from desktop.config import DIST_DIR  # noqa: E402


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """Serve built frontend files, falling back to index.html for SPA routes."""
    index = DIST_DIR / "index.html"
    if not index.is_file():
        raise RuntimeError(f"Frontend build not found at {DIST_DIR}. Run: python desktop/setup.py")
    if full_path:
        candidate = (DIST_DIR / full_path).resolve()
        # Keep path traversal inside the dist directory.
        if candidate.is_file() and candidate.is_relative_to(DIST_DIR.resolve()):
            return FileResponse(candidate)
    return FileResponse(index)
