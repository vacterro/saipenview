"""T-40 / W2-030: SingleInstanceGuard._handoff ignores ACK.

_handoff sent SHOW and returned True without reading the versioned ACK
response. Second launch could not distinguish "live owner heard us" from
"port was just open but nobody answered".

Fix: read ACK (short timeout) after send; return True only if ACK is
present in the response.
"""

from __future__ import annotations

import socket
import threading
import time
from unittest.mock import patch

import pytest

from saipenview.guard import SingleInstanceGuard, _SHOW_ACK, _SHOW_MAGIC


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_guard(port: int) -> SingleInstanceGuard:
    guard = SingleInstanceGuard(port)
    guard.acquire(on_show_request=lambda: None)
    return guard


def test_handoff_reads_ack_and_returns_true():
    """Second instance sends SHOW; owner replies ACK; handoff returns True."""
    port = _free_port()
    owner = _start_guard(port)
    try:
        second = SingleInstanceGuard(port)
        result = second._handoff()
        assert result is True, "_handoff should return True when ACK received"
    finally:
        owner.stop()


def test_handoff_returns_false_when_no_ack():
    """Second instance sends SHOW but owner is gone; handoff returns False."""
    port = _free_port()
    # Owner is acquired then stopped BEFORE second instance connects
    owner = SingleInstanceGuard(port)
    owner.acquire(on_show_request=lambda: None)
    owner.stop()

    second = SingleInstanceGuard(port)
    result = second._handoff()
    assert result is False, "_handoff should return False when no ACK"


def test_full_acquire_second_instance_false_with_ack():
    """Full acquire flow: second instance gets False and shows ACK was read."""
    port = _free_port()
    showed = threading.Event()

    def on_show():
        showed.set()

    owner = SingleInstanceGuard(port)
    owner.acquire(on_show_request=on_show)
    try:
        second = SingleInstanceGuard(port)
        acquired = second.acquire()
        assert acquired is False, "second instance must not acquire"
        # With ACK fix, show callback fires only when ACK is exchanged.
        assert showed.wait(timeout=3), "SHOW callback should fire after ACK exchange"
    finally:
        owner.stop()


def test_handoff_garbage_response_returns_false():
    """Owner sends garbage instead of ACK; handoff returns False."""
    port = _free_port()

    def _garbage_server(port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        try:
            conn, _ = sock.accept()
            conn.settimeout(2.0)
            conn.recv(64)
            conn.sendall(b"GARBAGE\n")
            conn.close()
        except OSError:
            pass
        finally:
            sock.close()

    t = threading.Thread(target=_garbage_server, args=(port,), daemon=True)
    t.start()
    second = SingleInstanceGuard(port)
    result = second._handoff()
    assert result is False, "_handoff should return False on garbage ACK"
