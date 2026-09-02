"""Walks local drives to find SAIPEN projects (dirs containing .saipen/STATE.md)."""

import collections
import concurrent.futures
import inspect
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


def _lexical_root_key(root: str) -> str:
    """Cheap scheduling identity used before filesystem-touching preflight."""
    return os.path.normcase(os.path.normpath(os.fspath(root))).rstrip("\\/")


def _scan_root_task(
    raw_root: str,
    max_depth: int,
    delay: float,
    extra_excludes: set[str] | None,
    cancel: threading.Event,
) -> dict:
    """Preflight and scan one raw root inside its bounded worker.

    PERF-002: the root is reserved by its lexical key BEFORE any
    filesystem-touching canonical()/exists() preflight. If the same
    lexical root is already in flight (from a previous cycle whose worker
    timed out), this one returns SKIPPED immediately -- the previous
    worker is still alive and will eventually complete. After canonical
    resolution the reservation is upgraded to the canonical key; alias
    deduplication (two raw roots resolving to the same canonical path) is
    also handled atomically.
    """
    lexical = _lexical_root_key(raw_root)
    if cancel.is_set():
        return {"root": lexical, "status": "unresolved", "projects": [], "worktrees": []}
    # PERF-002: reserve by lexical key BEFORE any filesystem I/O. A
    # blocked canonical() will not prevent the reservation, so a later
    # scan cycle sees the root is already in flight and skips submitting
    # a duplicate worker. The reservation persists until the worker exits
    # (not until the coordinator times out), so timed-out roots stay
    # quarantined.
    with _inflight_lock:
        if lexical in _inflight_roots:
            _push_error(
                f"scan root {raw_root} already in flight, skipping duplicate"
            )
            return {
                "root": raw_root,
                "key": lexical,
                "status": "skipped",
                "projects": [],
                "worktrees": [],
            }
        _inflight_roots[lexical] = "running"
    # The canonical key that will be popped on exit; starts as lexical.
    _current_key = lexical
    try:
        if cancel.is_set():
            return {"root": lexical, "status": "unresolved", "projects": [], "worktrees": []}
        try:
            resolved = canonical(raw_root)
            key = canonical_key(resolved)
            if not Path(resolved).exists() or not Path(resolved).is_dir():
                _push_error(f"scan root missing, quarantined until it returns: {resolved}")
                return {
                    "root": resolved,
                    "key": key,
                    "status": "unresolved",
                    "projects": [],
                    "worktrees": [],
                }
        except (OSError, ValueError) as exc:
            _push_error(f"scan root preflight failed for {raw_root}: {exc}")
            return {
                "root": lexical,
                "key": lexical,
                "status": "unresolved",
                "projects": [],
                "worktrees": [],
            }
        # Upgrade reservation from lexical to canonical key if they differ.
        if key != lexical:
            with _inflight_lock:
                _inflight_roots.pop(lexical, None)
                if key in _inflight_roots:
                    return {
                        "root": resolved,
                        "key": key,
                        "status": "skipped",
                        "projects": [],
                        "worktrees": [],
                    }
                _inflight_roots[key] = "running"
            _current_key = key
        if cancel.is_set():
            return {"root": resolved, "key": key, "status": "unresolved", "projects": [], "worktrees": []}
        projects, worktrees = _scan_one_root(
            resolved,
            max_depth,
            delay,
            extra_excludes,
            collect_worktrees=True,
            cancel=cancel,
        )
        return {
            "root": resolved,
            "key": key,
            "status": "completed",
            "projects": projects,
            "worktrees": worktrees,
        }
    except (OSError, TypeError, ValueError) as exc:
        _push_error(f"scan of {resolved} failed: {exc}")
        return {"root": resolved, "key": key, "status": "unresolved", "projects": [], "worktrees": []}
    finally:
        with _inflight_lock:
            _inflight_roots.pop(_current_key, None)
        with _progress_lock:
            _scan_progress["roots_done"] += 1
            total = _scan_progress.get("roots_total", 1) or 1
            _scan_progress["pct"] = min(99, int(_scan_progress["roots_done"] * 100 / total))


