"""Unit tests for the desktop launcher helpers (pure — no server needed).

Covers the behaviours that regressed during development: the stdout-safe log(),
the --route display URL, and the single-instance lock.
"""

import io
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import launch  # noqa: E402


def test_display_url_plain():
    assert launch.display_url("http://127.0.0.1:9", []) == "http://127.0.0.1:9"


def test_display_url_route_leading_slash():
    assert (
        launch.display_url("http://127.0.0.1:9", ["--route", "/launcher"])
        == "http://127.0.0.1:9/launcher"
    )


def test_display_url_route_no_slash():
    assert (
        launch.display_url("http://127.0.0.1:9", ["--route", "launcher"])
        == "http://127.0.0.1:9/launcher"
    )


def test_log_is_safe_when_stdout_none(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    launch.log("must not raise")  # regression: bare print() raised on frozen builds


def test_log_writes_and_flushes(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    launch.log("hello")
    assert buf.getvalue() == "hello\n"


def test_free_port_is_bindable():
    port = launch.free_port()
    assert isinstance(port, int)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))  # would raise if not actually free


def test_wait_healthy_raises_on_closed_port():
    port = launch.free_port()
    with pytest.raises(SystemExit):
        launch.wait_healthy(f"http://127.0.0.1:{port}/health", timeout=0.5)


def test_single_instance_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".running"
    monkeypatch.setattr(launch, "LOCK_FILE", lock)

    assert launch.running_instance_url() is None  # no lock yet

    launch.write_lock("http://127.0.0.1:1234")
    assert launch.running_instance_url() == "http://127.0.0.1:1234"  # our pid is alive

    # A stale pid clears the lock and reports no instance.
    lock.write_text(json.dumps({"pid": 2**31 - 1, "url": "x"}), encoding="utf-8")
    assert launch.running_instance_url() is None
    assert not lock.exists()

    launch.write_lock("u")
    launch.clear_lock()
    assert not lock.exists()
