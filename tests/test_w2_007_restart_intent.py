"""T-17 / W2-007: BackgroundScanner restart intent survives blocked stop."""

import threading
from unittest.mock import MagicMock

from saipenview import scanner as sc
from saipenview.scanner import BackgroundScanner, ScanOutcome


def test_restart_waits_for_old_generation_and_starts_once(monkeypatch):

    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    calls = []

    def fake_scan(*args, **kwargs):
        event = kwargs["cancel"]
        calls.append(event)
        if len(calls) == 1:
            first_started.set()
            release_first.wait(timeout=5)
        else:
            second_started.set()
        return ScanOutcome()

    monkeypatch.setattr(sc, "scan", fake_scan)
    scanner = BackgroundScanner(on_result=MagicMock(), interval_seconds=60.0)
    scanner.start()
    assert first_started.wait(timeout=5)

    scanner.stop()
    assert scanner._restart_pending is True
    old_thread = scanner._thread
    assert old_thread is not None and old_thread.is_alive()

    scanner.start()
    assert scanner._thread is old_thread
    assert len(calls) == 1
    assert calls[0].is_set()

    release_first.set()
    assert second_started.wait(timeout=5)
    assert len(calls) == 2
    assert calls[1] is not calls[0]
    assert calls[1].is_set() is False

    scanner.stop()


def test_start_without_restart_pending_respects_alive_guard():
    """When no restart was requested (e.g. double-start), start()
    must still respect the alive-boundary and NOT stack a second loop.
    """
    on_result = MagicMock()
    scanner = BackgroundScanner(on_result=on_result, interval_seconds=60.0)
    scanner.start()
    assert scanner.is_alive()

    # Call start() again while thread is alive -- no restart was requested.
    # Should return early (double-start guard).
    scanner.start()
    # Should still have exactly one thread.
    assert scanner._thread is not None
    # No restart intent was set.
    assert not scanner._restart_pending

    scanner.stop()
