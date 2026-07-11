"""Thin CLI wrapper for the registry-driven source update controller.

All logic lives in ``moneysweep.update_controller``; this entrypoint only wires
the package CLI so it can be run as ``python scripts/update_sources.py <cmd>``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moneysweep.update_controller.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
