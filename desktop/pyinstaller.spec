# PyInstaller spec for the standalone desktop build (Phase 2).
# Build (on the target OS):
#   pip install pyinstaller
#   pyinstaller desktop/pyinstaller.spec --distpath dist-desktop
# Produces a self-contained one-folder app: dist-desktop/PRII-MONEYSWEEP/
# The bundle mirrors the repo layout so server/backend/main.py finds data/
# and releases/ with its normal relative paths.

import os
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "PRII-MONEYSWEEP"

# Windowed by default (no console window for double-click users). CI sets
# PRII_CONSOLE=1 to build a console binary it can smoke-test with visible stdio.
CONSOLE = os.environ.get("PRII_CONSOLE") == "1"

datas = [
    (str(REPO_ROOT / "dashboard" / "dist"), "dashboard/dist"),
    (str(REPO_ROOT / "data" / "canonical_v1"), "data/canonical_v1"),
]

a = Analysis(
    [str(REPO_ROOT / "desktop" / "launch.py")],
    pathex=[str(REPO_ROOT)],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "desktop.app_server",
        "server.backend.main",
        # Shared desktop-wrapper runtime (thehub-pr/packages/prii_desktop),
        # imported by the desktop/ shims — bundle it into the frozen build.
        "prii_desktop",
        "prii_desktop.launcher",
        "prii_desktop.appserver",
        "prii_desktop.config",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    console=CONSOLE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name=APP_NAME,
)

import sys

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        bundle_identifier="pr.prii.moneysweep",
    )
