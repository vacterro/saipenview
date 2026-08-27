"""T-124: real-time watcher ownership, event handling, lifecycle, JS bridge.

The old SaipenWatcher lived in ProcessManager (only agent-launched projects
were watched), handled only on_modified, leaked debounce timers past
unwatch/stop, and the Api pushed the root/file into JavaScript through an
f-string -- a Windows root with an apostrophe or backslash broke the page.

These drive a real watchdog observer against real directories, because the
only honest test of a file watcher is a filesystem event.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.events import event_bus
from saipenview.watcher import SaipenWatcher

# A short debounce makes the arrival tests fast; the collapse/no-event tests
# build their own long-debounce watcher. Short here is fine because the
# "event must arrive" assertions never sleep a fixed window -- they wait.
TEST_DEBOUNCE = 0.05


def _wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _write_until_seen(do_write, log, timeout=10.0) -> bool:
    """Run *do_write* until the watcher publishes an event.

    watchdog's emitter opens its OS watch handle asynchronously after
    `schedule()` returns; a write landing before that handle is live is
    silently missed (an OS-baseline race, not a watcher defect -- the app
    polls and self-heals). Retrying until the event arrives makes the
    integration test deterministic under load.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        do_write()
        if log.count() >= 1:
            return True
        time.sleep(TEST_DEBOUNCE * 2)
    return False


def _make_project(root: Path) -> Path:
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    (saipen / "BOARD.md").write_text("# B\n", encoding="utf-8")
    return root


@pytest.fixture
def watcher():
    w = SaipenWatcher(debounce_delay=TEST_DEBOUNCE)
    yield w
    w.stop()


@pytest.fixture
def project(tmp_path):
    return _make_project(tmp_path / "proj")


class _EventLog:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def __call__(self, data: dict) -> None:
        with self._lock:
            self.events.append(data)

    def count(self) -> int:
        with self._lock:
            return len(self.events)

    def last(self) -> dict | None:
        with self._lock:
            return self.events[-1] if self.events else None


@pytest.fixture
def event_log():
    log = _EventLog()
    event_bus.subscribe("saipen.project_changed", log)
    yield log
    event_bus.unsubscribe("saipen.project_changed", log)


class TestOwnership:
    def test_scanned_project_is_watched_without_any_agent(
        self, watcher, project, event_log
    ):
        """The watch set comes from known projects, not from agent launch."""
        watcher.sync([str(project)])
        assert _write_until_seen(
            lambda: (project / ".saipen" / "STATE.md").write_text(
                "---\nphase: BUILD\n---\n", encoding="utf-8"
            ),
            event_log,
        ), "no event for a plain project"
        assert event_log.last()["root"] == str(project)
        assert event_log.last()["file"] == "STATE.md"

    def test_unknown_root_is_not_watched(self, watcher, project, event_log):
        watcher.sync([])
        (project / ".saipen" / "STATE.md").write_text("x\n", encoding="utf-8")
        time.sleep(TEST_DEBOUNCE * 4)
        assert event_log.count() == 0


class TestEventKinds:
    def test_atomic_os_replace_state_triggers(self, watcher, project, event_log):
        watcher.sync([str(project)])

        def do_write():
            tmp = project / ".saipen" / "STATE.md.tmp"
            tmp.write_text("---\nphase: SCOUT\n---\n", encoding="utf-8")
            os.replace(tmp, project / ".saipen" / "STATE.md")

        assert _write_until_seen(do_write, event_log)
        assert event_log.last()["file"] == "STATE.md"

    def test_board_moved_event_triggers(self, watcher, project, event_log):
        watcher.sync([str(project)])

        def do_write():
            tmp = project / ".saipen" / "incoming.tmp"
            tmp.write_text("# B2\n", encoding="utf-8")
            os.replace(tmp, project / ".saipen" / "BOARD.md")

        assert _write_until_seen(do_write, event_log)
        assert event_log.last()["file"] == "BOARD.md"

    def test_log_created_event_triggers(self, watcher, project, event_log):
        watcher.sync([str(project)])
        assert _write_until_seen(
            lambda: (project / ".saipen" / "LOG.md").write_text(
                "- 01.01.26 00:00 [E-1] RUN: x\n", encoding="utf-8"
            ),
            event_log,
        )
        assert event_log.last()["file"] == "LOG.md"

    def test_unrelated_file_ignored(self, watcher, project, event_log):
        watcher.sync([str(project)])
        (project / ".saipen" / "MANIFEST.md").write_text("- x\n", encoding="utf-8")
        (project / "scratch.txt").write_text("x\n", encoding="utf-8")
        time.sleep(TEST_DEBOUNCE * 4)
        assert event_log.count() == 0


class TestDebounce:
    def test_event_burst_collapses_to_one_refresh(self, tmp_path, project, event_log):
        # A long debounce makes the collapse deterministic: six rapid writes
        # land well inside one debounce window, so exactly one event publishes.
        watcher = SaipenWatcher(debounce_delay=0.6)
        try:
            watcher.sync([str(project)])
            f = project / ".saipen" / "STATE.md"
            # Retry the burst until the emitter's OS watch handle is live (the
            # start-up race), then assert the single-event collapse.
            deadline = time.monotonic() + 10.0
            seen = False
            while time.monotonic() < deadline and not seen:
                for _ in range(6):
                    f.write_text("---\nphase: BUILD\n---\n", encoding="utf-8")
                    time.sleep(0.01)
                seen = _wait_for(lambda: event_log.count() >= 1, timeout=2.0)
            assert seen, "burst produced no event"
            time.sleep(1.5)  # well past the 0.6s debounce
            assert event_log.count() == 1, f"burst produced {event_log.count()} events"
        finally:
            watcher.stop()


