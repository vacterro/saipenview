"""Walks local drives to find SAIPEN projects (dirs containing .saipen/STATE.md)."""

import collections
import concurrent.futures
import os
import string
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from saipenview.parser import ProjectStatus, load_project

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
                except Exception as e:
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
):
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
                # Found a project root -- anything nested below is that
                # project's own concern (test fixtures, sub-.saipen/
                # examples), never an independent project to list.
                dirnames.clear()


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
) -> list[ProjectStatus]:
    projects = []
    for project_root in find_saipen_roots(
        [root], max_depth=max_depth, delay=delay, extra_excludes=extra_excludes
    ):
        try:
            status = load_project(project_root)
        except Exception as e:
            # One malformed project (bad encoding, corrupt frontmatter, ...)
            # MUST NOT take the rest of this root -- let alone every other
            # root -- down with it. Skip it, surface it, keep walking.
            _push_error(f"failed to load project at {project_root}: {e}")
            continue
        if status is not None:
            if _is_garbage_root(project_root):
                _push_error(f"skipped garbage path: {project_root}")
                continue
            projects.append(status)
    return projects


def _auto_roots() -> list[str]:
    """Auto-detected roots, excluding system drive to avoid disk thrash."""
    return [d for d in local_drives() if d.upper() != SYSTEM_DRIVE.upper()]


def _scan_worker(
    root: str, max_depth: int, delay: float, extra_excludes: set[str] | None
) -> list[ProjectStatus]:
    _set_scan_progress(root=root)
    result = _scan_one_root(root, max_depth, delay, extra_excludes)
    with _progress_lock:
        _scan_progress["roots_done"] += 1
        total = _scan_progress.get("roots_total", 1)
        _scan_progress["pct"] = min(99, int(_scan_progress["roots_done"] * 100 / total))
    return result


def scan(
    scan_roots: list[str] | None = None,
    max_depth: int = MAX_SCAN_DEPTH,
    delay: float = SCAN_INTER_DIR_DELAY,
    extra_excludes: set[str] | None = None,
) -> list[ProjectStatus]:
    """Scans every root in parallel so one slow/hung drive can't starve the rest."""
    raw_roots = scan_roots if scan_roots is not None else _auto_roots()
    roots = [
        r + "\\" if r.endswith(":") else (r if r.endswith(("\\", "/")) else r + "\\")
        for r in raw_roots
    ]
    # Deduplicate roots before parallel submission -- same path scanned
    # twice wastes a thread and can race on _scan_progress counters.
    seen_roots = set()
    unique_roots = []
    for r in roots:
        key = r.upper()
        if key not in seen_roots:
            seen_roots.add(key)
            unique_roots.append(r)
    roots = unique_roots
    if not roots:
        return []
    _set_scan_progress(pct=0, root="", roots_done=0, roots_total=len(roots))
    projects: list[ProjectStatus] = []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(roots))
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
                projects.extend(future.result(timeout=0))
            except concurrent.futures.TimeoutError:
                _push_error(f"scan of {root} exceeded {PER_ROOT_TIMEOUT_SECONDS}s, skipped")
            except OSError as e:
                _push_error(f"scan of {root} failed: {e}")
    except concurrent.futures.TimeoutError:
        _push_error("overall scan timeout reached, some roots skipped")
    _set_scan_progress(
        pct=100, root="", roots_done=_scan_progress.get("roots_total", 0)
    )
    pool.shutdown(wait=False)
    seen = set()
    deduped = []
    for p in projects:
        if _is_garbage_root(p.root):
            continue
        k = str(p.root).lower()
        if k not in seen:
            seen.add(k)
            deduped.append(p)
    return deduped


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
    """Runs `scan()` on a timer, delivering results to `on_result` off the main thread."""

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

    def _loop(self) -> None:
        my_gen = self._gen
        while not self._stop_event.is_set():
            try:
                if not _is_gen_current(my_gen):
                    break
                if self._on_scan_start:
                    self._on_scan_start()
                self._on_result(
                    scan(
                        self._scan_roots,
                        max_depth=self._max_depth,
                        delay=self._delay,
                        extra_excludes=self._extra_excludes,
                    )
                )
            except Exception as e:
                # An uncaught exception in scan() (e.g. all roots timeout
                # and as_completed raises) would kill the daemon thread
                # silently under pythonw.exe (no console). Log, push an
                # error, and let the loop sleep normally before retrying.
                _push_error(f"background scan failed: {e}")
                print(
                    f"SAIPENVIEW: BackgroundScanner._loop error: {e}", file=sys.stderr
                )
            self._stop_event.wait(self._interval)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def rescan_now(self) -> None:
        if not _is_gen_current(self._gen):
            return
        if self._on_scan_start:
            self._on_scan_start()
        self._on_result(
            scan(
                self._scan_roots,
                max_depth=self._max_depth,
                delay=self._delay,
                extra_excludes=self._extra_excludes,
            )
        )

    def stop(self) -> None:
        _next_gen()
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
