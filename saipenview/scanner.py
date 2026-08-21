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
    """
    projects: list[ProjectStatus] = field(default_factory=list)
    worktrees: list[dict] = field(default_factory=list)
    complete: bool = True

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
):
    """Walk a scan root, yielding discovered project Paths.

    PERF-003: when *collect_worktrees* is True, also accumulates linked-worktree
    records during the same traversal so callers never need a second walk.
    Yields either a Path (project) or a dict (worktree record) depending on
    *collect_worktrees*.
    """
    combined = EXCLUDE_DIRS | (extra_excludes or set())
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
        if collect_worktrees:
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
) -> Iterator[Path]:
    for root in scan_roots:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            continue
        yield from _walk_with_depth_limit(root_path, max_depth, delay, extra_excludes)


PER_ROOT_TIMEOUT_SECONDS = 120


def _scan_one_root(
    root: str,
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
    *,
    collect_worktrees: bool = False,
) -> tuple[list[ProjectStatus], list[dict]]:
    """Walk one scan root.

    PERF-003: returns (projects, worktrees) in a single traversal when
    *collect_worktrees* is True.
    """
    projects: list[ProjectStatus] = []
    worktrees: list[dict] = []
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return projects, worktrees
    for item in _walk_with_depth_limit(
        root_path, max_depth, delay, extra_excludes,
        collect_worktrees=collect_worktrees,
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
    root: str, max_depth: int, delay: float, extra_excludes: set[str] | None
) -> tuple[list[ProjectStatus], list[dict]]:
    # CORE-005: the in-flight reservation is now taken atomically in scan()
    # (before worker submission), so the worker only RELEASES it. This avoids
    # two concurrent scans both enqueuing a worker for the same root and makes
    # "owned by another scan" the only skip reason.
    ckey = canonical_key(root)
    try:
        _set_scan_progress(root=root)
        projects, worktrees = _scan_one_root(
            root, max_depth, delay, extra_excludes, collect_worktrees=True
        )
        return projects, worktrees
    finally:
        with _inflight_lock:
            _inflight_roots.pop(ckey, None)
        with _progress_lock:
            _scan_progress["roots_done"] += 1
            total = _scan_progress.get("roots_total", 1)
            _scan_progress["pct"] = min(99, int(_scan_progress["roots_done"] * 100 / total))


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
    # Stale-root quarantine (T-138 layer 2): a missing drive/root is surfaced,
    # never silently dropped from the scan set -- and it stays in the set, so
    # when the drive returns the next scan picks it up again automatically.
    for r in roots:
        if not Path(r).exists():
            _push_error(f"scan root missing, quarantined until it returns: {r}")
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
    complete = True
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(roots), 32))
    futures = {
        pool.submit(_scan_worker, root, max_depth, delay, extra_excludes): root
        for root in roots
    }
    try:
        for future in concurrent.futures.as_completed(
            futures, timeout=PER_ROOT_TIMEOUT_SECONDS + 5
        ):
            root = futures[future]
            try:
                root_projects, root_worktrees = future.result(timeout=0)
                projects.extend(root_projects)
                all_worktrees.extend(root_worktrees)
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
        # A root that blew the overall timeout is abandoned, but its worker
        # thread is still alive (daemon). Give it a bounded grace window so a
        # mid-run git subprocess can't leave a dead _readerthread at process
        # exit (T-179 / Bad file descriptor shutdown crash).
        concurrent.futures.wait(pending, timeout=30)
    _set_scan_progress(
        pct=100, root="", roots_done=_scan_progress.get("roots_total", 0)
    )
    pool.shutdown(wait=False)
    seen = set()
    deduped = []
    for p in projects:
        if _is_garbage_root(p.root):
            continue
        k = canonical_key(str(p.root))
        if k not in seen:
            seen.add(k)
            deduped.append(p)
    return ScanOutcome(projects=deduped, worktrees=all_worktrees, complete=complete)


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
        self._gen = _next_gen()

    def _do_scan(self) -> None:
        """Run one scan cycle, publishing results only if the epoch is still current."""
        result = scan(
            self._scan_roots,
            max_depth=self._max_depth,
            delay=self._delay,
            extra_excludes=self._extra_excludes,
        )
        # CORE-010: re-check stop + generation AFTER scan completes.
        if self._stop_event.is_set() or not _is_gen_current(self._gen):
            return
        # Pass both projects list and complete flag for backward compat
        # with callbacks that accept (projects, complete=False).
        self._on_result(result.projects, complete=result.complete)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not _is_gen_current(self._gen):
                    break
                if self._on_scan_start:
                    self._on_scan_start()
                self._do_scan()
            except (OSError, ValueError) as e:
                _push_error(f"background scan failed: {e}")
                print(
                    f"SAIPENVIEW: BackgroundScanner._loop error: {e}", file=sys.stderr
                )
            self._stop_event.wait(self._interval)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        # CORE-010: acquire a fresh epoch on start so a previously-stopped
        # scanner's old generation can never match the current one.
        self._gen = _next_gen()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def rescan_now(self) -> None:
        """Manual rescan participates in the newest-request-wins generation model."""
        if not _is_gen_current(self._gen):
            return
        if self._on_scan_start:
            self._on_scan_start()
        self._do_scan()

    def stop(self) -> None:
        _next_gen()
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