# PERF-001/002: shared bounded executor pool. Reused across scan cycles
# so timed-out workers do not create unbounded thread accumulation.
# PERF-001: when a scan times out, its pool is quarantined -- the next
# scan creates a fresh pool instead of reusing capacity poisoned by
# non-cooperative stuck workers.  The old pool's remaining futures still
# decrement counters through the per-future callback, so refcounts
# remain correct across generations.
_SHARED_POOL_MAX = 32
_SHARED_POOL_LOCK = threading.Lock()
_SHARED_POOL: concurrent.futures.ThreadPoolExecutor | None = None
_SHARED_POOL_USERS = 0
_SHARED_POOL_FUTURES = 0
_SHARED_POOL_STALE = False  # PERF-001: set when timed-out futures exist
_QUARANTINED_FUTURES = 0


def _get_shared_pool(
    n_workers: int,
) -> concurrent.futures.ThreadPoolExecutor | None:
    global _SHARED_POOL, _SHARED_POOL_USERS, _SHARED_POOL_STALE
    with _SHARED_POOL_LOCK:
        available = _SHARED_POOL_MAX - _QUARANTINED_FUTURES
        if available <= 0:
            return None
        if _SHARED_POOL is None or _SHARED_POOL_STALE:
            old_pool = _SHARED_POOL
            _SHARED_POOL_STALE = False
            if old_pool is not None:
                old_pool.shutdown(wait=False)
            _SHARED_POOL = concurrent.futures.ThreadPoolExecutor(
                max_workers=min(max(n_workers, 1), available)
            )
        _SHARED_POOL_USERS += 1
        return _SHARED_POOL


def _release_shared_pool() -> None:
    global _SHARED_POOL, _SHARED_POOL_USERS
    pool = None
    with _SHARED_POOL_LOCK:
        _SHARED_POOL_USERS -= 1
        if _SHARED_POOL_USERS == 0 and _SHARED_POOL_FUTURES == 0:
            pool = _SHARED_POOL
            _SHARED_POOL = None
    if pool is not None:
        pool.shutdown(wait=False)


