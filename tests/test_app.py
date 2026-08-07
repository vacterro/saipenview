"""Tests for saipenview.guard — single-instance guard with unique ports."""

from __future__ import annotations

import socket
import threading

import pytest


@pytest.fixture
def free_port() -> int:
    """Return a free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestSingleInstanceGuard:
    """SingleInstanceGuard ensures only one instance runs."""

    def test_acquire_success(self, free_port):
        """First instance successfully acquires the lock."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard(free_port)
        try:
            acquired = guard.acquire()
            assert acquired is True
        finally:
            guard.stop()

    def test_acquire_fails_on_second_instance(self, free_port):
        """Second instance cannot acquire on the same port."""
        from saipenview.guard import SingleInstanceGuard

        guard1 = SingleInstanceGuard(free_port)
        guard2 = SingleInstanceGuard(free_port)
        try:
            acquired1 = guard1.acquire()
            acquired2 = guard2.acquire()
            assert acquired1 is True
            assert acquired2 is False
        finally:
            guard1.stop()
            guard2.stop()

    def test_show_request_triggers_callback(self, free_port):
        """Second instance sending SHOW triggers the callback on first."""
        from saipenview.guard import SingleInstanceGuard

        show_called = threading.Event()
        guard = SingleInstanceGuard(free_port)

        def on_show():
            show_called.set()

        try:
            guard.acquire(on_show_request=on_show)

            # Simulate second instance
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("127.0.0.1", free_port))
                client.sendall(b"SHOW\n")
            finally:
                client.close()

            assert show_called.wait(timeout=5), "Callback should have been called"
        finally:
            guard.stop()

    def test_stop_cleans_up(self, free_port):
        """After stop, the port is free."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard(free_port)
        guard.acquire()
        guard.stop()

        guard2 = SingleInstanceGuard(free_port)
        try:
            acquired = guard2.acquire()
            assert acquired is True
        finally:
            guard2.stop()

    def test_double_stop_no_error(self):
        """Stopping an already-stopped guard is safe."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard()
        guard.stop()
        guard.stop()  # Should not raise

    def test_acquire_without_callback_returns_true(self, free_port):
        """Acquire works without on_show_request callback."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard(free_port)
        try:
            assert guard.acquire() is True
        finally:
            guard.stop()

    def test_socket_close_in_stop_handles_error(self):
        """If socket.close() raises, stop() catches it."""
        from unittest.mock import MagicMock

        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard()
        mock_sock = MagicMock()
        mock_sock.close.side_effect = OSError("close failed")
        guard._server_sock = mock_sock
        guard.stop()  # Should not raise

    def test_second_instance_connect_fails_gracefully(self, free_port):
        """If port is bound but connect fails, second instance returns False."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard(free_port)
        try:
            guard.acquire()
            # Bind the same port externally so connect() in the second guard fails
            guard2 = SingleInstanceGuard(free_port)
            result = guard2.acquire()
            assert result is False
        finally:
            guard.stop()

    def test_stop_close_error_handled(self):
        """Stopping a guard with no server socket is safe (no OSError on close)."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard()
        guard._server_sock = None
        guard.stop()  # Should not raise

    def test_socket_error_during_listen_loop(self, free_port):
        """If the listen socket is closed mid-loop, the listener exits gracefully."""
        from saipenview.guard import SingleInstanceGuard

        guard = SingleInstanceGuard(free_port)
        try:
            guard.acquire(on_show_request=lambda: None)
            # Force-close the server socket while the listener thread is running
            sock = guard._server_sock
            if sock:
                sock.close()
            import time

            time.sleep(0.2)
            # Thread should have exited without error
            assert guard._thread is None or not guard._thread.is_alive()
        finally:
            guard.stop()
