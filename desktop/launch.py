"""Launch the app as a local desktop window.

Starts uvicorn on a free localhost port in a background thread, waits for the
backend health endpoint, then opens a native window (pywebview) — showing a
"starting…" splash until the backend is ready. Falls back to the default
browser when pywebview is unavailable.

Flags:
  --no-window   serve only; print the URL and block (Ctrl+C to stop)
  --browser     skip pywebview and open the default browser
  --route PATH  open the window/browser on a client route (e.g. /launcher)
  --smoke       start, verify health, exit 0 (used by CI and setup checks)
"""

from __future__ import annotations

import contextlib
import json
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

# Records the running instance (pid + url) so a second double-click reuses it
# instead of starting another server. Lives beside this file; gitignored.
LOCK_FILE = Path(__file__).resolve().parent / ".running"


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


def display_url(base: str, argv: list[str]) -> str:
    """Build the URL to open in the window/browser.

    --route <path> opens a specific client route (e.g. the federation launcher
    at /launcher); health checks still target the server root (base).
    """
    if "--route" in argv:
        route = argv[argv.index("--route") + 1]
        return base + "/" + route.lstrip("/")
    return base


def running_instance_url() -> str | None:
    """Return the URL of a live prior instance, or None (and clean stale locks)."""
    try:
        data = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        pid = int(data["pid"])
    except Exception:  # noqa: BLE001 - missing/garbled lock == no instance
        return None
    try:
        os.kill(pid, 0)  # signal 0 just checks existence
    except OSError:
        LOCK_FILE.unlink(missing_ok=True)
        return None
    return data.get("url")


def write_lock(url: str) -> None:
    payload = json.dumps({"pid": os.getpid(), "url": url})
    with contextlib.suppress(Exception):  # the lock is best-effort
        LOCK_FILE.write_text(payload, encoding="utf-8")


def clear_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def finish(server) -> None:
    """Stop the server and end the process, including lingering threads.

    In frozen (PyInstaller) builds — notably windowed Windows exes — event-loop
    threads can keep the process alive after main() returns, so every terminal
    path must end the process explicitly.
    """
    clear_lock()
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


# Kept as short pieces so every source line stays within strict line-length lints.
_FONT = "-apple-system,Segoe UI,Roboto,sans-serif"
_PAGE_CSS = (
    "html,body{height:100%;margin:0}"
    "body{display:flex;flex-direction:column;align-items:center;"
    f"justify-content:center;font-family:{_FONT};background:#0f172a;color:#e2e8f0;"
    "text-align:center;padding:0 32px}"
    "h1{font-size:17px;margin:0 0 10px}"
    "p{color:#94a3b8;font-size:13px;max-width:34rem}"
    "code{background:#1e293b;padding:2px 6px;border-radius:4px}"
    ".spin{width:34px;height:34px;border:4px solid #334155;border-top-color:#818cf8;"
    "border-radius:50%;animation:s .8s linear infinite;margin-bottom:18px}"
    "@keyframes s{to{transform:rotate(360deg)}}"
)


def _page(body: str) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<style>{_PAGE_CSS}</style></head><body>{body}</body></html>"
    )


def _splash_html(message: str) -> str:
    return _page(f'<div class="spin"></div><p>Starting {message}…</p>')


def _error_html(message: str, detail: str) -> str:
    return _page(
        f"<h1>{message} could not start</h1>"
        "<p>The local server did not become ready. Try again, or run "
        "<code>python desktop/setup.py</code> from the repo to repair it.</p>"
        f'<p style="color:#64748b">{detail}</p>'
    )


def _run_window(server, base: str, url: str) -> None:
    """Open a native window on a splash, then load the app once it is healthy."""
    import webview

    window = webview.create_window(APP_TITLE, html=_splash_html(APP_TITLE), width=1280, height=860)

    def _on_ready() -> None:
        try:
            wait_healthy(base + HEALTH_PATH)
            write_lock(url)
            window.load_url(url)
        except BaseException as exc:  # noqa: BLE001 - show a friendly page, keep window open
            log(f"backend failed to start: {exc}")
            window.load_html(_error_html(APP_TITLE, str(exc)))

    webview.start(_on_ready)
    finish(server)


def _block_until_interrupt(server) -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        finish(server)


def main() -> None:
    args = set(sys.argv[1:])
    argv = sys.argv[1:]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    url = display_url(base, argv)

    # Single-instance guard: for user-facing launches, reuse a running instance
    # (open its URL) instead of starting a second server. Dev modes are exempt.
    if not (args & {"--smoke", "--no-window"}):
        existing = running_instance_url()
        if existing:
            import webbrowser

            log(f"{APP_TITLE} is already running at {existing}")
            webbrowser.open(existing)
            return

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

    if "--no-window" in args:
        wait_healthy(base + HEALTH_PATH)
        log(f"{APP_TITLE} running at {url} (Ctrl+C to stop)")
        _block_until_interrupt(server)
        return

    if "--browser" not in args:
        try:
            _run_window(server, base, url)
            return
        except Exception as exc:  # noqa: BLE001 - fall back to the browser
            log(f"pywebview unavailable ({exc}); opening the default browser.")

    import webbrowser

    wait_healthy(base + HEALTH_PATH)
    write_lock(url)
    webbrowser.open(url)
    log(f"{APP_TITLE} running at {url} — close this window/Ctrl+C to stop.")
    _block_until_interrupt(server)


if __name__ == "__main__":
    main()
