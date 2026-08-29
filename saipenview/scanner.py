"""Walks local drives to find SAIPEN projects (dirs containing .saipen/STATE.md)."""

import collections
import concurrent.futures
import os
import string
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from saipenview.parser import ProjectStatus, load_project
from saipenview.paths import canonical, canonical_key

# PERF-007: process-wide registry of roots with in-flight workers.
# Prevents duplicate workers for the same root across scan cycles.
_inflight_lock = threading.Lock()
_inflight_roots: dict[str, str] = {}  # canonical_root -> status ("running")


@dataclass(frozen=True)
class ScanOutcome:
    """The result of a scan, distinguishing complete success from partial/failure.

    CORE-011: callers (especially the cache) must know whether an empty
    result means 'no projects exist' (complete=True) or 'scan failed/was
    interrupted' (complete=False), so the cache can decide whether to
    replace or preserve existing rows.
    PERF-003: worktrees collected during the same traversal as projects.
    CORE-001: cache authority is per scanned ROOT, not one global boolean.
    ``completed_roots`` lists the canonical roots this scan authoritatively
    covered (their result is trustworthy for replace/add/remove); the
    remaining requested roots are "unresolved" -- missing, skipped by an
    in-flight scan, or timed out -- and callers must preserve existing rows
    beneath them.
    """

    projects: list[ProjectStatus] = field(default_factory=list)
    worktrees: list[dict] = field(default_factory=list)
    complete: bool = True
    completed_roots: list[str] = field(default_factory=list)
    unresolved_roots: list[str] = field(default_factory=list)


_scan_errors: collections.deque[dict] = collections.deque(maxlen=20)
_scan_progress: dict = {"pct": 0, "root": "", "roots_done": 0, "roots_total": 0}
_progress_lock = threading.Lock()


def get_scan_errors() -> list[str]:
    return [e["message"] for e in _scan_errors]


def get_scan_error_log() -> list[dict]:
    return list(_scan_errors)


def get_scan_progress() -> dict:
    with _progress_lock:
        return dict(_scan_progress)


def _set_scan_progress(**kw) -> None:
    with _progress_lock:
        _scan_progress.update(kw)


def _push_error(msg: str) -> None:
    import datetime

    _scan_errors.append(
        {
            "time": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "message": msg,
        }
    )


EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "$Recycle.Bin",
    "ProgramData",
    "AppData",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "__pycache__",
    "$RECYCLE.BIN",
    "System Volume Information",
    "Local",
    "Roaming",
    "Microsoft",
    "Packages",
    "vendor",
    ".cache",
    ".cargo",
    ".rustup",
    ".nuget",
    ".gradle",
    ".m2",
    ".electron",
    ".vs",
    "obj",
    "bin",
    "target",
    "out",
    "dist",
    "build",
    # Garbage/temp/test dirs that should never contain real SAIPEN projects
    "_TEMP_",
    "tmp",
    "temp",
    "Temp",
    "TMP",
    "TEMP",
    "tests",
    "test",
    "Test",
    "Tests",
    "scratch",
    "backup",
    "Backup",
    "cache",
    "CACHE",
    "log",
    "logs",
    "Logs",
    "trash",
}

# Path components that mark a project root as garbage (test fixture, temp,
# scratch) and exclude from scan results even if reached via os.walk.
# Case-insensitive check against each path part.
GARBAGE_PATH_MARKERS: set[str] = {
    "_temp_",
    "pytest-of-",
    "tmp",
    "scratch",
    "test-fixture",
    "__pycache__",
    ".pytest_cache",
}


def _is_garbage_root(root: Path) -> bool:
    """True if root path contains any GARBAGE_PATH_MARKERS component."""
    for part in root.parts:
        lower = part.lower()
        for marker in GARBAGE_PATH_MARKERS:
            if marker in lower:
                return True
    return False


MAX_SCAN_DEPTH = 8
SCAN_INTER_DIR_DELAY = 0.001
SCAN_DELAY_EVERY_N = 100
SYSTEM_DRIVE = "C:\\"


# --- Linked worktree detection ---
# A git-linked worktree has .git as a FILE (containing the path to the main
# repo's .git directory). Never mixed into the normal .saipen/ project list.


