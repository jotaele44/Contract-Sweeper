# Run MONEYSWEEP as a desktop app

Double-click the launcher for your system in the repo root:

| System | File |
|---|---|
| macOS | `PRII-MONEYSWEEP.command` |
| Windows | `PRII-MONEYSWEEP.bat` |
| Linux | `PRII-MONEYSWEEP.sh` |

The **first run** needs an internet connection once: it creates a private
`.venv`, installs the Python dependencies, and builds the dashboard
(requires [Python 3.11+](https://www.python.org/downloads/) and
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

## macOS app icon

`PRII-MONEYSWEEP.app` is a double-click macOS app (Apple-silicon and Intel). Double-click
it in Finder and the dashboard opens in its own window — no Terminal. The first
launch runs the one-time setup (needs internet once, plus Node.js for the
dashboard build); after that it starts straight away and works offline.

Because the app is a small self-locating wrapper around `desktop/launch.py`, it
must stay at the repo root (it finds the repo from its own location). If macOS
blocks the first open, see **If macOS won't open the app** below.
No-Python-required standalone builds are still produced separately by the
`desktop-build` workflow.

## If macOS won't open the app

The app is safe — it's an open-source launcher script you can read in
`Contents/MacOS/`. macOS blocks it only because it isn't signed with a paid
Apple Developer ID or notarized by Apple, so the first open may show *"cannot be
opened because Apple cannot check it for malicious software"* or an
*"unidentified developer"* notice. That's macOS quarantining files downloaded
from the internet (it happens especially with GitHub's **Download ZIP**). Any
one of the following clears it — you only do this once per download:

- **Easiest — run the helper.** Double-click **`Fix-Gatekeeper.command`** in the
  repo root, then open the app normally. If the helper is itself blocked,
  right-click it → **Open** to run it once.
- **Terminal (always works).** Paste this into Terminal (pasting a command is
  never blocked), then press Return:
  ```bash
  xattr -dr com.apple.quarantine "/path/to/moneysweep-pr/PRII-MONEYSWEEP.app"
  ```
  Tip: type `xattr -dr com.apple.quarantine ` (with a trailing space) and drag
  the app onto the Terminal window to fill in its path.
- **System Settings.** Double-click the app, let macOS block it, then open
  **System Settings → Privacy & Security**, scroll to the message naming the app,
  and click **Open Anyway**. On macOS Sequoia 15 and later this replaces the old
  right-click → **Open** trick.

### "First-run setup could not finish" after Open Anyway

**Open Anyway** permits *this one launch*; it does not clear the quarantine
flag. While that flag is set, macOS keeps running the app from a throwaway
read-only copy under `/private/var/folders/…/AppTranslocation/…` — and only the
`.app` is copied there, so the checkout it needs is missing and no `.venv` can
be written. The app now detects this and names the real cause instead of
blaming the network.

Clear the quarantine rather than only permitting the launch: run
`Fix-Gatekeeper.command`, or the `xattr -dr` command above, or move the folder
somewhere else in Finder. Moving it defeats translocation on its own, which is
why dragging the folder out of Downloads (or the Trash) is usually quickest.

Genuine setup failures — no internet on the first run, or Node.js missing —
retain their output in a unique
`$TMPDIR/prii-moneysweep-pr-setup.XXXXXX` file, and the failure message names
that file. Successful setup logs are removed before the desktop process starts.
