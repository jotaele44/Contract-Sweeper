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

import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.config import APP_TITLE, HEALTH_PATH  # noqa: E402


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int) -> "uvicorn.Server":
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
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    server = start_server(port)
    wait_healthy(url + HEALTH_PATH)

    if "--smoke" in args:
        print(f"smoke ok: {url}{HEALTH_PATH}")
        server.should_exit = True
        return

    if "--no-window" in args:
        print(f"{APP_TITLE} running at {url} (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.should_exit = True
        return

    if "--browser" not in args:
        try:
            import webview

            webview.create_window(APP_TITLE, url, width=1280, height=860)
            webview.start()
            server.should_exit = True
            return
        except Exception as exc:  # noqa: BLE001 - fall back to the browser
            print(f"pywebview unavailable ({exc}); opening the default browser.")

    import webbrowser

    webbrowser.open(url)
    print(f"{APP_TITLE} running at {url} — close this window/Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == "__main__":
    main()
