"""Desktop-wrapper configuration for this repo.

The desktop/ folder is a shared PRII federation template; only this file
differs between repos.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Window title of the desktop app.
APP_TITLE = "MoneySweep — PRII Public Money Monitor"

# Dotted import path of the FastAPI application object.
APP_IMPORT = "server.backend.main:app"

# Directory containing the Vite frontend (with package.json).
FRONTEND_DIR = REPO_ROOT / "dashboard"

# Vite build output served by the desktop app.
DIST_DIR = FRONTEND_DIR / "dist"

# Requirement files installed into the private .venv by desktop/setup.py.
REQUIREMENT_FILES = [
    REPO_ROOT / "server" / "backend" / "requirements.txt",
    REPO_ROOT / "requirements-desktop.txt",
]

# Health endpoint used to detect that the backend is up.
HEALTH_PATH = "/health"
