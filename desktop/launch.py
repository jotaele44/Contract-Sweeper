"""Launch MoneySweep as a local desktop window.

The shared ``prii_desktop`` package owns the uvicorn/native-window lifecycle.
MoneySweep adds one mandatory pre-launch step: bootstrap a writable per-user
workspace outside the immutable application bundle. The backend then reads and
writes through ``MONEYSWEEP_DATA_ROOT`` instead of mutating packaged resources.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prii_desktop import DesktopConfig, launch  # noqa: E402

from desktop import config  # noqa: E402
from desktop.workspace import bootstrap_workspace  # noqa: E402


def main() -> None:
    bootstrap_workspace()
    launch(DesktopConfig.from_module(config))


if __name__ == "__main__":
    main()