class TestLifecycle:
    def test_unwatch_cancels_pending_timer(self, watcher, project, event_log):
        watcher.sync([str(project)])
        (project / ".saipen" / "STATE.md").write_text("x\n", encoding="utf-8")
        watcher.unwatch(str(project))
        time.sleep(TEST_DEBOUNCE * 4)
        assert event_log.count() == 0, "a callback fired after unwatch"

    def test_stop_is_idempotent_and_silences_events(self, watcher, project, event_log):
        watcher.sync([str(project)])
        watcher.stop()
        watcher.stop()
        (project / ".saipen" / "STATE.md").write_text("x\n", encoding="utf-8")
        time.sleep(TEST_DEBOUNCE * 4)
        assert event_log.count() == 0


class TestJsBridge:
    def test_windows_path_survives_js_round_trip(self):
        """The root/file reach the JS as JSON literals, byte-exact through a
        real JS engine -- the property an f-string interpolation breaks."""
        import subprocess

        tricky = r"V:\weird 'path' ünïcode\proj"
        assert json.loads(json.dumps(tricky)) == tricky
        js_expr = (
            "onSaipenFileChanged("
            + json.dumps(tricky)
            + ", "
            + json.dumps("STATE.md")
            + ", "
            + json.dumps("external")
            + ")"
        )
        r = subprocess.run(
            [
                "node",
                "-e",
                "function onSaipenFileChanged(a,b,c){console.log(JSON.stringify([a,b,c]))};"
                + js_expr,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout) == [tricky, "STATE.md", "external"], (
            "a Windows root did not survive the JS round-trip byte-exact"
        )

    def test_api_pushes_json_not_interpolated(self, tmp_path):
        from saipenview.api import Api
        from saipenview.config import DEFAULTS

        cfg = dict(DEFAULTS)
        cfg["pinned_roots"] = []
        cfg["hidden_roots"] = []
        cfg["scan_roots"] = None
        with (
            patch("saipenview.api.config_path"),
            patch("saipenview.api.load_config", return_value=cfg),
            patch("saipenview.api.save_config"),
            patch("saipenview.api.BackgroundScanner"),
        ):
            api = Api()
            api._debounce_delay = 0  # CORE-005: test expects synchronous publish
            try:
                pushed = {}
                api._window = type(
                    "W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)}
                )()
                tricky = r"V:\it's & weird ünïcode"
                with patch.object(api, "_refresh_one_project") as mock_refresh:
                    api._on_file_changed({"root": tricky, "file": "STATE.md"})
                    mock_refresh.assert_called_once()
                    args, kwargs = mock_refresh.call_args
                    assert args[0] == tricky
                    assert args[1] == {"STATE.md"} or kwargs.get("changed_files") == {"STATE.md"}
                assert json.dumps(tricky) in pushed["js"], pushed["js"]
            finally:
                api.stop()

    def test_one_event_does_not_trigger_two_full_refreshes(self, tmp_path):
        from saipenview.api import Api
        from saipenview.config import DEFAULTS

        cfg = dict(DEFAULTS)
        cfg["pinned_roots"] = []
        cfg["hidden_roots"] = []
        cfg["scan_roots"] = None
        with (
            patch("saipenview.api.config_path"),
            patch("saipenview.api.load_config", return_value=cfg),
            patch("saipenview.api.save_config"),
            patch("saipenview.api.BackgroundScanner"),
        ):
            api = Api()
            api._debounce_delay = 0  # CORE-005: test expects synchronous publish
            try:
                api._window = type("W", (), {"evaluate_js": lambda self, s: None})()
                with (
                    patch.object(api, "refresh_known") as mock_all,
                    patch.object(api, "_refresh_one_project") as mock_one,
                ):
                    api._on_file_changed({"root": "r", "file": "STATE.md"})
                    mock_one.assert_called_once()
                    mock_all.assert_not_called()
            finally:
                api.stop()


class TestCacheWrite:
    def test_two_simultaneous_writes_do_not_corrupt_cache(self, tmp_path):
        from saipenview.api import Api
        from saipenview.config import DEFAULTS

        cfg = dict(DEFAULTS)
        cfg["pinned_roots"] = []
        cfg["hidden_roots"] = []
        cfg["scan_roots"] = None
        with (
            patch("saipenview.api.config_path"),
            patch("saipenview.api.load_config", return_value=cfg),
            patch("saipenview.api.save_config"),
            patch("saipenview.api.BackgroundScanner"),
        ):
            api = Api()
            try:
                cache = tmp_path / "cache.json"
                api._cache_file = cache
                api._projects = [{"root": f"r{i}", "n": i} for i in range(3)]

                def writer(offset):
                    for i in range(5):
                        with api._lock:
                            api._projects = [{"root": f"r{i + offset}", "n": i}]
                        api._write_cache()

                threads = [
                    threading.Thread(target=writer, args=(0,)),
                    threading.Thread(target=writer, args=(100,)),
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=10)
                data = json.loads(cache.read_text(encoding="utf-8"))
                assert isinstance(data, list)
                # no leftover temp debris
                leftovers = [
                    p for p in tmp_path.iterdir() if p.name.startswith("cache.json.")
                ]
                assert leftovers == [], leftovers
            finally:
                api.stop()
