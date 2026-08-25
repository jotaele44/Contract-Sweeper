# PyInstaller spec for the standalone MoneySweep desktop build.
# Build (on the target OS):
#   pip install pyinstaller
#   pyinstaller desktop/pyinstaller.spec --distpath dist-desktop
#
# The frozen application is self-contained: Python, the dashboard, the complete
# MoneySweep runtime, source registry/schema metadata, and seed canonical data
# are inside the bundle. Mutable data is never written into the bundle; the
# launcher bootstraps a per-user Application-Support workspace.

import json
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "PRII-MONEYSWEEP"

BRANDING = REPO_ROOT / "assets" / "branding"
EXE_ICON = str(BRANDING / "icon.ico") if sys.platform == "win32" else None
CONSOLE = os.environ.get("PRII_CONSOLE") == "1"

# Immutable resources needed by the desktop data plane. Keep mutable raw,
# staging and manual payloads out of the application bundle.
datas = [
    (str(REPO_ROOT / "dashboard" / "dist"), "dashboard/dist"),
    (str(REPO_ROOT / "data" / "canonical_v1"), "data/canonical_v1"),
    (str(REPO_ROOT / "registries"), "registries"),
    (str(REPO_ROOT / "schemas"), "schemas"),
    (
        str(REPO_ROOT / "reports" / "materialization_readiness.json"),
        "reports",
    ),
    (
        str(REPO_ROOT / "data" / "exports" / "production_status.json"),
        "data/exports",
    ),
]


def _producer_modules_from_registry() -> list[str]:
    """Discover the exact dynamic-producer candidate set from registry JSON.

    PyInstaller cannot see importlib-loaded producer modules. Do not freeze the
    entire scripts package heuristically: preserve the full declared candidate
    set and add exactly each declared producer module as a hidden import.
    """
    modules: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            producer = value.get("producer_script")
            if isinstance(producer, str) and producer.strip():
                name = producer.strip()
                if name.endswith(".py"):
                    name = name[:-3]
                modules.add(name.replace("/", ".").replace("\\", "."))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    registry_root = REPO_ROOT / "registries"
    candidates = [registry_root / "source_registry.json"]
    candidates += sorted((registry_root / "source_registry_extensions").glob("*.json"))
    candidates += sorted((registry_root / "source_registry_overrides").glob("*.json"))
    for path in candidates:
        if not path.exists():
            continue
        walk(json.loads(path.read_text(encoding="utf-8")))
    if not modules:
        raise RuntimeError("source registry yielded zero producer modules")
    return sorted(modules)


producer_hiddenimports = _producer_modules_from_registry()

hiddenimports = sorted(
    set(
        collect_submodules("moneysweep")
        + collect_submodules("server.backend")
        + producer_hiddenimports
        + [
            "scripts.run_automatable_sources",
            "scripts.build_source_recovery_matrix",
            "scripts.check_network_egress",
            "scripts.config",
            "uvicorn.logging",
            "uvicorn.loops.auto",
            "uvicorn.protocols.http.auto",
            "uvicorn.protocols.websockets.auto",
            "uvicorn.lifespan.on",
            "desktop.app_server",
            "desktop.workspace",
            "server.backend.desktop_app",
            "server.backend.materialization",
            "prii_desktop",
            "prii_desktop.launcher",
            "prii_desktop.appserver",
            "prii_desktop.config",
        ]
    )
)

a = Analysis(
    [str(REPO_ROOT / "desktop" / "launch.py")],
    pathex=[str(REPO_ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    console=CONSOLE,
    icon=EXE_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(BRANDING / "AppIcon.icns"),
        bundle_identifier="pr.prii.moneysweep",
    )
