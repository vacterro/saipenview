"""PERF-002: debounce must collapse SCHEDULING work, not just callbacks.

Both `_RootRouterHandler` and `_SaipenEventHandler` used to cancel and recreate
a `threading.Timer` for every raw event. A 10,000-event burst on one key built,
started and cancelled 10,000 timers to publish once. The fix keeps ONE live
slot per identity: later events only advance a monotonic deadline and the
count; the timer re-arms once if the deadline moved.

These tests instrument `threading.Timer` construction under a large burst and
assert the count is bounded independently of the raw-event count, while the
final publish still carries the exact accumulated event_count.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from saipenview.events import event_bus
from saipenview.watcher import _RootRouterHandler, _SaipenEventHandler


class _TimerCounter:
    def __init__(self, monkeypatch):
        self.constructed = 0
        self.started = 0
        self.cancelled = 0
        real_timer = threading.Timer

        counter = self

        class _CountingTimer(real_timer):  # type: ignore[misc, valid-type]
            def __init__(self, *a, **k):
                counter.constructed += 1
                super().__init__(*a, **k)

            def start(self):
                counter.started += 1
                return super().start()

            def cancel(self):
                counter.cancelled += 1
                return super().cancel()

        monkeypatch.setattr(threading, "Timer", _CountingTimer)


def _collect_publishes(monkeypatch):
    events: list[dict] = []
    real_publish = event_bus.publish

    def spy(name, data=None):
        if name == "saipen.project_changed":
            events.append(dict(data or {}))
        return real_publish(name, data)

    monkeypatch.setattr(event_bus, "publish", spy)
    return events


def test_fallback_handler_burst_is_bounded_scheduling(monkeypatch):
    counter = _TimerCounter(monkeypatch)
    events = _collect_publishes(monkeypatch)

    import tempfile

    root = tempfile.mkdtemp()
    handler = _SaipenEventHandler(root, debounce_delay=0.05)

    ev = SimpleNamespace(is_directory=False, src_path=f"{root}\\.saipen\\LOG.md")
    for _ in range(10000):
        handler._maybe_path(ev.src_path)

    # Wait for the debounce to settle and publish.
    for _ in range(200):
        if events:
            break
        import time

        time.sleep(0.02)

    handler.cancel()
    assert len(events) == 1, f"expected one publish, got {len(events)}"
    assert events[0]["event_count"] == 10000
    assert counter.constructed <= 20, (
        f"timer churn not collapsed: constructed={counter.constructed}"
    )


def test_router_handler_burst_is_bounded_scheduling(monkeypatch):
    counter = _TimerCounter(monkeypatch)
    events = _collect_publishes(monkeypatch)

    import tempfile

    scope = tempfile.mkdtemp()
    project = f"{scope}\\proj"
    router = {scope: {project: project}}
    handler = _RootRouterHandler(scope, router, debounce_delay=0.05)

    import os

    saipen_dir = os.path.join(project, ".saipen")
    os.makedirs(saipen_dir, exist_ok=True)
    log_path = os.path.join(saipen_dir, "LOG.md")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("x\n")

    for _ in range(10000):
        handler._maybe_path(log_path)

    for _ in range(200):
        if events:
            break
        import time

        time.sleep(0.02)

    handler.cancel()
    assert len(events) == 1, f"expected one publish, got {len(events)}"
    assert events[0]["event_count"] == 10000
    # The whole point: timer construction is bounded independently of the
    # 10,000 raw events (pre-fix this was ~10,000).
    assert counter.constructed <= 20, (
        f"timer churn not collapsed: constructed={counter.constructed}"
    )


def test_no_publish_after_cancel(monkeypatch):
    _TimerCounter(monkeypatch)
    events = _collect_publishes(monkeypatch)

    import tempfile

    root = tempfile.mkdtemp()
    handler = _SaipenEventHandler(root, debounce_delay=0.05)
    handler._maybe_path(f"{root}\\.saipen\\BOARD.md")
    handler.cancel()
    import time

    time.sleep(0.2)
    assert events == [], "callback published after cancel()"


def test_distinct_keys_publish_independently(monkeypatch):
    _collect_publishes(monkeypatch)

    import tempfile
    import time

    root = tempfile.mkdtemp()
    handler = _SaipenEventHandler(root, debounce_delay=0.05)

    collected: list[dict] = []
    real_publish = event_bus.publish

    def spy(name, data=None):
        if name == "saipen.project_changed":
            collected.append(dict(data or {}))
        return real_publish(name, data)

    monkeypatch.setattr(event_bus, "publish", spy)

    for _ in range(10):
        handler._maybe_path(f"{root}\\.saipen\\LOG.md")
    for _ in range(5):
        handler._maybe_path(f"{root}\\.saipen\\BOARD.md")

    for _ in range(200):
        if len(collected) >= 2:
            break
        time.sleep(0.02)
    handler.cancel()

    by_file = {e["file"]: e["event_count"] for e in collected}
    assert by_file.get("LOG.md") == 10
    assert by_file.get("BOARD.md") == 5