def _track_shared_future(future: concurrent.futures.Future) -> None:
    global _SHARED_POOL_FUTURES
    with _SHARED_POOL_LOCK:
        _SHARED_POOL_FUTURES += 1
    # PERF-001: capture the owning pool so this callback always
    # decrements the correct generation, even if _SHARED_POOL has
    # been replaced by a fresh pool before this future completes.
    owning_pool = _SHARED_POOL

    def done(_future, _pool=owning_pool) -> None:
        global _SHARED_POOL, _SHARED_POOL_FUTURES
        pool_to_check = None
        with _SHARED_POOL_LOCK:
            _SHARED_POOL_FUTURES -= 1
            if _SHARED_POOL_USERS == 0 and _SHARED_POOL_FUTURES == 0:
                pool_to_check = _SHARED_POOL
                _SHARED_POOL = None
        # PERF-001: only shut down if the pool we captured is still the
        # live one.  A replaced (quarantined) pool is abandoned and will
        # be garbage-collected once its remaining futures complete.
        if pool_to_check is not None and pool_to_check is _pool:
            pool_to_check.shutdown(wait=False)

    future.add_done_callback(done)


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
    global _QUARANTINED_FUTURES
    if cancel is not None and cancel.is_set():
        _set_scan_progress(pct=0, root="", roots_done=0, roots_total=0)
        return ScanOutcome(projects=[], complete=True)
    raw_roots = scan_roots if scan_roots is not None else _auto_roots()
    # PERF-002: raw roots enter workers immediately. canonical() and existence
    # probing may touch a disconnected drive, so neither may run serially on
    # the coordinator before healthy roots can start.
    _set_scan_progress(pct=0, root="", roots_done=0, roots_total=len(raw_roots))
    internal_cancel = threading.Event()
    if cancel is not None:
        class _EitherEvent:
            def is_set(self) -> bool:
                return cancel.is_set() or internal_cancel.is_set()

        both_cancel = _EitherEvent()  # type: ignore[assignment]
    else:
        both_cancel = internal_cancel
    # PERF-002: reuse the shared bounded executor instead of creating a
    # fresh pool per cycle whose running workers were abandoned on timeout.
    pool = _get_shared_pool(len(raw_roots))
    if pool is None:
        _push_error("scan pool capacity exhausted, all roots skipped")
        return ScanOutcome(
            projects=[], worktrees=[], complete=False,
            completed_roots=[], unresolved_roots=[_lexical_root_key(r) for r in raw_roots],
        )
    futures = {
        pool.submit(
            _scan_root_task, raw, max_depth, delay, extra_excludes, both_cancel
        ): raw
        for raw in raw_roots
    }
    for future in futures:
        _track_shared_future(future)
    projects: list[ProjectStatus] = []
    all_worktrees: list[dict] = []
    completed: dict[str, str] = {}
    unresolved: dict[str, str] = {}
    complete = True
    try:
        for future in concurrent.futures.as_completed(
            futures, timeout=max(float(PER_ROOT_TIMEOUT_SECONDS), 0.01)
        ):
            raw = futures[future]
            lexical = _lexical_root_key(raw)
            try:
                result = future.result(timeout=0)
            except (OSError, ValueError) as exc:
                _push_error(f"scan of {raw} failed: {exc}")
                unresolved[lexical] = lexical
                complete = False
                continue
            root = result.get("root", lexical)
            key = result.get("key", lexical)
            if result.get("status") == "completed":
                completed[key] = root
                projects.extend(result.get("projects", []))
                all_worktrees.extend(result.get("worktrees", []))
            else:
                unresolved[key] = root
                complete = False
    except concurrent.futures.TimeoutError:
        _push_error("overall scan timeout reached, some roots skipped")
        complete = False
    pending = [future for future in futures if not future.done()]
    if pending:
        complete = False
        internal_cancel.set()
        for future in pending:
            raw = futures[future]
            if future.cancel():
                unresolved[_lexical_root_key(raw)] = _lexical_root_key(raw)
            else:
                unresolved[_lexical_root_key(raw)] = _lexical_root_key(raw)
                # PERF-001: running non-cooperative future = quarantined
                with _SHARED_POOL_LOCK:
                    _QUARANTINED_FUTURES += 1
                def _quarantine_cleanup(_f, _id=id(future)):
                    global _QUARANTINED_FUTURES
                    with _SHARED_POOL_LOCK:
                        _QUARANTINED_FUTURES = max(0, _QUARANTINED_FUTURES - 1)
                future.add_done_callback(_quarantine_cleanup)
        # PERF-001: quarantine this pool generation -- its non-cooperative
        # workers occupy capacity that must not block healthy roots in
        # the next scan.  _get_shared_pool will create a fresh pool.
        with _SHARED_POOL_LOCK:
            _SHARED_POOL_STALE = True
    _set_scan_progress(
        pct=100, root="", roots_done=len(raw_roots), roots_total=len(raw_roots)
    )
    seen = set()
    deduped = []
    for project in projects:
        if _is_garbage_root(project.root):
            continue
        key = canonical_key(str(project.root))
        if key not in seen:
            seen.add(key)
            deduped.append(project)
    completed_roots = sorted(set(completed.values()))
    unresolved_roots = sorted(set(unresolved.values()))
    if unresolved_roots:
        complete = False
    outcome = ScanOutcome(
        projects=deduped,
        worktrees=all_worktrees,
        complete=complete,
        completed_roots=completed_roots,
        unresolved_roots=unresolved_roots,
    )
    _release_shared_pool()
    return outcome


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
        epoch_source: Callable[[], int] | None = None,
    ):
        self._on_result = on_result
        self._scan_roots = scan_roots
        self._interval = interval_seconds
        self._max_depth = max_depth
        self._delay = delay
        self._extra_excludes = extra_excludes
        self._on_scan_start = on_scan_start
        # W2-001: every _do_scan captures the api's current scan epoch at
        # request start so a newer manual rescan can supersede this in-flight
        # publication. None means the on_result callback does not accept
        # epoch (legacy behaviour preserved).
        self._epoch_source = epoch_source
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
        # W2-001: capture the api scan epoch at REQUEST START, before the
        # filesystem work. A newer manual rescan bumps the epoch while this
        # scan runs; when it finishes, _set_cache rejects its stale epoch so
        # the older result can never roll back the manual one.
        request_epoch = self._epoch_source() if self._epoch_source is not None else None
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
        callback_kwargs = {
            "complete": result.complete,
            "worktrees": result.worktrees,
            "completed_roots": result.completed_roots,
            "unresolved_roots": result.unresolved_roots,
        }
        if request_epoch is not None:
            callback_kwargs["epoch"] = request_epoch
        # Preserve consumers that intentionally implement the original
        # list-only callback. New consumers receive full provenance; old
        # consumers remain valid without catching a TypeError raised inside
        # their own callback body.
        try:
            parameters = inspect.signature(self._on_result).parameters
            accepts_kwargs = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if accepts_kwargs:
                supported_kwargs = callback_kwargs
            else:
                supported_kwargs = {
                    name: value
                    for name, value in callback_kwargs.items()
                    if name in parameters
                }
        except (TypeError, ValueError):
            supported_kwargs = callback_kwargs
        self._on_result(result.projects, **supported_kwargs)

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
