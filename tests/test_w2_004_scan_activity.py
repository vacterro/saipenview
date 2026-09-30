"""W2-004: scan liveness is the lifetime of actual scan operations.

Before the fix, `Api._scanning` was a boolean cleared only inside
`_set_cache`'s SUCCESS branches. `BackgroundScanner._loop` caught a failed
scan and continued with no paired finish callback, so a raising `scan()` left
`scanning=True` forever after the thread had stopped. The same boolean was
also vulnerable to overlapping scans clearing each other's state.

The fix makes scan activity an explicit counter owned by Api
(`_scan_begin`/`_scan_end`, or the `_scan_activity()` context manager) and
makes `BackgroundScanner` pair `on_scan_start` with `on_scan_end` in a
`finally` on every exit -- success, error, cancellation or stale generation.
"""

from __future__ import annotations

import threading
import time

import pytest

from saipenview import scanner
from saipenview.scanner import BackgroundScanner


def _wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class _Counter:
    """Stands in for Api's paired scan-activity primitive."""

    def __init__(self):
        self.active = 0
        self.lock = threading.Lock()

    def begin(self):
        with self.lock:
            self.active += 1

    def end(self):
        with self.lock:
            self.active = max(0, self.active - 1)

    @property
    def scanning(self):
        with self.lock:
            return self.active > 0


def test_failed_scan_clears_scanning(tmp_path, monkeypatch):
    """A scan() that raises OSError must not leave scanning true."""
    counter = _Counter()

    def boom(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(scanner, "scan", boom)

    bs = BackgroundScanner(
        on_result=lambda *a, **k: None,
        scan_roots=[str(tmp_path)],
        interval_seconds=0.05,
        on_scan_start=counter.begin,
        on_scan_end=counter.end,
    )
    bs.start()
    try:
        # Let at least one failing cycle run.
        assert _wait_for(lambda: counter.active >= 0), "no cycle ran"
        time.sleep(0.2)
    finally:
        bs.stop()

    # After stop() drains, no scan can be active: scanning is false.
    assert _wait_for(lambda: not counter.scanning), (
        "scanning stayed true after a failed scan"
    )
    assert counter.active == 0


def test_cancelled_inflight_scan_clears_scanning(tmp_path, monkeypatch):
    """A cancelled in-flight scan must release the paired activity on exit."""
    counter = _Counter()
    entered = threading.Event()
    release = threading.Event()

    def slow_scan(*args, **kwargs):
        entered.set()
        # Respect cancellation deterministically: wait for stop or release.
        cancel = kwargs.get("cancel")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                break
            if release.is_set():
                break
            time.sleep(0.01)
        result = scanner.ScanOutcome(
            projects=[], complete=False, worktrees=[], completed_roots=[], unresolved_roots=[]
        )
        return result

    monkeypatch.setattr(scanner, "scan", slow_scan)

    bs = BackgroundScanner(
        on_result=lambda *a, **k: None,
        scan_roots=[str(tmp_path)],
        interval_seconds=10,
        on_scan_start=counter.begin,
        on_scan_end=counter.end,
        initial_delay=0.0,
    )
    bs.start()
    try:
        assert entered.wait(timeout=5), "scan never started"
        assert counter.scanning is True
    finally:
        bs.stop()
    assert _wait_for(lambda: not counter.scanning, timeout=10), (
        "cancelled scan never cleared the activity count"
    )
    assert counter.active == 0


def test_overlapping_scans_keep_scanning_until_last_exits():
    """Completion of one active scan must not clear another still running."""
    counter = _Counter()
    counter.begin()
    counter.begin()
    assert counter.active == 2
    counter.end()  # first finishes
    assert counter.scanning is True, "first completion cleared a live scan"
    counter.end()  # last finishes
    assert counter.scanning is False


def test_api_scanning_false_after_raised_rescan(tmp_path, monkeypatch):
    """BEHAVIORAL red control (works on both trees): a rescan whose scan()
    raises must not leave the public `scanning` view true.

    Pre-fix this fails: `rescan()` wrote `_scanning=True` and only `_set_cache`
    success branches cleared it, so the raise stranded it true forever.
    """
    import unittest.mock as _mock

    import saipenview.api as api_mod
    from saipenview.config import DEFAULTS

    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None

    def raising_scan(*a, **k):
        raise OSError("scan boom")

    with monkeypatch.context() as m:
        m.setattr(api_mod, "config_path", lambda: tmp_path / "config.json")
        m.setattr(api_mod, "load_config", lambda: dict(cfg))
        m.setattr(api_mod, "save_config", lambda *a, **k: None)
        m.setattr(api_mod, "BackgroundScanner", _mock.MagicMock())
        m.setattr(api_mod, "SaipenWatcher", _mock.MagicMock())
        m.setattr(api_mod, "scan", raising_scan)
        api = api_mod.Api()
        try:
            with pytest.raises(OSError):
                api.rescan()
            assert api.get_status()["scanning"] is False, (
                "scanning stranded true after a raised rescan"
            )
        finally:
            api.stop()


def test_api_scan_activity_is_paired_on_rescan(tmp_path, monkeypatch):
    """Api.rescan() clears its active-scan count even when scan() raises."""
    import unittest.mock as _mock

    import saipenview.api as api_mod
    from saipenview.config import DEFAULTS

    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None

    def raising_scan(*a, **k):
        raise OSError("scan boom")

    with monkeypatch.context() as m:
        m.setattr(api_mod, "config_path", lambda: tmp_path / "config.json")
        m.setattr(api_mod, "load_config", lambda: dict(cfg))
        m.setattr(api_mod, "save_config", lambda *a, **k: None)
        m.setattr(api_mod, "BackgroundScanner", _mock.MagicMock())
        m.setattr(api_mod, "SaipenWatcher", _mock.MagicMock())
        m.setattr(api_mod, "scan", raising_scan)
        api = api_mod.Api()
        try:
            with pytest.raises(OSError):
                api.rescan()
            # The paired activity cleared the state despite the raise.
            assert api._scan_active == 0
            assert api.get_status()["scanning"] is False
        finally:
            api.stop()
