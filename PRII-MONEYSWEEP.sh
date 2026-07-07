#!/bin/sh
# Launcher (Linux). Double-click where your file manager allows executing
# scripts, or run ./PRII-MONEYSWEEP.sh. First run installs dependencies (needs
# internet once); later runs start the app directly and work offline.
set -eu
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required (e.g. sudo apt install python3 python3-venv)."
  exit 1
fi

python3 desktop/setup.py --ensure
exec .venv/bin/python desktop/launch.py "$@"
