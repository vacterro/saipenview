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


class _RootRouterHandler(FileSystemEventHandler):
    """PERF-001: per-scan-root router.

    The handler subscribes to one recursive watchdog watch on a configured
    scan root. Each filesystem event is resolved to the owning project by
    longest-prefix match against the router table and published as if it
    had arrived on a per-project watch. Empty matches are dropped (the
    event was beneath the scan root but above every known project's
    .saipen/ tree).
    """

    def __init__(
        self,
        scope: str,
        router: dict[str, dict[str, str]],
        debounce_delay: float = DEBOUNCE_DELAY,
    ) -> None:
        super().__init__()
        self._scope = scope
        # Reference the router by identity so the owning SaipenWatcher can
        # mutate it without re-baking handler state.
        self._router = router
        self._debounce_delay = debounce_delay
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._event_counts: dict[str, int] = {}
        self._disposed = False

    def on_any_event(self, event) -> None:
        if event.is_directory:
            return
        self._maybe_path(event.src_path)
        dest = getattr(event, "dest_path", None)
        if dest:
            self._maybe_path(dest)

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        self._maybe_path(event.src_path)
        dest = getattr(event, "dest_path", None)
        if dest:
            self._maybe_path(dest)

    def _maybe_path(self, path_str: str) -> None:
        project = self._resolve_project(path_str)
        if project is None:
            return
        try:
            rel = Path(path_str).relative_to(Path(project) / ".saipen")
        except ValueError:
            return
        if rel.name in _TRACKED:
            key = rel.as_posix()
            with self._lock:
                if self._disposed:
                    return
                self._event_counts[key] = self._event_counts.get(key, 0) + 1
            self._debounce(project, key)

    def _resolve_project(self, path_str: str) -> str | None:
        norm = path_str.replace("\\", "/").lower()
        projects = self._router.get(self._scope, {})
        # Longest-prefix match: prefer the deepest known project root
        # beneath the scan root.
        best: tuple[int, str] | None = None
        for project in projects:
            proj_norm = project.replace("\\", "/").lower().rstrip("/")
            if norm == proj_norm or norm.startswith(proj_norm + "/"):
                if best is None or len(proj_norm) > best[0]:
                    best = (len(proj_norm), project)
        return best[1] if best else None

    def _debounce(self, project: str, key: str) -> None:
        with self._lock:
            if self._disposed:
                return
            timer = self._timers.get(key)
            if timer:
                timer.cancel()
            t = threading.Timer(
                self._debounce_delay, self._fire, args=(project, key)
            )
            t.daemon = True
            self._timers[key] = t
            t.start()

    def _fire(self, project: str, key: str) -> None:
        with self._lock:
            if self._disposed:
                return
            self._timers.pop(key, None)
            event_count = self._event_counts.pop(key, 0)
        event_bus.publish(
            "saipen.project_changed",
            {
                "root": project,
                "file": key,
                "event_count": event_count,
            },
        )

    def cancel(self) -> None:
        with self._lock:
            self._disposed = True
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
            self._event_counts.clear()


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
            # W2-001: ONE canonical key for event counts, debounce timers,
            # published "file" field, and SelfWriteRegistry lookup. Using
            # rel.as_posix() ensures forward-slash keys on all platforms so
            # Windows backslash paths do not drift from the normalized
            # SelfWriteRegistry keys.
            key = rel.as_posix()
            with self._lock:
                if self._disposed:
                    return
                self._event_counts[key] = self._event_counts.get(key, 0) + 1
            self._debounce(key)

    def _debounce(self, key: str) -> None:
        with self._lock:
            if self._disposed:
                return
            timer = self._timers.get(key)
            if timer:
                timer.cancel()
            t = threading.Timer(self._debounce_delay, self._fire, args=(key,))
            t.daemon = True
            self._timers[key] = t
            t.start()

    def _fire(self, key: str) -> None:
        # T-124's lifecycle contract, made deterministic (T-183 wave): the
        # callback MUST never publish after cancel()/stop() -- a timer that
        # already began executing when cancel() ran is checked here, under the
        # same lock cancel() uses.
        with self._lock:
            if self._disposed:
                return
            self._timers.pop(key, None)
            event_count = self._event_counts.pop(key, 0)
        event_bus.publish(
            "saipen.project_changed",
            {
                "root": self.root,
                "file": key,
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
    """Owns the watchdog observer and the set of watched project roots.

    PERF-001: schedule by SCAN ROOT, not per project. A watchdog
    ``BaseObserver.schedule`` creates a distinct emitter per ObservedWatch
    even when one Observer is shared, so the old O(projects) topology grew
    threads linearly with the project count. Group projects under their
    configured scan roots and run one recursive watch per scan root; a
    per-scan-root router resolves each event path to the owning project.
    Roots that fall outside any scan root (e.g. pinned/hidden projects) use
    a bounded per-project fallback to keep the topological bound on
    watchdog resources while preserving event attribution.
    """

    _MAX_FALLBACK_PER_PROJECT_WATCHES = 32

    def __init__(self, debounce_delay: float = DEBOUNCE_DELAY) -> None:
        self._observer = Observer()
        self._observer.start()
        self._watches: dict[str, object] = {}
        self._handlers: dict[str, _SaipenEventHandler] = {}
        # PERF-001: a router maps scan_root -> {project_root: project_path}
        # so an event arriving on a scan-root watch is published for the
        # exact owning project. Per-project fallback paths are also
        # tracked here for cleanup.
        self._root_router: dict[str, dict[str, str]] = {}
        self._project_to_scope: dict[str, str] = {}
        self._fallback_projects: dict[str, object] = {}
        self._lock = threading.Lock()
        self._stopped = False
        self._debounce_delay = debounce_delay

    def sync(self, roots: list[str], scan_roots: list[str] | None = None) -> None:
        """Reconcile the watch set with the current known projects.

        PERF-001: when ``scan_roots`` is provided, schedule at most one
        recursive watchdog watch per scan root, and a per-scan-root router
        maps incoming event paths back to the owning project. Projects that
        do not fall beneath any configured scan root use a bounded per-
        project fallback. When ``scan_roots`` is None or empty the watcher
        falls back to the legacy per-project topology (still bounded by
        ``_MAX_FALLBACK_PER_PROJECT_WATCHES``).
        """
        if self._stopped:
            return
        wanted = {r for r in roots if (Path(r) / ".saipen").is_dir()}
        if scan_roots:
            self._sync_by_scan_roots(wanted, scan_roots)
            return
        with self._lock:
            current = set(self._watches) | set(self._fallback_projects)
        for root in current - wanted:
            self.unwatch(root)
        for root in wanted:
            if root in self._watches or root in self._fallback_projects:
                continue
            if len(self._fallback_projects) >= self._MAX_FALLBACK_PER_PROJECT_WATCHES:
                break
            self._watch_project_fallback(root)

    def _sync_by_scan_roots(
        self, wanted: set[str], scan_roots: list[str]
    ) -> None:
        """PERF-001: one recursive watch per scan root, router per project."""
        # Normalize scan roots to lowercase posix for prefix matching.
        normalized_scans = [
            (self._normpath(scan_root), scan_root) for scan_root in scan_roots
        ]
        projects_by_scan: dict[str, list[str]] = {}
        fallback: list[str] = []
        for project in sorted(wanted):
            scope = self._matching_scan_root(project, normalized_scans)
            if scope is not None:
                projects_by_scan.setdefault(scope, []).append(project)
            else:
                fallback.append(project)

        # Tear down scan-root watches whose project set is now empty.
        for scope in list(self._root_router):
            if scope not in projects_by_scan:
                self._unwatch_scan_root(scope)

        # Schedule / refresh scan-root watches.
        for scope, projects in projects_by_scan.items():
            self._watch_scan_root(scope, projects)

        # Tear down stale per-project fallback watches.
        for project in list(self._fallback_projects):
            if project not in fallback:
                self._unwatch_project_fallback(project)

        # Add new per-project fallback watches, bounded.
        current_fallback = len(self._fallback_projects)
        for project in fallback:
            if project in self._fallback_projects:
                continue
            if (
                current_fallback + (1 if project not in self._fallback_projects else 0)
                > self._MAX_FALLBACK_PER_PROJECT_WATCHES
            ):
                # Bound reached: drop this project from observation rather
                # than exceed the limit. The next sync() will retry.
                continue
            self._watch_project_fallback(project)
            current_fallback += 1

    def _matching_scan_root(
        self,
        project: str,
        normalized_scans: list[tuple[str, str]],
    ) -> str | None:
        project_norm = self._normpath(project)
        # Prefer the longest matching scan root -- a project beneath a
        # deeper drive mounts to the deepest configured scope, so its
        # sibling projects cannot be conflated across mounts.
        best: tuple[int, str] | None = None
        for scan_norm, scan_orig in normalized_scans:
            if self._is_under(project_norm, scan_norm):
                if best is None or len(scan_norm) > best[0]:
                    best = (len(scan_norm), scan_orig)
        return best[1] if best else None

    @staticmethod
    def _normpath(path_str: str) -> str:
        return path_str.replace("\\", "/").rstrip("/").lower()

    @staticmethod
    def _is_under(path_norm: str, scope_norm: str) -> bool:
        return path_norm == scope_norm or path_norm.startswith(scope_norm + "/")

    def _watch_scan_root(self, scope: str, projects: list[str]) -> None:
        if scope in self._root_router:
            # Already scheduled; just refresh the router.
            self._root_router[scope] = {p: p for p in projects}
            for p in projects:
                self._project_to_scope[p] = scope
            return
        scan_path = Path(scope)
        if not scan_path.is_dir():
            # Configure-time scope no longer accessible; degrade to per-project.
            for project in projects:
                if project not in self._watches and project not in self._fallback_projects:
                    self._watch_project_fallback(project)
            return
        try:
            handler = _RootRouterHandler(
                scope, self._root_router, debounce_delay=self._debounce_delay
            )
            watch = self._observer.schedule(
                handler, str(scan_path), recursive=True
            )
            self._watches[scope] = watch
            self._handlers[scope] = handler
            self._root_router[scope] = {p: p for p in projects}
            for p in projects:
                self._project_to_scope[p] = scope
        except OSError as e:
            print(
                f"SAIPENVIEW: watcher failed to watch scan root {scope}: {e}",
                file=sys.stderr,
            )
            for project in projects:
                self._watch_project_fallback(project)

    def _unwatch_scan_root(self, scope: str) -> None:
        watch = self._watches.pop(scope, None)
        handler = self._handlers.pop(scope, None)
        for project in self._root_router.pop(scope, {}):
            self._project_to_scope.pop(project, None)
        if handler is not None:
            handler.cancel()
        if watch is not None:
            try:
                self._observer.unschedule(watch)
            except OSError as e:
                print(
                    f"SAIPENVIEW: watcher failed to unwatch {scope}: {e}",
                    file=sys.stderr,
                )

    def _watch_project_fallback(self, root: str) -> None:
        saipen_dir = Path(root) / ".saipen"
        if not saipen_dir.is_dir():
            return
        try:
            handler = _SaipenEventHandler(root, debounce_delay=self._debounce_delay)
            watch = self._observer.schedule(
                handler, str(saipen_dir), recursive=True
            )
            self._fallback_projects[root] = watch
            # Keep a parallel _handlers entry so cancel()/stop() can find it.
            self._handlers[root] = handler
        except OSError as e:
            print(
                f"SAIPENVIEW: watcher failed to watch {root}: {e}", file=sys.stderr
            )

    def _unwatch_project_fallback(self, root: str) -> None:
        watch = self._fallback_projects.pop(root, None)
        handler = self._handlers.pop(root, None)
        if handler is not None:
            handler.cancel()
        if watch is not None:
            try:
                self._observer.unschedule(watch)
            except OSError as e:
                print(
                    f"SAIPENVIEW: watcher failed to unwatch {root}: {e}",
                    file=sys.stderr,
                )

    def watch(self, root: str) -> None:
        """Watch one project's .saipen/ dir (no-op if absent or already watched).

        Kept for API compat. With ``scan_roots`` provided at ``sync()``,
        the per-project path is reserved for the bounded fallback; this
        method delegates to the per-project fallback schedule so external
        callers (tests, single-project callers) get the old behaviour.
        """
        if self._stopped:
            return
        if root in self._watches or root in self._fallback_projects:
            return
        self._watch_project_fallback(root)

    def unwatch(self, root: str) -> None:
        """Stop watching a project and cancel its pending debounce timers."""
        with self._lock:
            handler = self._handlers.pop(root, None)
            watch = self._watches.pop(root, None)
            fallback_watch = self._fallback_projects.pop(root, None)
            if fallback_watch is not None and watch is None:
                watch = fallback_watch
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
            scope = self._project_to_scope.pop(root, None)
            if scope is not None and scope in self._root_router:
                self._root_router[scope].pop(root, None)

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
            self._root_router.clear()
            self._project_to_scope.clear()
            self._fallback_projects.clear()
        try:
            self._observer.stop()
            self._observer.join(timeout=0.5)
        except (RuntimeError, OSError):
            pass

    def revive(self) -> None:
        """CORE-005: make a stopped watcher usable again.

        A watchdog Observer cannot be restarted after stop(), so a stopped
        watcher gets a fresh Observer. Idempotent: an already-live watcher
        stays untouched. Known roots are NOT re-watched here -- the caller
        follows up with sync(roots) so the restarted Api re-watches them.
        """
        with self._lock:
            if not self._stopped:
                return
            self._observer = Observer()
            self._observer.start()
            self._stopped = False
            self._handlers.clear()
            self._watches.clear()
            self._root_router.clear()
            self._project_to_scope.clear()
            self._fallback_projects.clear()
