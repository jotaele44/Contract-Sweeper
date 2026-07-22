"""Same-origin ASGI app for the desktop wrapper.

Thin shim: the SPA-serving wrapper (reuse the repo's FastAPI backend + serve the
built Vite frontend from the same port) now lives in the shared ``prii_desktop``
package. This module keeps exposing ``app`` so existing importers (and the
PyInstaller spec's ``desktop.app_server`` hidden import) keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prii_desktop import DesktopConfig, make_desktop_app  # noqa: E402

from desktop import config  # noqa: E402

app = make_desktop_app(DesktopConfig.from_module(config))
