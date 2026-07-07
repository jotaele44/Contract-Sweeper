# Run MONEYSWEEP as a desktop app

Double-click the launcher for your system in the repo root:

| System | File |
|---|---|
| macOS | `PRII-MONEYSWEEP.command` |
| Windows | `PRII-MONEYSWEEP.bat` |
| Linux | `PRII-MONEYSWEEP.sh` |

The **first run** needs an internet connection once: it creates a private
`.venv`, installs the Python dependencies, and builds the dashboard
(requires [Python 3.10+](https://www.python.org/downloads/) and
[Node.js](https://nodejs.org) to be installed). Every later run starts
instantly and **works offline** — the app serves the data committed in this
repository from a local server and shows it in a native window.

Offline caveat: map basemap tiles are fetched from the internet
(OpenStreetMap), so without a connection the map background is blank while
all data, tables, and charts keep working.

## How it works

- `desktop/config.py` — the only per-repo file (title, paths, requirements).
- `desktop/app_server.py` — reuses the existing FastAPI backend and also
  serves the built dashboard from the same port (no CORS, one process).
- `desktop/launch.py` — picks a free port, starts uvicorn, opens a native
  [pywebview](https://pywebview.flowrl.com/) window (falls back to the
  default browser). Flags: `--no-window`, `--browser`, `--smoke`.
- `desktop/setup.py` — idempotent one-time setup (`--force` to redo).

## Command line

```bash
python desktop/setup.py          # one-time setup
.venv/bin/python desktop/launch.py            # native window
.venv/bin/python desktop/launch.py --browser  # browser tab instead
.venv/bin/python desktop/launch.py --no-window  # server only
```
