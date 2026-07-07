"""Launch the app as a local desktop window.

Starts uvicorn on a free localhost port in a background thread, waits for the
backend health endpoint, then opens a native window (pywebview). Falls back to
the default browser when pywebview is unavailable.

Flags:
  --no-window   serve only; print the URL and block (Ctrl+C to stop)
  --browser     skip pywebview and open the default browser
  --smoke       start, verify health, exit 0 (used by CI and setup checks)
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Frozen windowed builds can leave the standard streams as None; give every
# library (uvicorn logging, asyncio) a real sink so nothing deadlocks or raises
# on a missing stream.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name, None) is None:
        setattr(sys, _name, open(os.devnull, "w"))  # noqa: SIM115

from desktop.config import APP_TITLE, HEALTH_PATH  # noqa: E402


def log(message: str) -> None:
    """Print without ever raising.

    Frozen windowed builds (notably on Windows) have sys.stdout/stderr set to
    None, so a bare print() raises AttributeError. If that happened before the
    os._exit() in finish(), the process would hang on non-daemon asyncio
    executor threads until it was killed. Route all output through here.
    """
    stream = sys.stdout
    if stream is None:
        return
    try:
        stream.write(f"{message}\n")
        stream.flush()
    except Exception:  # noqa: BLE001 - logging must never break control flow
        pass


def finish(server) -> None:
    """Stop the server and end the process, including lingering threads.

    In frozen (PyInstaller) builds — notably windowed Windows exes — event-loop
    threads can keep the process alive after main() returns, so every terminal
    path must end the process explicitly.
    """
    server.should_exit = True
    time.sleep(0.3)
    os._exit(0)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int):
    import uvicorn

    from desktop.app_server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()
    return server


def wait_healthy(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - retried until deadline
            last_error = exc
        time.sleep(0.2)
    raise SystemExit(f"Backend did not become healthy at {url}: {last_error}")


def main() -> None:
    args = set(sys.argv[1:])
    argv = sys.argv[1:]
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    # Optional --route <path> opens the window/browser on a specific client
    # route (e.g. the federation launcher at /launcher) while health checks
    # still target the server root.
    url = base
    if "--route" in argv:
        route = argv[argv.index("--route") + 1]
        url = base + "/" + route.lstrip("/")

    server = start_server(port)

    if "--smoke" in args:
        # Absolute backstop: a frozen build must never hang the CI job. If the
        # normal exit below is somehow not reached, force-terminate.
        def _watchdog() -> None:
            time.sleep(60)
            os._exit(2)

        threading.Thread(target=_watchdog, name="smoke-watchdog", daemon=True).start()

        # Self-contained so os._exit() always runs — even if the health check
        # fails — so a frozen build can never hang CI on lingering threads.
        try:
            wait_healthy(base + HEALTH_PATH)
            log(f"smoke ok: {base}{HEALTH_PATH}")
            code = 0
        except BaseException as exc:  # noqa: BLE001 - report and exit non-zero
            log(f"smoke failed: {exc}")
            code = 1
        server.should_exit = True
        time.sleep(0.3)
        os._exit(code)

    wait_healthy(base + HEALTH_PATH)

    if "--no-window" in args:
        log(f"{APP_TITLE} running at {url} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            finish(server)
        return

    if "--browser" not in args:
        try:
            import webview

            webview.create_window(APP_TITLE, url, width=1280, height=860)
            webview.start()
            finish(server)
        except Exception as exc:  # noqa: BLE001 - fall back to the browser
            log(f"pywebview unavailable ({exc}); opening the default browser.")

    import webbrowser

    webbrowser.open(url)
    log(f"{APP_TITLE} running at {url} — close this window/Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        finish(server)


if __name__ == "__main__":
    main()