def find_linked_worktrees(
    scan_roots: list[str],
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
) -> list[dict]:
    """Walk scan roots looking for git-linked worktrees: directories where .git
    is a FILE (containing the path to the main repo's .git dir) and there is
    no .saipen/ directory (so it's not already tracked as a project).
    Returns [{root: str, name: str, git_dir: str}] sorted by name."""
    results = []
    combined = EXCLUDE_DIRS | (extra_excludes or set())
    for root in scan_roots:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            continue
        dir_count = 0
        for dirpath, dirnames, _filenames in os.walk(
            root_path, topdown=True, onerror=lambda e: None
        ):
            rel = Path(dirpath).relative_to(root_path)
            depth = len(rel.parts) if str(rel) != "." else 0
            if depth >= max_depth:
                dirnames.clear()
            dirnames[:] = [
                d
                for d in dirnames
                if d not in combined and not d.startswith("$") and not d.startswith(".")
            ]
            dir_count += 1
            if delay and dir_count % SCAN_DELAY_EVERY_N == 0:
                time.sleep(delay)
            git_path = Path(dirpath) / ".git"
            saipen_path = Path(dirpath) / ".saipen"
            if git_path.is_file() and not saipen_path.is_dir():
                try:
                    git_dir_content = git_path.read_text(encoding="utf-8").strip()
                    results.append(
                        {
                            "root": str(Path(dirpath).resolve()),
                            "name": Path(dirpath).name,
                            "git_dir": git_dir_content,
                        }
                    )
                except (OSError, ValueError) as e:
                    # Don't drop the worktree just because its marker file
                    # wouldn't read -- that would silently hide the very thing
                    # this function exists to surface. Report it and still list
                    # the worktree, with git_dir left unknown (T-063).
                    _push_error(f"linked worktree at {dirpath}: .git unreadable: {e}")
                    results.append(
                        {
                            "root": str(Path(dirpath).resolve()),
                            "name": Path(dirpath).name,
                            "git_dir": "",
                        }
                    )
                # Don't recurse into a worktree's own subdirs
                dirnames.clear()
    results.sort(key=lambda x: x["name"].lower())
    return results


def local_drives() -> list[str]:
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(root)
    return drives


def _walk_with_depth_limit(
    root_path: Path,
    max_depth: int,
    delay: float,
    extra_excludes: set[str] | None = None,
    *,
    collect_worktrees: bool = False,
    cancel: threading.Event | None = None,
):
    """Walk a scan root, yielding discovered project Paths.

    PERF-003: when *collect_worktrees* is True, also accumulates linked-worktree
    records during the same traversal so callers never need a second walk.
    Yields either a Path (project) or a dict (worktree record) depending on
    *collect_worktrees*.

    PERF-006: when *cancel* is set the walk stops cooperatively -- checked
    before every directory descent -- instead of grinding through a wedged
    drive after its owner is gone.
    """
    combined = EXCLUDE_DIRS | (extra_excludes or set())
    dir_count = 0
    for dirpath, dirnames, _filenames in os.walk(
        root_path, topdown=True, onerror=lambda e: None
    ):
        if cancel is not None and cancel.is_set():
            return
        rel = Path(dirpath).relative_to(root_path)
        depth = len(rel.parts) if str(rel) != "." else 0
        if depth >= max_depth:
            dirnames.clear()
        dirnames[:] = [
            d
            for d in dirnames
            if d not in combined
            and not d.startswith("$")
            and not (d.startswith(".") and d != ".saipen")
        ]
        dir_count += 1
        if delay and dir_count % SCAN_DELAY_EVERY_N == 0:
            time.sleep(delay)
        if ".saipen" in dirnames:
            dirnames.remove(".saipen")
            candidate = Path(dirpath) / ".saipen" / "STATE.md"
            if candidate.is_file():
                yield Path(dirpath)
        # PERF-003: detect linked worktrees in the same pass.
        if collect_worktrees and ".git" in _filenames:
            git_path = Path(dirpath) / ".git"
            saipen_path = Path(dirpath) / ".saipen"
            if git_path.is_file() and not saipen_path.is_dir():
                try:
                    git_dir_content = git_path.read_text(encoding="utf-8").strip()
                except (OSError, ValueError) as e:
                    _push_error(f"linked worktree at {dirpath}: .git unreadable: {e}")
                    git_dir_content = ""
                yield {
                    "root": str(Path(dirpath).resolve()),
                    "name": Path(dirpath).name,
                    "git_dir": git_dir_content,
                }
                # Don't recurse into a worktree's own subdirs
                dirnames.clear()
                # Deliberately NOT clearing dirnames here. The old code did,
                # on the theory that anything below a project root is that
                # project's own concern (test fixtures, sub-.saipen/ examples)
                # -- but that also hid REAL nested projects: a repo that is
                # itself a SAIPEN project (V:\...\__CODE) routinely contains
                # other projects beneath it (_PY\_SAIPENVIEW and friends), and
                # the clear() made them invisible. Test fixtures no longer
                # need the guard anyway: they live under tests/scenarios/
                # which EXCLUDE_DIRS already prunes, and GARBAGE_PATH_MARKERS
                # catches _TEMP_/pytest-of-/scratch nests at yield time.


