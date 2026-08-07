"""Real-time file watcher for SAIPEN projects (T-124 rewrite).

Ownership moved where it belongs: the watcher lives in the Api/project
registry, NOT in the ProcessManager. Every known project is watched whether
or not an agent is running; agent launch/finish no longer touches
project-file watching; a root whose ``.saipen/`` reappears is picked up by
the next ``sync()``.

One filesystem event produces one structured ``saipen.project_changed`` event
carrying ``{"root", "file"}``. The Api re-reads exactly the changed project
and pushes the root/file to the frontend via JSON serialization -- never
through f-string interpolation into JavaScript.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from saipenview.events import event_bus

DEBOUNCE_DELAY = 0.2
# The only files whose change means the project's protocol state moved.
_TRACKED = frozenset({"STATE.md", "BOARD.md", "LOG.md"})


class _SaipenEventHandler(FileSystemEventHandler):
    """Reacts to all four watchdog event kinds, filtering to the protocol
    files, collapsing bursts into one debounced publish per file."""

    def __init__(self, root: str) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def on_modified(self, event) -> None:
        self._maybe_event(event)

    def on_created(self, event) -> None:
        self._maybe_event(event)

    def on_deleted(self, event) -> None:
        self._maybe_event(event)

    def on_moved(self, event) -> None:
        # The destination path is the file that now exists and carries the
        # change; a temp-file rename (write_doc's os.replace) lands here.
        dest = getattr(event, "dest_path", None)
        if not dest or event.is_directory:
            return
        self._maybe_path(dest)

    def _maybe_event(self, event) -> None:
        if event.is_directory:
            return
        self._maybe_path(event.src_path)

    def _maybe_path(self, path_str: str) -> None:
        if Path(path_str).name in _TRACKED:
            self._debounce(Path(path_str).name)

    def _debounce(self, name: str) -> None:
        with self._lock:
            timer = self._timers.get(name)
            if timer:
                timer.cancel()
            t = threading.Timer(DEBOUNCE_DELAY, self._fire, args=(name,))
            t.daemon = True
            self._timers[name] = t
            t.start()

    def _fire(self, name: str) -> None:
        with self._lock:
            self._timers.pop(name, None)
        event_bus.publish("saipen.project_changed", {"root": self.root, "file": name})

    def cancel(self) -> None:
        """Cancel all pending timers -- the callback must never fire after
        the watch is gone (T-124)."""
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()


class SaipenWatcher:
    """Owns the watchdog observer and the set of watched project roots."""

    def __init__(self) -> None:
        self._observer = Observer()
        self._observer.start()
        self._watches: dict[str, object] = {}
        self._handlers: dict[str, _SaipenEventHandler] = {}
        self._lock = threading.Lock()
        self._stopped = False

    def sync(self, roots: list[str]) -> None:
        """Reconcile the watch set with the current known projects.

        Watches roots whose ``.saipen/`` exists, drops roots no longer known,
        and leaves a temporarily-missing root unobserved until it returns --
        at which point the next sync() re-watches it (T-124: a stale root
        stays registered logically and re-activates)."""
        if self._stopped:
            return
        wanted = {r for r in roots if (Path(r) / ".saipen").is_dir()}
        with self._lock:
            current = set(self._watches)
        for root in current - wanted:
            self.unwatch(root)
        for root in wanted:
            if root not in self._watches:
                self.watch(root)

    def watch(self, root: str) -> None:
        """Watch one project's .saipen/ dir (no-op if absent or already watched)."""
        saipen_dir = Path(root) / ".saipen"
        if not saipen_dir.is_dir():
            return
        with self._lock:
            if self._stopped or root in self._watches:
                return
            try:
                handler = _SaipenEventHandler(root)
                watch = self._observer.schedule(
                    handler, str(saipen_dir), recursive=False
                )
                self._watches[root] = watch
                self._handlers[root] = handler
            except OSError as e:
                print(
                    f"SAIPENVIEW: watcher failed to watch {root}: {e}", file=sys.stderr
                )

    def unwatch(self, root: str) -> None:
        """Stop watching a project and cancel its pending debounce timers."""
        with self._lock:
            handler = self._handlers.pop(root, None)
            watch = self._watches.pop(root, None)
            if handler:
                handler.cancel()
            if watch:
                try:
                    self._observer.unschedule(watch)
                except OSError as e:
                    print(
                        f"SAIPENVIEW: watcher failed to unwatch {root}: {e}",
                        file=sys.stderr,
                    )

    def stop(self) -> None:
        """Cancel everything and stop the observer. Idempotent (T-124)."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            for handler in self._handlers.values():
                handler.cancel()
            self._handlers.clear()
            self._watches.clear()
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
        except RuntimeError:
            # Observer already stopped or never started.
            pass
