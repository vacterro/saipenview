"""Real-time file watcher for active SAIPEN projects.

Uses watchdog to monitor .saipen/STATE.md, BOARD.md, and LOG.md.
When a file is modified, it debounces the event and publishes it
to the EventBus so the UI can refresh immediately without waiting
for the 5-second poll cycle.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from saipenview.events import event_bus

DEBOUNCE_DELAY = 0.2


class _SaipenEventHandler(FileSystemEventHandler):
    def __init__(self, root: str) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        name = path.name

        if name in ("STATE.md", "BOARD.md", "LOG.md"):
            self._debounce(name)

    def _debounce(self, name: str) -> None:
        with self._lock:
            timer = self._timers.get(name)
            if timer:
                timer.cancel()

            t = threading.Timer(DEBOUNCE_DELAY, self._fire, args=(name,))
            self._timers[name] = t
            t.start()

    def _fire(self, name: str) -> None:
        with self._lock:
            self._timers.pop(name, None)

        event_name = {
            "STATE.md": "saipen.state_changed",
            "BOARD.md": "saipen.board_changed",
            "LOG.md": "saipen.log_appended",
        }.get(name)

        if event_name:
            event_bus.publish(event_name, {"root": self.root, "file": name})


class SaipenWatcher:
    """Manages watchdog observers for active agent projects."""

    def __init__(self) -> None:
        self._observer = Observer()
        self._observer.start()
        self._watches = {}
        self._handlers = {}
        self._lock = threading.Lock()

    def watch(self, root: str) -> None:
        """Start watching a project's .saipen/ dir."""
        saipen_dir = str(Path(root) / ".saipen")
        if not Path(saipen_dir).exists():
            return

        with self._lock:
            if root in self._watches:
                return

            try:
                handler = _SaipenEventHandler(root)
                watch = self._observer.schedule(handler, saipen_dir, recursive=False)
                self._watches[root] = watch
                self._handlers[root] = handler
            except OSError as e:
                print(
                    f"SAIPENVIEW: watcher failed to watch {root}: {e}", file=sys.stderr
                )

    def unwatch(self, root: str) -> None:
        """Stop watching a project."""
        with self._lock:
            watch = self._watches.pop(root, None)
            self._handlers.pop(root, None)

            if watch:
                try:
                    self._observer.unschedule(watch)
                except OSError as e:
                    print(
                        f"SAIPENVIEW: watcher failed to unwatch {root}: {e}",
                        file=sys.stderr,
                    )

    def stop(self) -> None:
        """Stop the observer thread."""
        self._observer.stop()
        self._observer.join()