def find_saipen_roots(
    scan_roots: list[str],
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
    cancel: threading.Event | None = None,
) -> Iterator[Path]:
    for root in scan_roots:
        if cancel is not None and cancel.is_set():
            return
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            continue
        yield from _walk_with_depth_limit(
            root_path, max_depth, delay, extra_excludes, cancel=cancel
        )


PER_ROOT_TIMEOUT_SECONDS = 120


def _scan_one_root(
    root: str,
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
    *,
    collect_worktrees: bool = False,
    cancel: threading.Event | None = None,
) -> tuple[list[ProjectStatus], list[dict]]:
    """Walk one scan root.

    PERF-003: returns (projects, worktrees) in a single traversal when
    *collect_worktrees* is True. PERF-006: stops early when *cancel* is set.
    """
    projects: list[ProjectStatus] = []
    worktrees: list[dict] = []
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return projects, worktrees
    for item in _walk_with_depth_limit(
        root_path,
        max_depth,
        delay,
        extra_excludes,
        collect_worktrees=collect_worktrees,
        cancel=cancel,
    ):
        if isinstance(item, dict):
            worktrees.append(item)
            continue
        # item is a Path (project root)
        try:
            status = load_project(item)
        except (OSError, ValueError) as e:
            _push_error(f"failed to load project at {item}: {e}")
            continue
        if status is not None:
            if _is_garbage_root(item):
                _push_error(f"skipped garbage path: {item}")
                continue
            projects.append(status)
    return projects, worktrees


def _auto_roots() -> list[str]:
    """Auto-detected roots, excluding system drive to avoid disk thrash."""
    return [d for d in local_drives() if d.upper() != SYSTEM_DRIVE.upper()]


def _scan_worker(
    root: str,
    max_depth: int,
    delay: float,
    extra_excludes: set[str] | None,
    cancel: threading.Event | None = None,
) -> tuple[list[ProjectStatus], list[dict]]:
    # CORE-005: the in-flight reservation is now taken atomically in scan()
    # (before worker submission), so the worker only RELEASES it. This avoids
    # two concurrent scans both enqueuing a worker for the same root and makes
    # "owned by another scan" the only skip reason.
    ckey = canonical_key(root)
    try:
        # PERF-006: a worker whose cancellation fired before it started must
        # not begin any filesystem work -- it still releases its reservation
        # in the finally block (single owner of roots_done increment).
        if cancel is not None and cancel.is_set():
            return [], []
        _set_scan_progress(root=root)
        projects, worktrees = _scan_one_root(
            root,
            max_depth,
            delay,
            extra_excludes,
            collect_worktrees=True,
            cancel=cancel,
        )
        return projects, worktrees
    finally:
        with _inflight_lock:
            _inflight_roots.pop(ckey, None)
        with _progress_lock:
            _scan_progress["roots_done"] += 1
            total = _scan_progress.get("roots_total", 1) or 1
            _scan_progress["pct"] = min(
                99, int(_scan_progress["roots_done"] * 100 / total)
            )


