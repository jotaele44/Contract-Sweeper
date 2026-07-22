"""Launch the app as a local desktop window.

Thin shim: the launcher runtime (uvicorn + native window + single-instance lock
+ --smoke CI mode) now lives in the shared ``prii_desktop`` package
(thehub-pr/packages/prii_desktop), consumed as a local path dep so the code is
edited once for the whole federation. Only ``desktop/config.py`` is per-repo.

Flags (--no-window / --browser / --route PATH / --smoke) are handled by
``prii_desktop.launch``. See the package for details.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prii_desktop import DesktopConfig, launch  # noqa: E402

from desktop import config  # noqa: E402


def main() -> None:
    launch(DesktopConfig.from_module(config))


if __name__ == "__main__":
    main()
