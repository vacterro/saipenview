"""T-17 / W2-007: BackgroundScanner restart intent survives blocked stop."""
import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_gen():
    """Reset module-level generation counter so tests are isolated."""
    import saipenview.scanner as sc
    sc._current_gen = 0
    yield
    sc._current_gen = 0


def test_restart_pending_survives_slow_stop():
    """stop() blocks past 1s grace window -> _restart_pending=True.
    Immediate start() must launch a fresh worker even though old thread
    is still alive (its generation is stale so it will exit on next iter).
    """
    from saipenview.scanner import BackgroundScanner
    import saipenview.scanner as sc

    on_result = MagicMock()
    scanner = BackgroundScanner(on_result=on_result, interval_seconds=60.0)

    # Patch scan to block longer than stop()'s 1s join + start()'s 2s join.
    real_scan = sc.scan

    def slow_scan(*args, **kwargs):
        time.sleep(5.0)
        return real_scan(*args, **kwargs)

    sc.scan = slow_scan

    # Start the scanner so it has a live thread.
    scanner.start()
    assert scanner.is_alive()

    # stop() will set the stop event and try to join with 1s timeout.
    # The thread is blocked in slow_scan so it won't exit in time.
    scanner.stop()
    # Restart intent must be recorded.
    assert scanner._restart_pending is True
    # Old thread is still alive.
    assert scanner._thread is not None
    assert scanner._thread.is_alive()

    # Immediate start(): despite old thread being alive, restart intent
    # means we must launch a fresh worker, not bail out.
    scanner.start()

    # A new thread must have been launched and restart flag cleared.
    assert scanner._thread is not None
    assert scanner._restart_pending is False
    # The scanner is alive (new worker running).
    assert scanner.is_alive()

    # Cleanup -- let the slow scan finish, then stop.
    scanner.stop()


def test_start_without_restart_pending_respects_alive_guard():
    """When no restart was requested (e.g. double-start), start()
    must still respect the alive-boundary and NOT stack a second loop.
    """
    from saipenview.scanner import BackgroundScanner

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