def scan(
    scan_roots: list[str] | None = None,
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
    cancel: threading.Event | None = None,
) -> ScanOutcome:
    """Scan every root in parallel so one slow/hung drive cannot starve the rest.

    CORE-011: returns a ScanOutcome with complete/partial status.
    CORE-010: when cancel is set, returns immediately with zero roots.
    """
    if cancel is not None and cancel.is_set():
        _set_scan_progress(pct=0, root="", roots_done=0, roots_total=0)
        return ScanOutcome(projects=[], complete=True)
    raw_roots = scan_roots if scan_roots is not None else _auto_roots()
    # Canonical forms: absolute, case-normalised, symlink-resolved, drive
    # roots carry a single trailing separator (T-138 layer 1).
    roots = [canonical(r) for r in raw_roots]
    # W2-009 / T-138 layer 2: a missing drive/root is surfaced, never silently
    # dropped from the scan set -- and it stays in the set, so when the drive
    # returns the next scan picks it up again automatically.
    # Track missing roots so we can force the outcome to incomplete: a
    # temporarily offline drive must not be treated as authoritative empty.
    missing_roots: list[str] = []
    for r in roots:
        if not Path(r).exists():
            _push_error(f"scan root missing, quarantined until it returns: {r}")
            missing_roots.append(r)
    # Deduplicate roots by canonical key before parallel submission -- same
    # path scanned twice wastes a thread and can race on _scan_progress.
    seen_roots: set[str] = set()
    unique_roots: list[str] = []
    for r in roots:
        key = canonical_key(r)
        if key not in seen_roots:
            seen_roots.add(key)
            unique_roots.append(r)
    # CORE-005: reserve canonical roots atomically BEFORE submitting workers so
    # two concurrent scans cannot both enqueue a worker for the same root, and a
    # root already owned by another scan is skipped (not duplicated). Only the
    # owner releases the reservation (in _scan_worker's finally).
    with _inflight_lock:
        fresh_roots = [
            r for r in unique_roots if canonical_key(r) not in _inflight_roots
        ]
        for r in fresh_roots:
            _inflight_roots[canonical_key(r)] = "running"
    skipped = len(unique_roots) - len(fresh_roots)
    roots = fresh_roots
    if not roots:
        # Every requested root is owned by an in-flight scan: this scan is NOT
        # authoritative. Return incomplete so callers preserve the existing
        # cache instead of wiping it with a complete-empty result (CORE-005).
        _set_scan_progress(pct=100, root="", roots_done=skipped, roots_total=skipped)
        return ScanOutcome(projects=[], complete=(skipped == 0))
    _set_scan_progress(pct=0, root="", roots_done=0, roots_total=len(roots))
    projects: list[ProjectStatus] = []
    all_worktrees: list[dict] = []
    # CORE-001: only a scan that ran ALL requested roots without skip/
    # error/timeout is authoritative. Skipped roots were owned by another
    # scan, so we never saw those projects -- marking complete=True would
    # let callers treat partial data as authoritative.
    # W2-009: missing roots are also non-authoritative -- the scan cannot
    # guarantee it saw all projects when a configured root was unreachable.
    complete = skipped == 0 and not missing_roots
    # PERF-006: one cooperative cancellation event per scan() invocation.
    # Workers check it before every directory descent; the timeout paths set
    # it so running walks unwind promptly instead of grinding on after their
    # owner is gone (ThreadPoolExecutor workers are NOT daemon threads).
    internal_cancel = threading.Event()
    if cancel is not None:
        # Honor either the caller's event or this scan's own timeout path.
        class _EitherEvent:
            def is_set(self) -> bool:
                return cancel.is_set() or internal_cancel.is_set()

            def set(self) -> None:
                internal_cancel.set()

        both_cancel = _EitherEvent()  # type: ignore[assignment]
    else:
        both_cancel = internal_cancel
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(roots), 32))
    futures = {
        pool.submit(
            _scan_worker, root, max_depth, delay, extra_excludes, both_cancel
        ): root
        for root in roots
    }
    # CORE-001: per-root authority tracking. Every root submitted to a worker
    # starts as 'in_flight'; on success it moves to 'completed', on hard
    # failure/timeout it stays 'in_flight' (unresolved). The cache uses these
    # sets to replace rows beneath completed roots while preserving rows
    # beneath unresolved ones.
    completed: set[str] = set()
    try:
        for future in concurrent.futures.as_completed(
            futures, timeout=PER_ROOT_TIMEOUT_SECONDS + 5
        ):
            root = futures[future]
            try:
                root_projects, root_worktrees = future.result(timeout=0)
                projects.extend(root_projects)
                all_worktrees.extend(root_worktrees)
                completed.add(canonical_key(root))
            except concurrent.futures.TimeoutError:
                _push_error(
                    f"scan of {root} exceeded {PER_ROOT_TIMEOUT_SECONDS}s, skipped"
                )
                complete = False
            except OSError as e:
                _push_error(f"scan of {root} failed: {e}")
                complete = False
    except concurrent.futures.TimeoutError:
        _push_error("overall scan timeout reached, some roots skipped")
        complete = False
    pending = [f for f in futures if not f.done()]
    if pending:
        complete = False
        # PERF-006: tell still-running workers to stop cooperatively. The
        # INTERNAL event is set here; a caller's cancel Event is never ours
        # to mutate. Cancellation must never publish partial data as
        # authoritative -- `complete` above already stays False.
        internal_cancel.set()
        # CORE-002: resolve queued-future ownership before shutdown. A queued
        # future canceled here never runs _scan_worker, so its reservation
        # would leak forever -- remove it now. A future already running
        # (cancel() returns False) keeps its reservation and releases it in
        # _scan_worker's finally.
        for f in pending:
            if f.cancel():
                with _inflight_lock:
                    _inflight_roots.pop(canonical_key(futures[f]), None)
        # cancel_futures=False: everything still pending was already handed
        # to cancel() above; the pool must not cancel additional futures
        # without matching reservation cleanup.
        pool.shutdown(wait=False, cancel_futures=False)
        concurrent.futures.wait(pending, timeout=30)
    else:
        pool.shutdown(wait=False)
    _set_scan_progress(
        pct=100, root="", roots_done=_scan_progress.get("roots_total", 0)
    )
    seen = set()
    deduped = []
    for p in projects:
        if _is_garbage_root(p.root):
            continue
        k = canonical_key(str(p.root))
        if k not in seen:
            seen.add(k)
            deduped.append(p)
    # CORE-001: partition the originally requested roots into authoritative
    # (scanned) and unresolved (missing, skipped, failed) buckets. Skipped
    # roots are 'fresh' roots that scan() chose not to submit because another
    # scan owned them. Missing roots come from the upfront existence check.
    completed_roots = sorted(canonical(r) for r in unique_roots if canonical_key(r) in completed)
    unresolved = set()
    for r in missing_roots:
        unresolved.add(canonical_key(r))
    for r in unique_roots:
        if canonical_key(r) not in completed:
            unresolved.add(canonical_key(r))
    unresolved_roots = sorted(r for r in unique_roots if canonical_key(r) in unresolved)
    return ScanOutcome(
        projects=deduped,
        worktrees=all_worktrees,
        complete=complete,
        completed_roots=completed_roots,
        unresolved_roots=unresolved_roots,
    )


