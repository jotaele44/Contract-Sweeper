#!/bin/bash
# Double-click launcher (macOS). First run installs dependencies (needs
# internet once); later runs start the app directly and work offline.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "Python 3 is required. Install it from https://www.python.org/downloads/"
  read -r -p "Press Enter to close…"
  exit 1
fi

"$PYTHON" desktop/setup.py --ensure
exec .venv/bin/python desktop/launch.py "$@"
