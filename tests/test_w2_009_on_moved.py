"""T-588 / W2-009: watcher on_moved must observe move-away events.

The old ``on_moved`` only classified ``dest_path``, so renaming a tracked
file away (``STATE.md`` -> ``STATE.bak``) produced no event and the cached
project went stale. Now both endpoints are inspected independently; the
debounce key (filename) dedupes a same-name replace to one event.

Verified against the audit matrix: STATE.md->STATE.bak, tmp->STATE.md,
STATE.md->BOARD.md, and an unrelated move each produce exactly the expected
set of debounced tracked events.
"""

from __future__ import annotations

import time

from saipenview.events import event_bus
from saipenview.watcher import _SaipenEventHandler


class _FakeMove:
    is_directory = False

    def __init__(self, src, dest):
        self.src_path = src
        self.dest_path = dest


def _run(handler, event):
    captured = []
    event_bus.subscribe("saipen.project_changed", captured.append)
    try:
        handler.on_moved(event)
        time.sleep(0.06)  # let the zero-delay debounce timer fire
        return captured
    finally:
        event_bus.unsubscribe("saipen.project_changed", captured.append)


def _strip_meta(events):
    """W2-002: the debounce event now carries an event_count field; tests
    assert on the semantic {root, file} payload, not the telemetry key."""
    return [
        {k: v for k, v in e.items() if k in ("root", "file")} for e in events
    ]


def test_move_away_fires_for_source():
    h = _SaipenEventHandler("/r", debounce_delay=0)
    cap = _run(h, _FakeMove("/r/.saipen/STATE.md", "/r/.saipen/STATE.bak"))
    assert _strip_meta(cap) == [{"root": "/r", "file": "STATE.md"}]
    assert cap[0]["event_count"] == 1


def test_move_in_fires_for_dest():
    h = _SaipenEventHandler("/r", debounce_delay=0)
    cap = _run(h, _FakeMove("/r/.saipen/tmpABC", "/r/.saipen/STATE.md"))
    assert _strip_meta(cap) == [{"root": "/r", "file": "STATE.md"}]


def test_move_between_tracked_fires_both():
    h = _SaipenEventHandler("/r", debounce_delay=0)
    cap = _run(h, _FakeMove("/r/.saipen/STATE.md", "/r/.saipen/BOARD.md"))
    assert {"root": "/r", "file": "STATE.md"} in _strip_meta(cap)
    assert {"root": "/r", "file": "BOARD.md"} in _strip_meta(cap)
    assert len(cap) == 2


def test_unrelated_move_ignored():
    h = _SaipenEventHandler("/r", debounce_delay=0)
    cap = _run(h, _FakeMove("/r/.saipen/foo.txt", "/r/.saipen/bar.txt"))
    assert cap == []


def test_directory_move_ignored():
    ev = _FakeMove("/r/.saipen/STATE.md", "/r/.saipen/STATE.bak")
    ev.is_directory = True
    h = _SaipenEventHandler("/r", debounce_delay=0)
    cap = _run(h, ev)
    assert cap == []