DEFAULT_RESCAN_SECONDS = 300


_current_gen = 0
_gen_lock = threading.Lock()


def _next_gen() -> int:
    global _current_gen
    with _gen_lock:
        _current_gen += 1
        return _current_gen


def _is_gen_current(gen: int) -> bool:
    with _gen_lock:
        return gen == _current_gen


class _GenCounter:
    """Per-scanner generation tracker.

    W2-008: the old module-global ``_current_gen`` meant that constructing a
    second BackgroundScanner invalidated every first one (its _gen was no
    longer == _current_gen).  Each scanner now owns an independent counter
    so scanners are isolation-safe: S1 running, S2 constructed+started,
    S1 continues unaffected.
    """

    __slots__ = ("_lock", "_gen")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gen = 0

    def next(self) -> int:
        with self._lock:
            self._gen += 1
            return self._gen

    def is_current(self, gen: int) -> bool:
        with self._lock:
            return gen == self._gen


class BackgroundScanner:
    """Runs `scan()` on a timer, delivering results to `on_result` off the main thread.

    CORE-010: Each start/request acquires an explicit current epoch; stop
    invalidates the previous one. Results are only published when the
    generating epoch is still current, so a stale scan after stop/replacement
    cannot deliver stale data.
    """

    def __init__(
        self,
        on_result: Callable[[list[ProjectStatus]], None],
        scan_roots: list[str] | None = None,
        interval_seconds: float = DEFAULT_RESCAN_SECONDS,
        max_depth: int = MAX_SCAN_DEPTH,
        delay: float = SCAN_INTER_DIR_DELAY,
        extra_excludes: set[str] | None = None,
        on_scan_start: Callable[[], None] | None = None,
    ):
        self._on_result = on_result
        self._scan_roots = scan_roots
        self._interval = interval_seconds
        self._max_depth = max_depth
        self._delay = delay
        self._extra_excludes = extra_excludes
        self._on_scan_start = on_scan_start
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()
        self._gen_counter = _GenCounter()
        self._gen = self._gen_counter.next()
        self._restart_pending = False
        self._restart_queued = False
        self._restart_reaper: threading.Thread | None = None

    def _do_scan(
        self,
        cancel_event: threading.Event | None = None,
        generation: int | None = None,
    ) -> None:
        """Run one scan cycle, publishing results only if the epoch is still current."""
        event = cancel_event if cancel_event is not None else self._stop_event
        gen = generation if generation is not None else self._gen
        result = scan(
            self._scan_roots,
            max_depth=self._max_depth,
            delay=self._delay,
            extra_excludes=self._extra_excludes,
            cancel=event,
        )
        if event.is_set() or not self._gen_counter.is_current(gen):
            return
        # PERF-001: pass the worktree list alongside the projects so the
        # consumer can skip its own second walk. Backward-compatible: the
        # worktrees travel as a keyword, and a ScanOutcome-aware consumer (the
        # Api cache) also receives them inside the projects object.
        self._on_result(
            result.projects, complete=result.complete, worktrees=result.worktrees
        )

    def _start_generation_locked(self) -> None:
        self._restart_pending = False
        self._restart_queued = False
        event = threading.Event()
        generation = self._gen_counter.next()
        self._stop_event = event
        self._gen = generation
        self._thread = threading.Thread(
            target=self._run_generation,
            args=(event, generation),
            daemon=True,
        )
        self._thread.start()

    def _run_generation(self, event: threading.Event, generation: int) -> None:
        self._scan_context = (event, generation)
        try:
            self._loop()
        finally:
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._restart_reaper = threading.Thread(
                        target=self._reap_generation,
                        args=(threading.current_thread(),),
                        daemon=True,
                    )
                    self._restart_reaper.start()

    def _reap_generation(self, thread: threading.Thread) -> None:
        thread.join()
        with self._lifecycle_lock:
            if self._restart_reaper is threading.current_thread():
                self._restart_reaper = None
            if self._thread is not thread:
                return
            self._thread = None
            self._restart_pending = False
            if self._restart_queued:
                self._start_generation_locked()

    def _loop(self) -> None:
        event, generation = self._scan_context
        try:
            while not event.is_set():
                if not self._gen_counter.is_current(generation):
                    break
                try:
                    if self._on_scan_start:
                        self._on_scan_start()
                    self._do_scan(event, generation)
                except (OSError, ValueError) as e:
                    _push_error(f"background scan failed: {e}")
                    print(
                        f"SAIPENVIEW: BackgroundScanner._loop error: {e}",
                        file=sys.stderr,
                    )
                event.wait(self._interval)
        except (OSError, ValueError) as e:
            _push_error(f"background scan failed: {e}")
            print(
                f"SAIPENVIEW: BackgroundScanner._loop error: {e}",
                file=sys.stderr,
            )

    def start(self) -> None:
        with self._lifecycle_lock:
            t = self._thread
            if t is not None and t.is_alive():
                if self._restart_pending:
                    self._restart_pending = False
                self._restart_queued = True
                return
            if t is not None:
                self._thread = None
            self._start_generation_locked()

    def rescan_now(self) -> None:
        """Manual rescan participates in the newest-request-wins generation model."""
        with self._lifecycle_lock:
            event = self._stop_event
            generation = self._gen
        if not self._gen_counter.is_current(generation):
            return
        if self._on_scan_start:
            self._on_scan_start()
        self._do_scan(event, generation)

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._restart_queued = False
            event = self._stop_event
            t = self._thread
            self._gen_counter.next()
            event.set()
        if t is None:
            return
        t.join(timeout=1)
        if not t.is_alive():
            with self._lifecycle_lock:
                if self._thread is t:
                    self._thread = None
        else:
            with self._lifecycle_lock:
                if self._thread is t:
                    self._restart_pending = True

    def is_alive(self) -> bool:
        """True when the coordinator thread exists and has not exited."""
        t = self._thread
        return t is not None and t.is_alive()
