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
_TRACKED = frozenset({"STATE.md", "BOARD.md", "LOG.md", "OUTBOX.md", "MANIFEST.md"})


class _SaipenEventHandler(FileSystemEventHandler):
    """Reacts to all four watchdog event kinds, filtering to the protocol
    files, collapsing bursts into one debounced publish per file.

    W2-002: the debounce now counts raw events per (root, file) in the
    window and publishes that count. The Api compares it against the number
    of armed self-write registrations for the same file: more raw events
    than self registrations means an external write landed between app
    writes (self A -> external B -> self C) -- a signal the final-content
    fingerprint check alone cannot see. Debounce stays only for the
    expensive reparse/UI refresh; the event count preserves causal evidence.
    """

    def __init__(self, root: str, debounce_delay: float = DEBOUNCE_DELAY) -> None:
        self.root = root
        self._debounce_delay = debounce_delay
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        # W2-002: raw-event count per file in the current debounce window.
        self._event_counts: dict[str, int] = {}
        self._disposed = False

    def on_modified(self, event) -> None:
        self._maybe_event(event)

    def on_created(self, event) -> None:
        self._maybe_event(event)

    def on_deleted(self, event) -> None:
        self._maybe_event(event)

    def on_moved(self, event) -> None:
        # W2-009: inspect BOTH endpoints independently. A move-away
        # (STATE.md -> STATE.bak) only appears on src_path; a temp-file rename
        # (tmp -> STATE.md) only on dest_path. Either way the tracked file's
        # protocol state moved and the Api must re-read it. Debounce keys by
        # filename, so a same-name replace collapses to one event naturally.
        if event.is_directory:
            return
        src = getattr(event, "src_path", None)
        dest = getattr(event, "dest_path", None)
        if src:
            self._maybe_path(src)
        if dest:
            self._maybe_path(dest)

    def _maybe_event(self, event) -> None:
        if event.is_directory:
            return
        self._maybe_path(event.src_path)

    def _maybe_path(self, path_str: str) -> None:
        # CORE-006: compute the path relative to the .saipen/ watch root so
        # nested same-named files (e.g. extensions/subs/x/BOARD.md vs
        # BOARD.md at the project root) use independent debounce keys and
        # publish the correct relative path for _on_file_changed to resolve.
        try:
            rel = Path(path_str).relative_to(Path(self.root) / ".saipen")
        except ValueError:
            return  # path is outside the watched tree
        if rel.name in _TRACKED:
            with self._lock:
                if self._disposed:
                    return
                # W2-002: count every raw event for this file in the window.
                self._event_counts[rel.name] = self._event_counts.get(rel.name, 0) + 1
            self._debounce(str(rel))

    def _debounce(self, name: str) -> None:
        with self._lock:
            if self._disposed:
                return
            timer = self._timers.get(name)
            if timer:
                timer.cancel()
            t = threading.Timer(self._debounce_delay, self._fire, args=(name,))
            t.daemon = True
            self._timers[name] = t
            t.start()

    def _fire(self, name: str) -> None:
        # T-124's lifecycle contract, made deterministic (T-183 wave): the
        # callback MUST never publish after cancel()/stop() -- a timer that
        # already began executing when cancel() ran is checked here, under the
        # same lock cancel() uses.
        with self._lock:
            if self._disposed:
                return
            self._timers.pop(name, None)
            event_count = self._event_counts.pop(name, 0)
        event_bus.publish(
            "saipen.project_changed",
            {
                "root": self.root,
                "file": name,
                "event_count": event_count,
            },
        )

    def cancel(self) -> None:
        """Cancel all pending timers -- the callback must never fire after
        the watch is gone (T-124)."""
        with self._lock:
            self._disposed = True
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
            self._event_counts.clear()


class SaipenWatcher:
    """Owns the watchdog observer and the set of watched project roots."""

    def __init__(self, debounce_delay: float = DEBOUNCE_DELAY) -> None:
        self._observer = Observer()
        self._observer.start()
        self._watches: dict[str, object] = {}
        self._handlers: dict[str, _SaipenEventHandler] = {}
        self._lock = threading.Lock()
        self._stopped = False
        self._debounce_delay = debounce_delay

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
        """Watch one project's .saipen/ dir (no-op if absent or already watched).

        PERF-002: recursive=True so SubSaipen/translate protocol sources under
        ``.saipen/extensions/subs/<name>/`` events also reach the per-project
        handler. The handler already filters by tracked filename, so a
        recursive watch costs only a few extra OS inotify-style entries per
        project, not extra publishes.
        """
        saipen_dir = Path(root) / ".saipen"
        if not saipen_dir.is_dir():
            return
        with self._lock:
            if self._stopped or root in self._watches:
                return
            try:
                handler = _SaipenEventHandler(root, debounce_delay=self._debounce_delay)
                watch = self._observer.schedule(
                    handler, str(saipen_dir), recursive=True
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
            self._observer.join(timeout=0.5)
        except (RuntimeError, OSError):
            pass
