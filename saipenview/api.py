"""JS-facing API exposed to the pywebview window as `pywebview.api`."""

# Agent engine layer (Wave 1)

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from saipenview import themes
from saipenview.config import config_path, load_config, save_config
from saipenview.conformance import check_project
from saipenview.engines import get_engine, list_engines
from saipenview.events import event_bus
from saipenview.git_diff import (
    commit_agent_work,
    delete_untracked_files,
    get_working_diff,
    revert_agent_work,
)
from saipenview.parser import (
    OutboxEntry,
    ProjectStatus,
    SubStatus,
    load_log_tail,
    load_project,
    parse_board,
    parse_frontmatter,
    update_state,
)
from saipenview.paths import canonical, dedupe, validate_file_path
from saipenview.runtime import ProcessManager
from saipenview.scanner import (
    BackgroundScanner,
    _auto_roots,
    _is_garbage_root,
    find_linked_worktrees,
    get_scan_error_log,
    get_scan_errors,
    get_scan_progress,
    scan,
)
from saipenview.textio import read_doc, read_doc_meta, write_doc
from saipenview.watcher import SaipenWatcher


def _canonical_or(root_str: str) -> str:
    """Canonical path for membership checks; preserve raw value on failure."""
    try:
        return canonical(root_str)
    except (OSError, ValueError):
        return root_str

_OUTBOX_STATUS_ORDER = {"ready": 0, "blocked": 1, "draft": 2, "stale": 3, "reviewed": 4}


def _outbox_entry_to_dict(e: OutboxEntry) -> dict:
    return {
        "id": e.entry_id,
        "title": e.title,
        "status": e.status,
        "summary": e.summary,
        "critical": e.critical,
        "severity": e.severity,
    }


class _EngineWithOverrides:
    """Wrap an engine so build_command honours `engine_overrides` (T-168).

    The override surface is deliberately small and validated: `path`
    replaces the executable, `extra_args` is appended to the argv, `env`
    merges into default_env. Anything else is rejected before a launch."""

    def __init__(self, engine, path, extra_args, env):
        self._engine = engine
        self._path = path
        self._extra = extra_args
        self._env = env

    @property
    def name(self) -> str:
        return self._engine.name

    @property
    def display_name(self) -> str:
        return self._engine.display_name

    def detect(self) -> bool:
        return self._engine.detect()

    def build_command(self, project_root, instruction, *, extra_args=None):
        merged = list(extra_args or []) + list(self._extra)
        cmd = self._engine.build_command(
            project_root, instruction, extra_args=merged or None
        )
        if isinstance(cmd, str):
            # A command-line string (GenericCLI shell contract, T-168):
            # replace the leading executable token only.
            if self._path:
                head, _, tail = cmd.partition(" ")
                cmd = self._path + (" " + tail if tail else "")
            return cmd
        cmd = list(cmd)
        if self._path:
            cmd[0] = self._path
        return cmd

    @property
    def supports_stdin(self) -> bool:
        return self._engine.supports_stdin

    @property
    def default_env(self) -> dict | None:
        env = dict(self._engine.default_env or {})
        env.update(self._env)
        return env or None

    def parse_event(self, line):
        return self._engine.parse_event(line)

    def to_dict(self) -> dict:
        return self._engine.to_dict()


def _apply_engine_overrides(engine, overrides) -> tuple:
    """Return (wrapped_engine, None) or (None, error) on invalid overrides."""
    ok, err = validate_engine_overrides(overrides)
    if not ok:
        return None, err
    path = overrides.get("path")
    extra = overrides.get("extra_args") or []
    env = overrides.get("env") or {}
    return _EngineWithOverrides(engine, path, extra, env), None


def validate_engine_overrides(overrides) -> tuple[bool, str]:
    """Shape-check one engine's override dict (T-178). The settings UI and the
    launch path share this so an invalid override is rejected the same way
    wherever it is typed."""
    if not isinstance(overrides, dict):
        return False, "engine_overrides entry must be an object"
    path = overrides.get("path")
    extra = overrides.get("extra_args") or []
    env = overrides.get("env") or {}
    if path is not None and not isinstance(path, str):
        return False, "engine override 'path' must be a string"
    if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
        return False, "engine override 'extra_args' must be a list of strings"
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        return False, "engine override 'env' must be a dict of str -> str"
    return True, ""


def _sub_to_dict(sub: SubStatus) -> dict:
    outbox_sorted = sorted(
        sub.outbox,
        key=lambda e: (_OUTBOX_STATUS_ORDER.get(e.status, 5), not e.critical),
    )
    return {
        "name": sub.name,
        "phase": sub.phase,
        "task": sub.task,
        "blocker": sub.blocker,
        "updated": sub.updated,
        "updated_kind": sub.updated_kind,
        "path": str(sub.path),
        "outbox": [_outbox_entry_to_dict(e) for e in outbox_sorted],
        "outbox_counts": sub.outbox_counts,
        "outbox_critical_ready": sub.outbox_critical_ready,
        "outbox_path": str(sub.path / "kitchen" / "OUTBOX.md"),
        "next_action": sub.next_action,
        "board_counts": dict(sub.board_counts),
        "log_tail": list(sub.log_tail),
    }


def _phase_rank(phase: str) -> int:
    return {
        "ACTIVE": 0,
        "BLOCKED": 1,
        "INIT": 2,
        "HUNT": 2,
        "BUILD": 2,
        "REVIEW": 2,
        "PLAN": 2,
        "SCOUT": 2,
        "ADD": 2,
        "CLEAN": 2,
        "TRANSLATE": 2,
        "VALIDATE": 2,
        "VERIFY": 3,
        "SHIP": 3,
        "DONE": 4,
    }.get(phase, 5)


class _Reversed:
    """Wraps a value so it sorts descending inside an otherwise-ascending
    tuple key -- list.sort() takes one direction per call, this is the
    standard way to mix directions per tuple field without a second pass."""

    __slots__ = ("obj",)

    def __init__(self, obj):
        self.obj = obj

    def __lt__(self, other):
        return other.obj < self.obj


def _project_sort_key(x: dict, order: str = "smart") -> tuple:
    if order == "name_asc":
        return (not x["is_pinned"], x["name"].lower())
    if order == "name_desc":
        return (not x["is_pinned"], _Reversed(x["name"].lower()))
    if order == "recent":
        return (not x["is_pinned"], -x.get("mtime", 0))
    if order == "oldest":
        return (not x["is_pinned"], x.get("mtime", 0))
    return (
        not x["is_pinned"],
        # A project the protocol rejects outranks phase: it is the one thing
        # here that no amount of waiting fixes by itself.
        (x.get("conformance") or {}).get("verdict") != "fail",
        _phase_rank(x["phase"]),
        not x.get("git_dirty", False),
        -x.get("mtime", 0),
        x["name"].lower(),
    )


def _is_top_level_log_change(fname: str) -> bool:
    """True only for the exact top-level ``.saipen/LOG.md`` change.

    Watcher keys are full ``.saipen``-relative posix paths. A nested
    SubSaipen/saitranslate LOG arrives as e.g. ``extensions/subs/<id>/LOG.md``
    or ``saitranslate/LOG.md`` and must NOT take the parent project's
    top-level LOG fast path -- it affects only the owning component and must
    fall through to a full project reload (CORE-002).
    """
    if not isinstance(fname, str) or not fname:
        return False
    norm = fname.replace("\\", "/")
    return norm.lower() == "log.md"


# CORE-004: one canonical cache-row validator for BOTH the legacy cache.json
# rows and the per-root sidecar records. A row that cannot satisfy the sort/
# render consumers must be quarantined as cache corruption, never enter
# ``_projects`` (where ``_project_sort_key`` would crash on its missing
# fields and turn disposable cache state into an application-startup failure).
_CACHE_REQUIRED_FIELDS: tuple[str, ...] = (
    "root", "name", "phase", "is_pinned", "task",
    "next_action", "blocker", "mtime", "updated",
    "updated_kind",
)


def _valid_cache_row(row: object) -> bool:
    """True when *row* can safely feed ``_project_sort_key`` and the UI.

    Matches the structural contract the legacy loader enforces: every
    required field present, ``root`` a non-empty string, ``is_pinned`` a
    bool. A row missing any field is quarantined by the caller, never loaded.
    """
    if not isinstance(row, dict):
        return False
    if not all(k in row for k in _CACHE_REQUIRED_FIELDS):
        return False
    if not isinstance(row.get("root"), str) or not row["root"]:
        return False
    if not isinstance(row.get("is_pinned"), bool):
        return False
    if not isinstance(row.get("name"), str) or not isinstance(row.get("phase"), str):
        return False
    return True


def _read_state_for_log_check(root: Path) -> dict[str, str] | None:
    """Parse the project's STATE frontmatter for the STATE-aware LOG checks.

    ``check_log(root, c, state)`` enforces the ``state.last_event.*``
    invariants only when ``state`` is supplied; a missing or unreadable
    STATE invalidates those cross-checks, so this returns None and the caller
    falls through to a full reload rather than silently downgrading (CORE-001).
    """
    try:
        state_path = Path(root) / ".saipen" / "STATE.md"
        if not state_path.is_file():
            return None
        from saipenview.textio import read_doc

        return parse_frontmatter(read_doc(state_path))
    except (OSError, ValueError):
        return None


def _project_to_dict(
    project: ProjectStatus, pinned_roots: set[str] | None = None
) -> dict:
    root_str = str(project.root)
    # CORE-003: pinned_roots are stored in canonical form (lowercase, resolved);
    # rows still carry the path as discovered. Membership uses canonical keys
    # so `V:\proj` and `v:\proj` agree on the pin state. canonical() resolves
    # once per row; callers should already pass a canonical `pinned_roots` set.
    is_pinned = bool(
        pinned_roots
        and _canonical_or(root_str) in pinned_roots
    )
    # Graded on every row, not only on the detail pane. A project that is
    # illegal is illegal from the list -- if the verdict only appeared once you
    # clicked in, the one project you never click is the one that stays broken.
    try:
        report = check_project(project.root, project.state, project.subs).to_dict()
    except Exception as e:  # noqa: BLE001 - a grader must never break the row
        print(f"SAIPENVIEW: conformance({root_str}) failed: {e}", file=sys.stderr)
        report = {
            "verdict": "unknown",
            "fails": 0,
            "warns": 0,
            "baseline": "",
            "findings": [],
        }
    return {
        "conformance": report,
        "name": project.name,
        "root": root_str,
        "phase": project.phase,
        "task": project.task,
        "next_action": project.next_action,
        "blocker": project.blocker,
        "updated": project.updated,
        "updated_kind": project.updated_kind,
        "mtime": project.mtime,
        "board": project.board.counts(),
        "subs": [_sub_to_dict(s) for s in project.subs],
        "translate": _sub_to_dict(project.translate) if project.translate else None,
        "is_pinned": is_pinned,
        "quick_actions": project.quick_actions,
        "subs_stale": project.subs_stale,
        "subs_stale_details": project.subs_stale_details,
        "git_branch": project.git_branch,
        "git_dirty": project.git_dirty,
    }


_cache_lock = threading.Lock()


@contextlib.contextmanager
def _cache_file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name("." + path.name + ".lock")
    with open(lock_path, "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Api:
    """Owns the cached scan result + user config; BackgroundScanner refreshes off-thread."""

    def __init__(
        self, on_hotkeys_changed=None, window=None, debounce_delay: float = 0.1
    ):
        self._window = window
        self._lock = threading.Lock()
        # W2-028: module-level cache lock shared across all Api instances.
        # Prevents two concurrent writers from overwriting each other's
        # snapshot when they share the same _data/cache.json path.
        self._projects: list[dict] = []
        self._has_scanned = False
        self._scanning = False
        self._config = load_config()
        self._auto_scan = self._config.get("auto_scan", True)
        self._on_hotkeys_changed = on_hotkeys_changed
        self._on_snap_hotkey_changed = None
        self._on_quit = None
        self._cache_file = config_path().parent / "cache.json"
        # PERF-004: per-root durable records overlay legacy monolithic
        # cache.json. The legacy file remains readable for migration and
        # compatibility; changed roots are written to a sibling sidecar
        # directory derived from current _cache_file.
        if self._cache_file.exists():
            try:
                with open(self._cache_file, encoding="utf-8") as f:
                    candidate = json.load(f)
                # Structural validation (CORE-013): require a list of dicts
                # each carrying a string "root" key. Anything else is
                # poisoned -- the comprehension below would crash on a
                # non-list, a non-dict row, or a missing/non-string root.
                if not isinstance(candidate, list):
                    raise ValueError("cache is not a list")
                # W2-005: cache-row validation requires the full minimum
                # project shape needed by _project_sort_key and UI
                # consumers — not just a string "root". A row missing
                # is_pinned, name, or phase would crash later in
                # sorting/rendering before a fresh scan repairs it.
                # CORE-004: identical validation for legacy rows and sidecar
                # records; centralize in _valid_cache_row so a malformed row
                # can never escape the legacy path, the sidecar path, or any
                # future cache input.
                valid_rows = []
                for p in candidate:
                    if _valid_cache_row(p):
                        valid_rows.append(p)
                    else:
                        raise ValueError("cache contains an invalid project entry")
                self._projects = valid_rows
                self._has_scanned = True
            except Exception as e:
                print(
                    f"SAIPENVIEW: cache at {self._cache_file} unreadable ({e}), starting fresh",
                    file=sys.stderr,
                )
                self._projects = []
                self._has_scanned = False

        self._linked_worktrees: list[dict] = []
        self._refresh_changed_roots: list[str] = []  # PERF-002
        self._load_cache_records()
        self._last_cache_snapshot = {p["root"]: p for p in self._projects}
        # PERF-008: in-memory ticket search index, keyed by root.
        self._ticket_index: dict[str, list[dict]] = {}
        self._verified_roots_cache: dict = {"key": None, "list": [], "set": set()}
        # PERF-005: per-root JSON serialization cache. Only changed roots
        # are re-serialized on _write_cache; unchanged rows are copied from
        # the previous serialization, cutting I/O from O(N) to O(dirty).
        self._row_json_cache: dict[str, str] = {}
        self._dirty_roots: set[str] = set()
        self._cache_deleted_roots: set[str] = set()
        # PERF-002: when True, refresh_known() must do a full re-parse (startup,
        # or just after a scan replaced the cache). Between scans the watcher
        # already keeps _projects current, so an idle poll may short-circuit
        # and skip the re-parse entirely.
        self._full_refresh_pending = True
        # W2-001: monotonic scan epoch. Every scan request, regardless of
        # origin (manual rescan / set_scan_roots / browse_folder / periodic
        # BackgroundScanner), captures the current epoch at request start
        # and only commits via _set_cache if its captured epoch still
        # matches. A newer request bumps the epoch, so any older in-flight
        # publication is rejected before mutating the registry.
        self._scan_epoch = 0
        # W2-007: registry revision. Bumped on every _projects mutation so a
        # refresh_known that reparsed outside the lock can detect a concurrent
        # _set_cache / file-event change and merge instead of clobbering.
        self._registry_rev = 0
        from saipenview.protocol_write import get_coordinator

        self._process_manager = ProcessManager(
            buffer_size=self._config.get("agent_output_buffer_size", 5000),
            ownership=get_coordinator().ownership,
        )
        self.background_scanner = BackgroundScanner(
            on_result=self._set_cache,
            scan_roots=self._config["scan_roots"],
            interval_seconds=self._config["rescan_interval"],
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
            on_scan_start=lambda: self._set_scanning(True),
            epoch_source=lambda: self._scan_epoch,
        )

        # The watcher belongs to the Api/project registry, not the
        # ProcessManager (T-124): every known project is watched, agent
        # launch/finish has nothing to do with it.
        self._watcher = SaipenWatcher()

        # CORE-022 / T-32: subscribe to EventBus AFTER all construction is
        # complete. If any post-subscription step failed, the constructor
        # would leave a dangling callback on the global EventBus pointing
        # at a half-initialized Api. By moving subscribe to start(), the
        # callback only lives once the object is fully constructed and
        # ready to handle events safely.
        self._event_subscribed = False

        # CORE-004 / T-542: debounce state must be INSTANCE-owned.
        self._debounce_delay = debounce_delay
        self._root_refresh_timers: dict[str, threading.Timer] = {}
        self._root_refresh_lock = threading.RLock()
        # Exact files observed to change per root with immediate origin attribution:
        # root -> {fname: origin}
        self._root_refresh_files: dict[str, dict[str, str]] = {}
        # W2-011: lifecycle generation. Incremented in stop() BEFORE unsubscribe
        # and timer cancellation so any callback already captured by EventBus
        # publish's snapshot sees a stale generation and aborts before scheduling
        # new refresh work or touching the window.
        self._stop_gen = 0

    def _on_file_changed(self, data: dict, _gen: int = None) -> None:
        # W2-011: generation is bound at subscription time (via the wrapper
        # in start()), not re-read at entry. A callback already captured in
        # EventBus's pre-stop snapshot but delayed until after stop sees the
        # old generation and aborts.
        if _gen is not None and self._stop_gen != _gen:
            return
        gen = self._stop_gen
        root = data["root"]
        changed_file = data.get("file")
        origin = "external"
        if changed_file:
            from saipenview.external_changes import get_registry
            from saipenview.protocol_write import get_coordinator

            coord = get_coordinator()
            changed_path = Path(root) / ".saipen" / changed_file
            try:
                # W2-002: the watcher counts raw events per file in the
                # debounce window. Compare that against the number of armed
                # self-write registrations: more raw events than self
                # generations means an external write landed between app
                # writes (self A -> external B -> self C), which the final
                # fingerprint check alone cannot see.
                event_count = int(data.get("event_count") or 0)
                try:
                    armed = int(coord.self_writes.count(root, changed_file) or 0)
                except (TypeError, ValueError):
                    armed = 0
                if coord.self_writes.has_live(root, changed_file):
                    fp = coord.fingerprint(changed_path)
                    matched = coord.self_writes.consume(root, changed_file, fp)
                    origin = "self" if matched else "external"
                else:
                    fp = coord.fingerprint(changed_path)
                    origin = "external"
                if origin == "self" and event_count > armed:
                    # External write landed inside the debounce window even
                    # though the final bytes match our own registration.
                    origin = "external"
                if origin == "external":
                    get_registry().record(root, changed_file, fp)
            except OSError:
                pass
            event_bus.publish(
                "saipen.file_changed",
                {"root": root, "file": changed_file, "origin": origin},
            )

        should_run_now = False
        with self._root_refresh_lock:
            if changed_file:
                self._root_refresh_files.setdefault(root, {})[changed_file] = origin
            existing = self._root_refresh_timers.get(root)
            if existing:
                existing.cancel()
            if self._debounce_delay <= 0:
                should_run_now = True
            else:
                timer = threading.Timer(
                    self._debounce_delay, self._do_root_refresh, args=(root, gen)
                )
                timer.daemon = True
                self._root_refresh_timers[root] = timer
                timer.start()

        if should_run_now:
            self._do_root_refresh(root, gen)

    def _do_root_refresh(self, root: str, gen: int) -> None:
        # W2-011: generation gate. If stop() incremented _stop_gen after this
        # timer was scheduled, abort immediately — no cache mutation, no JS push.
        if self._stop_gen != gen:
            return
        """T-542: single coalesced refresh per root from debounced timer.

        Re-parses the project once, updates cache once, then pushes JS notifications
        for all accumulated files in deterministic sorted order.
        """
        with self._root_refresh_lock:
            self._root_refresh_timers.pop(root, None)
            changed_dict = self._root_refresh_files.pop(root, {})
        # PERF-004: tell the targeted refresh WHICH artifacts moved so it can
        # skip the ticket-index rebuild / cache pickle when only LOG or
        # transcript lines changed. A directory-level event with no specific
        # file leaves changed_dict empty -> full refresh (None) for safety.
        if changed_dict:
            self._refresh_one_project(root, set(changed_dict.keys()))
        else:
            self._refresh_one_project(root)
        if not changed_dict or not self._window:
            return
        for fname in sorted(changed_dict.keys()):
            origin = changed_dict[fname]
            try:
                self._window.evaluate_js(
                    "if (window.onSaipenFileChanged) window.onSaipenFileChanged("
                    + json.dumps(root)
                    + ", "
                    + json.dumps(fname)
                    + ", "
                    + json.dumps(origin)
                    + ")"
                )
            except Exception as e:  # noqa: BLE001
                print(f"SAIPENVIEW: js push failed: {e}", file=sys.stderr)

    @staticmethod
    def _file_affects_index(fname: str) -> bool:
        """A change to this .saipen artifact moves the ticket index.

        CORE-002: nested SubSaipen/saitranslate protocol files arrive as full
        ``.saipen``-relative posix paths (``extensions/subs/<id>/BOARD.md``,
        ``extensions/subs/<id>/LOG.md``, ``saitranslate/LOG.md``). They are
        parsed inputs (``load_project`` reads sub boards/log tails), so a
        change to any tracked basename anywhere in the tree affects the row.
        """
        low = fname.replace("\\", "/").lower()
        base = low.rsplit("/", 1)[-1]
        return base in (
            "state.md",
            "board.md",
            "log.md",
            "outbox.md",
            "manifest.md",
            "ticket.md",
        )

    @staticmethod
    def _file_affects_cache(fname: str) -> bool:
        """A change to this .saipen artifact moves a persisted cache row."""
        return Api._file_affects_index(fname)

    def _refresh_one_project(
        self, root: str, changed_files: set[str] | None = None
    ) -> None:
        """Re-parse one project and update only its cache row.

        CORE-011: when load_project returns None (project vanished --
        STATE.md deleted), the row is removed from the cache.

        CORE-012: the vanished-project branch must NOT call _write_cache() or
        _sync_watcher() while holding self._lock -- both re-acquire that same
        non-reentrant lock and would self-deadlock the Api thread, freezing all
        later project/cache/watcher operations.

        PERF-004: when *changed_files* is known, only the heavy, recursive work
        that the changed artifact actually affects is redone. A pure LOG /
        transcript / agent-output change does not alter any cache row nor the
        ticket index, so both the index rebuild and the cache pickle+disk write
        are skipped -- no full re-parse of the ticket tree on every log line.
        """
        # CORE-001 / CORE-002: when every changed file is the exact top-level
        # ``LOG.md``, regrading this one project coherently is enough. Nested
        # LOG files (``extensions/subs/<id>/LOG.md``, ``saitranslate/LOG.md``)
        # do NOT match ``_is_top_level_log_change`` and therefore fall through
        # to the full reload below -- a nested event must rebuild the
        # affected SubSaipen/translate log_tail, not the parent LOG.
        log_only_fast_path = bool(
            changed_files
            and all(_is_top_level_log_change(name) for name in changed_files)
        )
        if log_only_fast_path:
            # CORE-001: a coherent regrade requires current STATE for the
            # ``state.last_event.*`` invariants and current SubSaipen/translation
            # for ``check_subs``. A missing/unreadable STATE invalidates the
            # STATE-aware contract; fall through to the full reload rather than
            # silently downgrading.
            log_state = _read_state_for_log_check(Path(root))
            if log_state is None:
                log_only_fast_path = False

        pinned_set = set(self._config.get("pinned_roots") or [])
        try:
            proj = load_project(Path(root), with_git=False)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"SAIPENVIEW: targeted refresh({root}) failed: {e}", file=sys.stderr)
            return

        # CORE-001: a top-level LOG-only change is regraded coherently here,
        # not by splicing the previous transport JSON. `check_project` runs
        # the same STATE-aware contract (check_state, check_board, check_cross,
        # check_log with current STATE, check_subs) as a cold grade, so
        # verdict, exact fail/warn counts, retained findings, `findings_total`
        # and `findings_truncated` are derived together from current bytes.
        # The row's non-LOG fields are untouched; the LOG change cannot alter
        # them. Nested LOG paths never reach here (log_only_fast_path is
        # False for them), so nested component state is always rebuilt by the
        # full reload below (CORE-002).
        if log_only_fast_path:
            if proj is None:
                pass
            else:
                try:
                    report = check_project(proj.root, proj.state, proj.subs).to_dict()
                except Exception as e:  # noqa: BLE001 - a grader must never break the refresh
                    print(
                        f"SAIPENVIEW: targeted LOG refresh({root}) failed: {e}",
                        file=sys.stderr,
                    )
                    return
                with self._lock:
                    current = next(
                        (p for p in self._projects if p["root"] == root), None
                    )
                    if current is None:
                        return
                    replacement = dict(current)
                    replacement["conformance"] = report
                    replacement_list = [
                        replacement if p["root"] == root else p
                        for p in self._projects
                    ]
                    replacement_list.sort(
                        key=lambda x: _project_sort_key(x, self._sort_order())
                    )
                    self._replace_projects_locked(replacement_list)
                return

        # Phase 1: decide + mutate in-memory state under the lock.
        vanished = False
        with self._lock:
            prev = next((p for p in self._projects if p["root"] == root), None)
            if prev is None:
                return
            if proj is None:
                # CORE-011/012: project vanished -- drop its row + index under
                # the lock, but defer cache/watcher writes until after release.
                self._replace_projects_locked(
                    [p for p in self._projects if p["root"] != root]
                )
                self._ticket_index.pop(root, None)
                vanished = True
            else:
                row = _project_to_dict(proj, pinned_set)
                row["git_branch"] = prev.get("git_branch", "")
                row["git_dirty"] = prev.get("git_dirty", False)
                replacement = list(self._projects)
                for i, p in enumerate(replacement):
                    if p["root"] == root:
                        replacement[i] = row
                        break
                replacement.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
                self._replace_projects_locked(replacement)

        # Phase 2: heavy/recursive work OUTSIDE the lock.
        if vanished:
            self._write_cache()
            self._sync_watcher()
            return
        # PERF-004: decide whether the durable artifacts actually moved.
        if changed_files is None:
            affects_index = affects_cache = True
        else:
            affects_index = any(self._file_affects_index(f) for f in changed_files)
            affects_cache = any(self._file_affects_cache(f) for f in changed_files)
            if not affects_cache:
                return
        if affects_index:
            # PERF-003: rebuild the ticket index for this root from the
            # already-parsed Board, skipping BOARD file I/O.
            pre_built = self._tickets_from_board(proj.board) if proj else None
            self._build_ticket_index(root, pre_built=pre_built)
        if affects_cache:
            self._write_cache()

    def _sync_watcher(self) -> None:
        """Reconcile the watcher's watch set with the known projects (T-124)."""
        with self._lock:
            roots = [p["root"] for p in self._projects]
            scan_roots = list(self._config.get("scan_roots") or [])
        # PERF-001: schedule by scan root (O(K) watchdog emitters) when scan
        # roots are configured; fallback to per-project topology otherwise.
        self._watcher.sync(roots, scan_roots)

    def _set_scanning(self, val: bool) -> None:
        with self._lock:
            self._scanning = val

    # W2-008: centralized scanner configuration helpers. Every root/depth/
    # delay/exclude reconfiguration uses the same effective options.

    def _scan_kwargs(self) -> dict:
        """Effective scan kwargs from current config."""
        return {
            "scan_roots": self._config["scan_roots"],
            "max_depth": self._config.get("scan_depth", 6),
            "delay": self._config.get("scan_delay_ms", 10) / 1000.0,
            "extra_excludes": set(self._config.get("exclude_dirs", [])),
        }

    def _replace_background_scanner(self) -> None:
        """Stop old scanner, create a new one with current config.

        Starts the replacement only if auto_scan is enabled. Preserves
        the intentional immediate-rescan behavior of root/exclude changes.
        """
        self.background_scanner.stop()
        self.background_scanner = BackgroundScanner(
            on_result=self._set_cache,
            **self._scan_kwargs(),
            interval_seconds=self._config["rescan_interval"],
            on_scan_start=lambda: self._set_scanning(True),
            epoch_source=lambda: self._scan_epoch,
        )
        if self._auto_scan:
            self.background_scanner.start()

    def _sort_order(self) -> str:
        return self._config.get("sort_order", "smart")

    def _mark_registry_mutation_locked(self, roots=()) -> None:
        roots = tuple(roots)
        self._registry_rev += 1
        self._dirty_roots.update(roots)
        self._verified_roots_cache = {"key": None, "list": [], "set": set()}
        for root in roots:
            if root not in self._refresh_changed_roots:
                self._refresh_changed_roots.append(root)

    def _replace_projects_locked(
        self, projects: list[dict], replace_all: bool = False
    ) -> bool:
        if projects == self._projects:
            return False
        old_by_root = {p["root"]: p for p in self._projects}
        new_by_root = {p["root"]: p for p in projects}
        changed_roots = {
            root
            for root in old_by_root.keys() | new_by_root.keys()
            if old_by_root.get(root) != new_by_root.get(root)
        }
        self._projects = projects
        self._cache_deleted_roots.update(set(old_by_root) - set(new_by_root))
        self._mark_registry_mutation_locked(changed_roots)
        return True

    def _set_cache(
        self,
        projects,
        force: bool = False,
        complete: bool = True,
        worktrees=None,
        completed_roots=None,
        unresolved_roots=None,
        epoch: int | None = None,
    ) -> None:
        """Update the project cache from a scan result.

        CORE-011: accepts either a ScanOutcome or a plain list of
        ProjectStatus. A complete empty result replaces the cache; an
        incomplete/failed result preserves existing rows beneath unresolved
        scan roots while replacing rows beneath completed ones (CORE-001).
        PERF-001/PERF-003: prefers worktrees passed through from the scan
        (ScanOutcome or the ``worktrees`` kwarg) so the linked-worktree walk
        is never done twice.

        W2-001: *epoch* is the scan-request epoch captured at request start.
        Only the newest still-authoritative request may publish; an older
        in-flight scan that finished after a newer manual rescan carries a
        stale epoch and is rejected here before any registry mutation.
        """
        # W2-001: reject a publication from a superseded scan request BEFORE
        # touching the registry. Authority is assigned at request start, so a
        # slower older scan can never roll back a newer manual result.
        if epoch is not None and epoch != self._scan_epoch:
            return
        from saipenview.scanner import ScanOutcome

        completed_roots = []
        unresolved_roots = []
        if isinstance(projects, ScanOutcome):
            complete = projects.complete
            project_list = projects.projects
            worktrees = projects.worktrees
            completed_roots = getattr(projects, "completed_roots", []) or []
            unresolved_roots = getattr(projects, "unresolved_roots", []) or []
        else:
            project_list = projects
            completed_roots = completed_roots or []
            unresolved_roots = unresolved_roots or []
        pinned_set = set(self._config.get("pinned_roots") or [])
        # CORE-006: keep EVERY verified known project in the internal registry
        # regardless of visibility. Hidden roots are filtered only at the
        # presentation boundary (get_projects), never deleted here, so hiding
        # can no longer erase a project from the registry/watcher.
        items = [
            _project_to_dict(p, pinned_set)
            for p in project_list
            if not _is_garbage_root(p.root)
        ]
        items.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
        # PERF-006: capture the pre-replacement root set so removed roots'
        # BOARD/LOG/staleness caches can be evicted after an authoritative
        # replace.
        _pre_replace = [p["root"] for p in self._projects]
        with self._lock:
            if not complete and self._has_scanned and self._projects:
                # CORE-001: scoped per-root merge when root provenance is
                # available. Preserve existing rows beneath unresolved roots
                # while replacing/removing rows beneath completed ones.
                if completed_roots or unresolved_roots:
                    effective_roots = [canonical(r) for r in (completed_roots + unresolved_roots)]
                    unresolved_set = set(canonical(r) for r in unresolved_roots)

                    def _belongs(proot: str, scan_root: str) -> bool:
                        try:
                            pp = Path(proot)
                        except (OSError, ValueError):
                            return False
                        return pp.is_relative_to(Path(scan_root)) or pp == Path(scan_root)

                    preserved = []
                    for row in self._projects:
                        spec = None
                        for sr in effective_roots:
                            if _belongs(row["root"], sr):
                                if spec is None or len(Path(sr).parts) > len(Path(spec).parts):
                                    spec = sr
                        if spec is None or canonical(spec) in unresolved_set:
                            preserved.append(row)
                    merged = {p["root"]: p for p in preserved}
                    for it in items:
                        merged[it["root"]] = it
                    merged_items = sorted(merged.values(), key=lambda x: _project_sort_key(x, self._sort_order()))
                    self._replace_projects_locked(merged_items)
                    self._has_scanned = True
                    self._scanning = False
                else:
                    # No root provenance available — preserve everything (old
                    # incomplete-result safety).
                    self._scanning = False
                    return
            elif (
                not force
                and not project_list
                and complete
                and self._has_scanned
                and self._projects
            ):
                # Complete scan returned zero projects: all previous ones vanished.
                # Fall through to set empty.
                self._replace_projects_locked(items)
                self._has_scanned = True
                self._scanning = False
            else:
                self._replace_projects_locked(items)
                self._has_scanned = True
                self._scanning = False
        # PERF-003: if the scan already collected worktrees, use them directly.
        # Fall back to a standalone walk only for non-scan callers.
        if worktrees is not None:
            with self._lock:
                if complete or not (completed_roots or unresolved_roots):
                    self._linked_worktrees = list(worktrees)
                else:
                    effective_roots = [canonical(r) for r in completed_roots + unresolved_roots]
                    unresolved_set = {canonical(r) for r in unresolved_roots}

                    def _worktree_root_scope(item):
                        return canonical(item.get("root", "")) if isinstance(item, dict) else ""

                    def _in_scope(item, scan_root):
                        item_root = _worktree_root_scope(item)
                        try:
                            return Path(item_root).is_relative_to(Path(scan_root)) or item_root == scan_root
                        except (OSError, ValueError):
                            return False

                    preserved = []
                    for item in self._linked_worktrees:
                        matches = [r for r in effective_roots if _in_scope(item, r)]
                        if not matches or canonical(max(matches, key=lambda r: len(Path(r).parts))) in unresolved_set:
                            preserved.append(item)
                    merged = {_worktree_root_scope(item): item for item in preserved}
                    merged.update({_worktree_root_scope(item): item for item in worktrees})
                    self._linked_worktrees = list(merged.values())
        else:
            self._scan_linked_worktrees()
        # Atomic write (temp + replace) via the shared helper -- a crash mid
        # plain write left truncated JSON that __init__'s json.load choked on.
        self._write_cache()
        # PERF-003: rebuild ticket index for all current roots.  When the
        # scan provided full ProjectStatus objects, extract indexes from the
        # already-parsed Board data instead of re-reading BOARD files.
        pre_built_indexes: dict[str, list[dict]] = {}
        if project_list:
            for p in project_list:
                root_key = str(p.root)
                pre_built_indexes[root_key] = self._tickets_from_board(p.board)
        with self._lock:
            roots = [p["root"] for p in self._projects]
        for r in roots:
            self._build_ticket_index(r, pre_built=pre_built_indexes.get(r))
        # PERF-006: a project removed authoritatively must not leave its
        # BOARD/LOG/staleness cache resident. Compute removed roots from the
        # old registry (captured before the replacement above) against the new.
        try:
            from saipenview.conformance import evict_project_caches
        except ImportError:
            evict_project_caches = None
        if evict_project_caches is not None:
            with self._lock:
                old_roots = set(_pre_replace)
                new_roots = {p["root"] for p in self._projects}
            removed = sorted(old_roots - new_roots)
            if removed:
                evict_project_caches(removed)
        # Watch exactly what we know about (T-124).
        self._sync_watcher()
        # PERF-003: ScanOutcome rows were parsed by scanner._scan_one_root
        # and their ticket indexes were built above. They are authoritative
        # for this publication; forcing refresh_known() to reparse every row
        # would duplicate the scan work. Keep the pending flag only for
        # constructor startup, where rows came from durable cache rather than
        # a fresh scan.
        with self._lock:
            self._full_refresh_pending = False

    def get_projects(self) -> list[dict]:
        hidden_set = set(self._config.get("hidden_roots") or [])
        with self._lock:
            # CORE-003: hidden_roots are canonical; rows carry raw paths.
            return [p for p in self._projects if _canonical_or(p["root"]) not in hidden_set]

    def refresh_known(self, known_revision: int | None = None) -> list[dict] | dict:
        """Re-read the .saipen/ files of roots we ALREADY know about.

        PERF-002: tracks which roots actually changed so the frontend can
        skip sidebar rebuild and detail reload when nothing changed.

        PERF-002 (idle polling): between scans the watcher already keeps
        ``_projects`` current on every file event (it calls ``_refresh_one_project``
        directly, and the JS side re-renders from the pushed projects, not from
        this poll). So an idle poll -- no scan running and no pending full
        refresh -- must NOT re-parse the whole tree; it returns the cached rows
        with an empty changed set. Only a scan result or startup forces the
        one reconciliation parse.
        """
        # W2-007: a refresh reparses outside the lock; a concurrent _set_cache
        # (scan discovery/removal) or file-event refresh may mutate the registry
        # in the meantime. Retry up to a few times so each attempt re-reads the
        # now-current set; if it still can't commit cleanly, trust the live
        # registry rather than clobbering it (never resurrect a removed root,
        # never drop a discovered one).
        # PERF-002: snapshot the pending flag under the lock so a concurrent
        # _set_cache that flips it does not race with the idle-skip decision.
        with self._lock:
            full_refresh_was_pending = self._full_refresh_pending
            self._full_refresh_pending = False
            prev_by_root = {p["root"]: p for p in self._projects}
            rev0 = self._registry_rev
        # W2-005: when the caller supplied a stale known_revision, do one
        # full reconciliation so the response carries everything needed to
        # advance to the current revision. The idle short-circuit below only
        # fires when the caller has no revision to compare (None) and no
        # scan/startup is pending.
        if (
            not full_refresh_was_pending
            and not self._scanning
            and known_revision is not None
            and known_revision == self._registry_rev
        ):
            with self._lock:
                result = {
                    "revision": self._registry_rev,
                    "changed_roots": list(self._refresh_changed_roots),
                    "projects": None,
                }
            return result
        for attempt in range(3):
            if attempt > 0:
                with self._lock:
                    prev_by_root = {p["root"]: p for p in self._projects}
                    rev0 = self._registry_rev
            if not prev_by_root:
                return self.get_projects()

            pinned_set = set(self._config.get("pinned_roots") or [])
            # CORE-006: refresh hidden projects too -- they remain in the registry,
            # so their rows stay current and pending external changes keep getting
            # tracked. Visibility is applied only in get_projects().
            fresh: list[dict] = []
            changed_roots: list[str] = []
            had_transient_failure = False
            for root in list(prev_by_root.keys()):
                prev = prev_by_root.get(root)
                transient = False
                try:
                    proj = load_project(Path(root), with_git=False)
                except (OSError, subprocess.SubprocessError) as e:
                    print(
                        f"SAIPENVIEW: refresh_known({root}) failed: {e}",
                        file=sys.stderr,
                    )
                    proj = None
                    transient = True
                    had_transient_failure = True
                if proj is None:
                    if prev and transient:
                        # W2-008: a transient read failure keeps the last-known row
                        # so a flaky disk/permission blip doesn't drop a live project.
                        fresh.append(prev)
                    elif prev:
                        # W2-008: a clean disappearance (STATE.md gone --
                        # load_project returns None without raising) drops the row,
                        # so a removed project stops being shown or persisted until
                        # it returns. Flag it as changed so cache/watcher/UI reconcile.
                        changed_roots.append(root)
                    continue
                row = _project_to_dict(proj, pinned_set)
                if prev:
                    row["root"] = prev["root"]
                    row["git_branch"] = prev.get("git_branch", "")
                    row["git_dirty"] = prev.get("git_dirty", False)
                fresh.append(row)
                # CORE-007: detect change by full-row diff, not just the parent
                # STATE 'updated'. A SubSaipen-only change (e.g. a sub BOARD ticket)
                # must still be flagged so the sidebar refreshes and the ticket
                # index rebuilds -- otherwise it stays invisible in UI/search.
                if prev is None or row != prev:
                    changed_roots.append(root)

            if (
                full_refresh_was_pending
                and not changed_roots
                and not had_transient_failure
            ):
                changed_roots = list(prev_by_root)
            fresh.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
            with self._lock:
                if self._registry_rev == rev0:
                    # No concurrent mutation while we reparsed: commit our view.
                    changed = self._replace_projects_locked(fresh)
                    break
                # Conflict: a concurrent mutation happened. Retry (the next
                # attempt re-reads the now-current registry).
        else:
            # Exhausted retries: trust the live registry, do not clobber it.
            return self.get_projects()
        # CORE-007: rebuild the ticket-search index for changed roots so a
        # SubSaipen-only change is reflected in search/UI immediately instead of
        # staying invisible until an unrelated parent change occurs.
        for root in changed_roots:
            self._build_ticket_index(root)
        if changed:
            self._write_cache()
        self._sync_watcher()
        # PERF-002: expose changed_roots for the frontend to skip rebuild.
        with self._lock:
            for root in changed_roots:
                if root not in self._refresh_changed_roots:
                    self._refresh_changed_roots.append(root)
            revision = self._registry_rev
        projects = self.get_projects()
        if known_revision is not None:
            return {
                "revision": revision,
                "changed_roots": changed_roots,
                "projects": projects,
            }
        return projects

    def _cache_records_path(self) -> Path:
        # Keep sidecar name separate from cache.json.* temporary-file patterns;
        # shared-cache cleanup tools treat those names as atomic-write debris.
        return self._cache_file.with_name(self._cache_file.stem + "_records")

    def _cache_record_path(self, root: str) -> Path:
        digest = hashlib.sha256(_canonical_or(root).encode("utf-8")).hexdigest()
        return self._cache_records_path() / f"{digest}.json"

    def _cache_tombstone_path(self, root: str) -> Path:
        # W2-003: legacy. Tombstones were a second durable file per root and
        # competed with the record file, so no operation ordering was
        # crash-atomic (a crash could resurrect a deliberately removed
        # project). Deletion is now an explicit state inside the single
        # digest-named JSON file; this path remains only for reading/migrating
        # pre-existing `.deleted` files.
        digest = hashlib.sha256(_canonical_or(root).encode("utf-8")).hexdigest()
        return self._cache_records_path() / f"{digest}.deleted"

    _CACHE_DELETED_MARKER = "__saipen_deleted__"

    def _load_cache_records(self) -> None:
        """Load dirty-granular records over legacy cache.json.

        W2-003: each canonical root has exactly ONE durable authority -- the
        digest-named ``<digest>.json`` file whose payload is either the
        complete validated row or the deleted marker
        ``{"__saipen_deleted__": true}``. The file is written to a unique
        same-directory temp and committed with ``os.replace``, so after any
        crash the on-disk state is either the complete pre-transition state or
        the complete post-transition state -- never a mixture. Deletion and
        recreation are therefore both crash-atomic.

        Legacy two-file state (record + ``.deleted`` tombstone, both written
        by older versions) is migrated deterministically: a ``.deleted`` file
        drops its row unless a newer record file wins by mtime. Those legacy
        files are never written again.
        """
        try:
            records_dir = self._cache_records_path()
            if not records_dir.is_dir():
                return
            # A manually rewritten legacy cache.json is a fresh complete
            # snapshot; stale sidecar records from an older cache generation
            # must not override it. Sidecar writes update their directory mtime
            # after the legacy migration base was created.
            if self._cache_file.is_file():
                try:
                    # CORE-004: > (strictly newer) so sidecars still load when
                    # cache.json and records_dir share the same mtime tick
                    # (Windows fast creation). A manual rewrite of cache.json
                    # produces a strictly newer mtime.
                    if self._cache_file.stat().st_mtime_ns > records_dir.stat().st_mtime_ns:
                        return
                except (OSError, TypeError):
                    return
            by_root = {row["root"]: row for row in self._projects}

            # PERF-002: single-pass parse -- each sidecar is read and
            # JSON-parsed exactly once.  Parsed rows are stored in a
            # digest-keyed index for O(1) lookup; legacy tombstone
            # comparison uses the same pre-computed digest instead of
            # re-hashing every root on every deletion.
            parsed: dict[str, dict] = {}  # digest -> validated row
            dropped_digests: set[str] = set()
            for record in records_dir.glob("*.json"):
                try:
                    row = json.loads(record.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if (
                    isinstance(row, dict)
                    and row.get(self._CACHE_DELETED_MARKER) is True
                ):
                    dropped_digests.add(record.stem)
                    continue
                if not _valid_cache_row(row):
                    continue
                digest = hashlib.sha256(
                    _canonical_or(row["root"]).encode("utf-8")
                ).hexdigest()
                if record.stem != digest:
                    continue
                parsed[record.stem] = row

            # Legacy `.deleted` tombstones: apply only when no newer record
            # file claims the same digest (mtime wins for recreated roots).
            tombstone_mtimes: dict[str, int] = {}
            for marker in records_dir.glob("*.deleted"):
                try:
                    tombstone_mtimes[marker.stem] = marker.stat().st_mtime_ns
                except OSError:
                    continue
            for digest, tomb_mtime in tombstone_mtimes.items():
                record = records_dir / f"{digest}.json"
                if record.is_file():
                    try:
                        if record.stat().st_mtime_ns > tomb_mtime:
                            continue  # newer record wins (recreated)
                    except OSError:
                        continue
                dropped_digests.add(digest)

            # Build canonical-path -> root-key index for O(1) old-row
            # lookup when applying surviving records.
            canon_index: dict[str, str] = {
                _canonical_or(root): root for root in list(by_root)
            }

            # Drop rows claimed by tombstones or deleted markers.
            for digest in dropped_digests:
                for root_key in list(by_root):
                    if hashlib.sha256(
                        _canonical_or(root_key).encode("utf-8")
                    ).hexdigest() == digest:
                        by_root.pop(root_key, None)

            # Apply surviving parsed records (each was already read once).
            for row in parsed.values():
                canon = _canonical_or(row["root"])
                old_key = canon_index.get(canon)
                if old_key is not None:
                    by_root.pop(old_key, None)
                by_root[row["root"]] = row
            self._projects = list(by_root.values())
            self._projects.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
        except OSError:
            return

    def _write_cache(self) -> None:
        """Persist changed project records without losing another writer's rows.

        CORE-004: the in-memory delta bookkeeping (_last_cache_snapshot,
        _dirty_roots, _cache_deleted_roots) is commit metadata: it advances
        ONLY after the durable os.replace succeeds. If the existing cache is
        unreadable/corrupt, the complete in-memory snapshot is rebuilt rather
        than applying a small delta to an invented empty base. The cross-
        process file lock and atomic replace are preserved (W2-028 merge).
        """
        try:
            with self._lock:
                snapshot = list(self._projects)
                current = {p["root"]: p for p in snapshot}
                previous = getattr(self, "_last_cache_snapshot", {})
                dirty = {
                    root for root, row in current.items() if previous.get(root) != row
                }
                dirty.update(self._dirty_roots)
                deleted = set(previous) - set(current)
                deleted.update(self._cache_deleted_roots)

            # PERF-004: no-op transactions perform zero durable I/O. Once a
            # legacy cache exists (or sidecar records were created), persist
            # only dirty roots and deletion tombstones; never rewrite the
            # complete registry image.
            if not dirty and not deleted:
                return
            if self._cache_file.exists() or self._cache_records_path().exists():
                with _cache_lock, _cache_file_lock(self._cache_file):
                    self._cache_records_path().mkdir(parents=True, exist_ok=True)
                    for root in deleted:
                        # W2-003: crash-atomic deletion. One durable authority
                        # per canonical root -- the <digest>.json file whose
                        # payload is either the validated row or the explicit
                        # deleted marker. Written to a unique same-directory
                        # temp and committed with os.replace so a crash leaves
                        # the on-disk state either fully pre- or fully
                        # post-transition; record + tombstone two-file races
                        # that allowed resurrection are impossible.
                        state_path = self._cache_record_path(root)
                        tmp_path = state_path.with_name(
                            state_path.name + f".del.{os.getpid()}.{time.monotonic_ns()}"
                        )
                        tmp_path.write_text(
                            json.dumps(
                                {self._CACHE_DELETED_MARKER: True},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            encoding="utf-8",
                        )
                        os.replace(tmp_path, state_path)
                        # Migrate legacy tombstone if present (harmless no-op
                        # when absent).
                        self._cache_tombstone_path(root).unlink(missing_ok=True)
                    for root in dirty:
                        if root not in current:
                            continue
                        record_path = self._cache_record_path(root)
                        tmp_path = record_path.with_name(
                            record_path.name + f".tmp.{os.getpid()}.{time.monotonic_ns()}"
                        )
                        tmp_path.write_text(
                            json.dumps(current[root], ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8",
                        )
                        os.replace(tmp_path, record_path)
                        # Removing a legacy tombstone is safe; the new
                        # single-state file is already authoritative.
                        self._cache_tombstone_path(root).unlink(missing_ok=True)
                with self._lock:
                    self._last_cache_snapshot = current
                    self._dirty_roots.clear()
                    self._cache_deleted_roots.clear()
                return

            with _cache_lock, _cache_file_lock(self._cache_file):
                disk_base_valid = False
                disk_rows: dict[str, dict] = {}
                if self._cache_file.is_file():
                    try:
                        stored = json.loads(
                            self._cache_file.read_text(encoding="utf-8")
                        )
                        if isinstance(stored, list):
                            disk_rows = {
                                row["root"]: row
                                for row in stored
                                if isinstance(row, dict)
                                and isinstance(row.get("root"), str)
                            }
                            disk_base_valid = True
                    except (OSError, ValueError):
                        disk_base_valid = False
                if not disk_base_valid:
                    # CORE-004: cannot trust the disk base -- rebuild the
                    # complete snapshot from memory instead of applying the
                    # delta to an empty base (which would drop live rows).
                    disk_rows = dict(current)
                else:
                    for root in deleted:
                        disk_rows.pop(root, None)
                    for root in dirty:
                        if root in current:
                            disk_rows[root] = current[root]
                rows = list(disk_rows.values())
                body = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
                # CORE-004: advance delta bookkeeping ONLY after the durable
                # os.replace succeeds, so a transient failure never suppresses
                # a future retry of the same delta (an earlier write that
                # dropped its bookkeeping would silently lose that delta
                # forever). The bookkeeping itself lives under self._lock
                # but the disk commit is outside the lock on purpose.
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(self._cache_file.parent), prefix="cache.json."
                )
                tmp_path = Path(tmp_name)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(body)
                    os.replace(tmp_path, self._cache_file)
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                with self._lock:
                    self._last_cache_snapshot = current
                    self._dirty_roots.clear()
                    self._cache_deleted_roots.clear()
        except (OSError, ValueError) as e:
            print(
                f"SAIPENVIEW: failed to write cache at {self._cache_file}: {e}",
                file=sys.stderr,
            )

    def get_local_drives(self) -> list[str]:
        from saipenview.scanner import local_drives

        return local_drives()

    def get_status(self) -> dict:
        with self._lock:
            return {
                "scanned": self._has_scanned,
                "scanning": self._scanning,
                "count": len(self._projects),
                "revision": self._registry_rev,
            }

    def get_scan_errors(self) -> list[str]:
        return get_scan_errors()

    def get_scan_error_log(self) -> list[dict]:
        return get_scan_error_log()

    def get_scan_progress(self) -> dict:
        return get_scan_progress()

    def get_changed_roots(self) -> list[str]:
        """Return changed roots mailbox, preserving delivery until consumed."""
        with self._lock:
            changed = list(self._refresh_changed_roots)
            self._refresh_changed_roots = []
            return changed

    def get_linked_worktrees(self) -> list[dict]:
        """Returns cached list of linked worktrees found during the last scan.
        Never mixed into normal project rows -- these are .git-as-file dirs
        without .saipen/ that need manual setup before they appear in the
        main project list."""
        with self._lock:
            return list(self._linked_worktrees)

    def _scan_linked_worktrees(self) -> None:
        """Run linked worktree detection and cache results."""
        roots = self._config.get("scan_roots")
        if not roots:
            self._linked_worktrees = []
            return
        try:
            self._linked_worktrees = find_linked_worktrees(
                roots,
                max_depth=self._config.get("scan_depth", 6),
                delay=self._config.get("scan_delay_ms", 10) / 1000.0,
                extra_excludes=set(self._config.get("exclude_dirs", [])),
            )
        except (OSError, ValueError) as e:
            print(f"SAIPENVIEW: linked worktree scan failed: {e}", file=sys.stderr)
            self._linked_worktrees = []

    def rescan(self) -> list[dict]:
        # W2-001: bump the scan epoch so any older background publication
        # becomes stale and is rejected by _set_cache. Authority is assigned
        # at request start, not by completion timestamps.
        epoch = self._next_scan_epoch()
        self._set_scanning(True)
        projects = scan(
            self._config["scan_roots"],
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
        )
        # _set_cache owns the linked-worktree scan (T-165): calling it here too
        # would run the same worktree walk twice per rescan.
        self._set_cache(projects, force=True, epoch=epoch)
        return self.get_projects()

    def _next_scan_epoch(self) -> int:
        # W2-001: every scan request -- manual or background -- captures an
        # epoch at start; the matching _set_cache commits only if its epoch
        # is still the current one. A newer request bumps this counter first,
        # so a slower older in-flight result becomes stale and is dropped.
        self._scan_epoch += 1
        return self._scan_epoch

    def get_wiki_pages(self) -> list[dict]:
        """Return available wiki pages as [{id, title, filename}, ...]."""
        return [
            {
                "id": "WIKI-001",
                "title": "Project Overview",
                "file": "WIKI-001-project-overview.md",
            },
            {
                "id": "WIKI-002",
                "title": "Architecture & Module Layout",
                "file": "WIKI-002-architecture.md",
            },
            {
                "id": "WIKI-003",
                "title": "Commands, Hotkeys & API",
                "file": "WIKI-003-commands-api.md",
            },
            {
                "id": "WIKI-004",
                "title": "Configuration Reference",
                "file": "WIKI-004-configuration.md",
            },
            {"id": "WIKI-005", "title": "UI & Theme", "file": "WIKI-005-ui-theme.md"},
        ]

    def get_wiki_page(self, page_id: str) -> dict | None:
        """Return wiki page content as {id, title, content} or None."""
        pages = self.get_wiki_pages()
        for p in pages:
            if p["id"] == page_id:
                # Resolve path: project root is 1 level up from saipenview/api.py
                import sys

                if getattr(sys, "frozen", False):
                    base = Path(sys.executable).parent
                else:
                    base = Path(__file__).resolve().parent.parent
                candidate = (
                    base
                    / ".saipen"
                    / "extensions"
                    / "subs"
                    / "saiwiki"
                    / "kitchen"
                    / p["file"]
                )
                if candidate.exists():
                    try:
                        content = read_doc(candidate)
                        return {"id": p["id"], "title": p["title"], "content": content}
                    except OSError as e:
                        print(
                            f"SAIPENVIEW: get_wiki_page read failed: {e}",
                            file=sys.stderr,
                        )
                        return None
                print(
                    f"SAIPENVIEW: get_wiki_page: {candidate} not found", file=sys.stderr
                )
                return None
        return None

    def get_locales(self) -> list[dict]:
        """Return available UI locales as [{code, name}, ...]."""
        return [
            {"code": "en", "name": "English"},
            {"code": "ar", "name": "العربية"},
            {"code": "bg", "name": "Български"},
            {"code": "cs", "name": "Čeština"},
            {"code": "da", "name": "Dansk"},
            {"code": "de", "name": "Deutsch"},
            {"code": "ded", "name": "Дед"},
            {"code": "el", "name": "Ελληνικά"},
            {"code": "es", "name": "Español"},
            {"code": "et", "name": "Eesti"},
            {"code": "fi", "name": "Suomi"},
            {"code": "fr", "name": "Français"},
            {"code": "he", "name": "עברית"},
            {"code": "hi", "name": "हिन्दी"},
            {"code": "hr", "name": "Hrvatski"},
            {"code": "hu", "name": "Magyar"},
            {"code": "id", "name": "Bahasa Indonesia"},
            {"code": "it", "name": "Italiano"},
            {"code": "ja", "name": "日本語"},
            {"code": "ko", "name": "한국어"},
            {"code": "nl", "name": "Nederlands"},
            {"code": "no", "name": "Norsk"},
            {"code": "pl", "name": "Polski"},
            {"code": "pt", "name": "Português"},
            {"code": "ro", "name": "Română"},
            {"code": "ru", "name": "Русский"},
            {"code": "sk", "name": "Slovenčina"},
            {"code": "sv", "name": "Svenska"},
            {"code": "th", "name": "ไทย"},
            {"code": "tr", "name": "Türkçe"},
            {"code": "uk", "name": "Українська"},
            {"code": "vi", "name": "Tiếng Việt"},
            {"code": "zh", "name": "中文"},
            {"code": "zh-CN", "name": "简体中文 (Simplified Chinese)"},
        ]

    def set_locale(self, code: str) -> dict:
        """Set the UI locale. Returns updated config."""
        self._mutate_config(lambda cfg: cfg.__setitem__("locale", code))
        return self.get_config()

    def get_themes(self) -> list[dict]:
        """Available colour palettes as [{slug, label, order}, ...], menu order."""
        return themes.list_themes()

    def get_theme_tokens(self, slug: str | None = None) -> dict:
        """The custom-property values to apply, plus the slug they came from.

        The slug is returned because it may not be the one asked for: an
        unknown slug resolves to the default. The UI needs to know which theme
        is actually on screen, or the Settings picker shows a lie.
        """
        resolved, tokens = themes.resolve(slug or self._config.get("theme"))
        return {"slug": resolved, "tokens": tokens}

    def set_theme(self, slug: str) -> dict:
        """Persist the chosen palette and return the tokens to apply now."""
        resolved, tokens = themes.resolve(slug)
        if resolved:
            self._mutate_config(lambda cfg: cfg.__setitem__("theme", resolved))
        return {"slug": resolved, "tokens": tokens}

    def get_config(self) -> dict:
        return dict(self._config)

    def _mutate_config(self, fn) -> object:
        """Mutate, normalize, and persist config as one transaction.

        W2-003: the mutation is staged on a COPY. Only after the candidate is
        durably persisted (save_config) is it assigned to ``self._config``.
        A persistence failure raises and leaves the live config, disk, and any
        dependent runtime state unchanged at their previous consistent value.

        CORE-004: returns the callback's return value so callers that need
        the persisted value (e.g. toggle_pin's pinned list derived inside the
        lock) can get it from the committed transaction.
        """
        from copy import deepcopy

        from saipenview.config import normalize_config

        with self._lock:
            candidate = normalize_config(deepcopy(self._config))
            result = fn(candidate)
            candidate = normalize_config(candidate)
            save_config(candidate)
            self._config = candidate
            self._verified_roots_cache = {"key": None, "list": [], "set": set()}
            return result

    def save_view_config(self, settings: dict) -> dict:
        # W2-005: the entire read-modify-normalize-replace sequence is one
        # atomic transaction under self._lock. Two concurrent callers
        # (e.g. search_query from poll and zoom_level from user) now see
        # each other's mutations instead of losing them.
        from saipenview.config import normalize_config

        _VIEW_KEYS = (
            "filter_phase",
            "compact_mode",
            "zoom_level",
            "window_width",
            "window_height",
            "window_x",
            "window_y",
            "selected_root",
            "search_query",
            "sidebar_width",
            "show_hidden",
            "top_panel_collapsed",
            "collapse_hint_acknowledged",
            "collapsed_sections",
            "show_on_launch",
            "flash_changes",
            "font_family",
            "custom_commands",
            "file_viewer_default",
            "locale",
            "layout_swap",
            "default_engine",
            "theme",
            "show_agent_panel",
            "projects_collapsed_by_default",
            "projects_unfolded_tail",
            "collapsed_projects",
        )

        def mutate(cfg):
            for k in _VIEW_KEYS:
                if k in settings:
                    cfg[k] = settings[k]
            # CORE-003: normalize_config owns path canonicalization; no
            # second transform here that could drift from load/save.
            normalized = normalize_config(cfg)
            cfg.clear()
            cfg.update(normalized)

        self._mutate_config(mutate)
        return self.get_config()

    def set_engine_overrides(self, overrides: dict) -> dict:
        """Persist the per-engine override dict (T-178), validated exactly as
        launch_agent validates it -- an invalid override is refused and the
        saved value is untouched."""
        if not isinstance(overrides, dict):
            return {"ok": False, "error": "engine_overrides must be an object"}
        for engine_name, entry in overrides.items():
            ok, err = validate_engine_overrides(entry)
            if not ok:
                return {
                    "ok": False,
                    "error": f"engine '{engine_name}': {err}",
                    "invalid_key": engine_name,
                }
        self._mutate_config(
            lambda cfg: cfg.__setitem__("engine_overrides", dict(overrides))
        )
        return {"ok": True, "config": self.get_config()}

    def toggle_pin(self, root_str: str) -> list[dict]:
        # CORE-004: the read-modify-write must happen INSIDE the locked
        # mutation callback. Deriving `pinned` from self._config before the
        # transaction lets a concurrent toggle's committed update be
        # overwritten by this stale pre-lock snapshot (lost update).
        # The callback returns the persisted pinned list (single locked
        # read-modify-write inside _mutate_config).
        # Canonicalize the target: pinned_roots are stored in canonical
        # form (CORE-003), and toggle must match a stored entry exactly.
        from saipenview.paths import canonical

        target = canonical(root_str)

        def _toggle(cfg):
            pinned = list(cfg.get("pinned_roots") or [])
            if target in pinned:
                pinned.remove(target)
            else:
                pinned.append(target)
            cfg["pinned_roots"] = pinned
            return pinned

        pinned = self._mutate_config(_toggle)
        with self._lock:
            changed = False
            for p in self._projects:
                pinned_value = _canonical_or(p["root"]) in pinned
                if p.get("is_pinned") != pinned_value:
                    p["is_pinned"] = pinned_value
                    changed = True
            self._projects.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
            if changed:
                self._mark_registry_mutation_locked(p["root"] for p in self._projects)
            return list(self._projects)

    def hide_project(self, root_str: str) -> list[dict]:
        # CORE-004: derive the hidden list inside the locked mutation.
        from saipenview.paths import canonical

        target = canonical(root_str)

        def _hide(cfg):
            hidden = list(cfg.get("hidden_roots") or [])
            if target not in hidden:
                hidden.append(target)
            cfg["hidden_roots"] = hidden
            return hidden

        self._mutate_config(_hide)
        # CORE-006: hiding is a visibility toggle only. The project stays in the
        # internal registry and under the watcher; get_projects() filters it from
        # the UI. No row is deleted, so unhide needs no rescan.
        return self.get_projects()

    def unhide_project(self, root_str: str) -> list[dict]:
        # CORE-004: derive the hidden list inside the locked mutation.
        from saipenview.paths import canonical

        target = canonical(root_str)

        def _unhide(cfg):
            hidden = list(cfg.get("hidden_roots") or [])
            if target in hidden:
                hidden.remove(target)
            cfg["hidden_roots"] = hidden
            return hidden

        self._mutate_config(_unhide)
        return self.get_projects()

    def get_hidden_projects(self) -> list[dict]:
        """Return the currently-hidden projects from the authoritative registry.

        CORE-003/PERF-007: hiding is visibility-only (CORE-006), so the hidden
        rows already live in ``_projects`` under the watcher. A prior build
        started a fresh recursive scan under every hidden root on every call
        (and crashed when ScanOutcome replaced the list type); this instead
        snapshots the in-memory rows whose canonical root is in ``hidden_roots``
        with ZERO filesystem discovery. The normal watcher/targeted-refresh/
        background-reconciliation machinery keeps those retained rows current.
        """
        hidden_set = {canonical(r) for r in (self._config.get("hidden_roots") or [])}
        if not hidden_set:
            return []
        with self._lock:
            rows = [
                dict(p) for p in self._projects if canonical(p["root"]) in hidden_set
            ]
        # Pinned flag may have changed since the row was built; recompute cheaply.
        pinned_set = set(self._config.get("pinned_roots") or [])
        for r in rows:
            r["is_pinned"] = r["root"] in pinned_set
        return rows

    def open_folder(self, root_str: str) -> bool:
        root = self._resolve_root(root_str)
        if not root:
            print(
                f"SAIPENVIEW: open_folder rejected {root_str!r}: not a verified project root",
                file=sys.stderr,
            )
            return False
        if os.path.exists(root):
            try:
                # S606: os.startfile IS the no-shell Windows API (ShellExecute);
                # the path is an existing dir from our own scan, never user text.
                os.startfile(root)  # noqa: S606
                return True
            except OSError as e:
                print(f"SAIPENVIEW: open_folder({root}) failed: {e}", file=sys.stderr)
        return False

    def open_terminal(self, root_str: str) -> bool:
        root = self._resolve_root(root_str)
        if not root:
            print(
                f"SAIPENVIEW: open_terminal rejected {root_str!r}: not a verified project root",
                file=sys.stderr,
            )
            return False
        if os.path.exists(root):
            try:
                subprocess.Popen(["cmd.exe", "/k", f'cd /d "{root}"'])
                return True
            except (OSError, subprocess.SubprocessError) as e:
                print(
                    f"SAIPENVIEW: open_terminal({root}) failed: {e}",
                    file=sys.stderr,
                )
        return False

    def open_editor(self, root_str: str) -> bool:
        root = self._resolve_root(root_str)
        if not root:
            print(
                f"SAIPENVIEW: open_editor rejected {root_str!r}: not a verified project root",
                file=sys.stderr,
            )
            return False
        if os.path.exists(root):
            try:
                # shell=True used to be needed because `code` is really
                # code.cmd on Windows and Popen won't resolve it otherwise --
                # but that also meant the project path was parsed by cmd, so a
                # directory named e.g. `foo & something.exe` would have EXECUTED
                # it. shutil.which() resolves the .cmd to a real absolute path,
                # so the argument list can be passed straight through with no
                # shell in between (ruff S602).
                code_exe = shutil.which("code")
                if not code_exe:
                    print(
                        "SAIPENVIEW: open_editor: 'code' not found on PATH",
                        file=sys.stderr,
                    )
                    return False
                # 0x08000000 = CREATE_NO_WINDOW
                subprocess.Popen(  # noqa: S603 - resolved absolute path, no shell
                    [code_exe, root], creationflags=0x08000000
                )
                return True
            except (OSError, FileNotFoundError) as e:
                print(f"SAIPENVIEW: open_editor({root}) failed: {e}", file=sys.stderr)
        return False

    def read_file_text(self, file_path: str) -> dict | str | None:
        """Read a file's text content.

        CORE-001: For protocol files (.saipen/), returns a dict
        `{text, edit_version}` where edit_version is the canonical raw_hash
        of the file at read time. The frontend MUST pass this edit_version
        back on save to prevent stale-editor overwrites.
        Non-protocol files return a plain string (backward compat).
        """
        ok, reason = validate_file_path(file_path, self._known_roots())
        if not ok:
            print(
                f"SAIPENVIEW: read_file_text rejected {file_path!r}: {reason}",
                file=sys.stderr,
            )
            return None
        path = Path(canonical(file_path))
        try:
            if path.exists():
                from saipenview.protocol_write import get_coordinator

                if get_coordinator().is_protocol_file(path):
                    from saipenview import saio

                    try:
                        root = get_coordinator().root_for(path)
                        codec = saio.engine(root)["codec"]
                        doc = codec.read_document(path)
                        return {"text": doc.text_norm, "edit_version": doc.raw_hash}
                    except Exception as e:
                        # CORE-001: fail closed -- a plain string would look
                        # readable but its save would never carry a matching
                        # edit_version, so the editor would always be rejected
                        # with no signal to the user about why.
                        print(
                            f"SAIPENVIEW: read_file_text({file_path}) protocol "
                            f"codec failed: {e}",
                            file=sys.stderr,
                        )
                        return None
                # W2-017: ordinary (non-protocol) files return the decoded text.
                text = read_doc(path)
                return text
        except OSError as e:
            print(
                f"SAIPENVIEW: read_file_text({file_path}) failed: {e}", file=sys.stderr
            )
        return None

    def write_file_text(
        self, file_path: str, content: str, edit_version: str | None = None
    ) -> bool:
        """Write content to a file.

        CORE-001: For protocol files, edit_version must be the edit_version
        returned by read_file_text. A mismatch means the file changed since
        the user read it, and the write is refused (STALE_STATE) to prevent
        a stale editor from overwriting a newer revision.
        """
        ok, reason = validate_file_path(file_path, self._known_roots())
        if not ok:
            print(
                f"SAIPENVIEW: write_file_text rejected {file_path!r}: {reason}",
                file=sys.stderr,
            )
            return False
        path = Path(canonical(file_path))
        from saipenview.ownership import AgentOwnershipError
        from saipenview.protocol_write import get_coordinator

        if get_coordinator().is_protocol_file(path):
            # CORE-001: protocol files are CAS-protected. A save without the
            # edit_version read token is a fail-open hole (tokenless editor
            # saves bypass the stale-read check), so refuse it closed -- EXCEPT
            # when creating a brand-new file, which has no prior revision to
            # stale against. Route every mutation through the canonical
            # coordinator so the OS writer lock, journal, recovery preflight,
            # byte-verification, and self-write registration all fire exactly
            # once -- never bypassed by the editor path.
            if not edit_version and path.is_file():
                print(
                    f"SAIPENVIEW: write_file_text refused {file_path!r}: "
                    "protocol file requires edit_version (read it first)",
                    file=sys.stderr,
                )
                return False
            root = get_coordinator().root_for(path)
            guard = self._guard_protocol_write(str(root))
            if guard:
                print(f"SAIPENVIEW: write_file_text refused: {guard}", file=sys.stderr)
                return False
            try:
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                from saipenview import saio
                from saipenview import textio as _textio
                from saipenview.protocol_write import _role_for

                # W2-015: snapshot existence ONCE at entry. The planner may run
                # later (under the coordinator lock, with stale_retry), and the
                # file's existence can transition in between. Without a snapshot,
                # missing->present is misclassified as edit (requires token ->
                # STALE_STATE) and present->missing is misclassified as create
                # (succeeds and overwrites nothing). One snapshot fixes both.
                exists_at_entry = path.is_file()
                expected = edit_version if exists_at_entry else None
                rel = str(path.relative_to(root)).replace("\\", "/")
                role = _role_for(rel)

                def _planner(r, attempt):
                    if exists_at_entry:
                        # Edit intent: file existed when the write was requested.
                        # If it disappeared, that's a stale transition -> refuse.
                        if not path.is_file():
                            return {
                                "ok": False,
                                "code": "STALE_STATE",
                                "message": "file disappeared between read and write",
                                "changed_files": [],
                                "retryable": True,
                                "recovery_required": False,
                                "op_id": None,
                            }
                        # Read encoding via textio (bypasses codec's BOM
                        # rejection on core files) so we preserve the viewer's
                        # encoding contract through the canonical journal.
                        _, enc, newline = _textio.read_doc_meta(path)
                        raw = path.read_bytes()
                        raw_hash = hashlib.sha256(raw).hexdigest()[:16]
                        if expected and raw_hash != expected:
                            return {
                                "ok": False,
                                "code": "STALE_STATE",
                                "message": "file changed since it was read",
                                "changed_files": [],
                                "retryable": True,
                                "recovery_required": False,
                                "op_id": None,
                            }
                        # Map textio encoding names to Document fields.
                        # Strip the -nobom suffix (textio convention, not a real codec).
                        # Detect BOM from raw bytes so we preserve it through the
                        # canonical writer even when textio normalizes the name.
                        codec_enc = enc
                        if codec_enc.endswith("-nobom"):
                            codec_enc = codec_enc[: -len("-nobom")]
                        elif codec_enc == "utf-8-sig":
                            codec_enc = "utf-8"
                        # Detect BOM from raw bytes (independent of encoding name).
                        bom = b""
                        for bom_bytes, _ in _textio._BOMS:
                            if raw.startswith(bom_bytes):
                                bom = bom_bytes
                                break
                    else:
                        # Create intent: file did not exist at entry.
                        # If it appeared, that's a stale transition -> refuse.
                        if path.is_file():
                            return {
                                "ok": False,
                                "code": "STALE_STATE",
                                "message": "file appeared between read and write",
                                "changed_files": [],
                                "retryable": True,
                                "recovery_required": False,
                                "op_id": None,
                            }
                        raw_hash = ""
                        codec_enc = "utf-8"
                        bom = b""
                        newline = "\n"
                    Doc = saio._load_codec_from(saio.resolve_home(r)).Document
                    doc = Doc(
                        text=content,
                        encoding=codec_enc,
                        bom=bom,
                        newline=newline,
                        final_newline=content.endswith("\n"),
                        raw_hash=raw_hash,
                    )
                    return saio.plan(
                        r,
                        f"viewer-{role}",
                        {"operation": f"viewer-{role}"},
                        [(rel, role, content, doc)],
                        {rel: raw_hash},
                        missing_paths=[] if exists_at_entry else [rel],
                    )

                result = get_coordinator().mutate(
                    root,
                    _planner,
                    verification_policy="none",
                    stale_retry=False,
                )
                if not result["ok"]:
                    code = result.get("code")
                    if code == "STALE_STATE":
                        print(
                            f"SAIPENVIEW: write_file_text({file_path}) STALE -- "
                            "file changed since it was read",
                            file=sys.stderr,
                        )
                    elif code == "RECOVERY_REQUIRED":
                        msg = result.get("message", "")
                        print(
                            f"SAIPENVIEW: write_file_text({file_path}) recovery required: {msg}",
                            file=sys.stderr,
                        )
                    else:
                        msg = result.get("message", result)
                        print(
                            f"SAIPENVIEW: write_file_text({file_path}) failed: {msg}",
                            file=sys.stderr,
                        )
                    return False
                return True
            except (OSError, AgentOwnershipError) as e:
                print(
                    f"SAIPENVIEW: write_file_text({file_path}) failed: {e}",
                    file=sys.stderr,
                )
                return False
        try:
            # CORE-003: ordinary files beneath a verified root must also
            # participate in the per-root ownership transaction so that a
            # live agent cannot be clobbered by a direct editor write.
            # WriteCoordinator.root_for() is protocol-only; for ordinary
            # files we find the owning root by canonical containment.
            path_str = str(path)
            owning_root = None
            for vr in self._verified_project_roots():
                if path_str.startswith((vr + os.sep, vr + "/")):
                    if owning_root is None or len(vr) > len(owning_root):
                        owning_root = vr
            if owning_root:
                from saipenview.protocol_write import get_coordinator

                ownership = get_coordinator().ownership
                if not ownership.begin_app_tx(Path(owning_root)):
                    print(
                        f"SAIPENVIEW: write_file_text refused {file_path!r}: "
                        "Core agent is active on this root",
                        file=sys.stderr,
                    )
                    return False
            try:
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                if path.is_file():
                    _, enc, newline = read_doc_meta(path)
                    write_doc(path, content, enc, newline)
                else:
                    write_doc(path, content)
                return True
            finally:
                if owning_root:
                    ownership.end_app_tx(Path(owning_root))
        except OSError as e:
            print(
                f"SAIPENVIEW: write_file_text({file_path}) failed: {e}", file=sys.stderr
            )
            return False

    def _verified_project_roots(self) -> list[str]:
        """Canonical roots the app may actually act on.

        Scanned, pinned and hidden roots that genuinely hold a
        ``.saipen/STATE.md``. A scan root alone -- potentially a whole drive --
        is DISCOVERY scope, never file-access scope, so it grants nothing
        until it is verified to be a project root (T-164).

        PERF-009: the verified set is cached and keyed by the registry
        revision plus pinned/hidden config. Any mutation that could change the
        set (a scan replace, a file-event row change, a pin toggle) bumps the
        revision or the config tuple, so repeated root-taking RPCs resolve in
        O(1) instead of re-canonicalizing and re-statting every project.
        """
        with self._lock:
            rev = self._registry_rev
            projects = [str(p["root"]) for p in self._projects]
        pinned = tuple(self._config.get("pinned_roots") or [])
        hidden = tuple(self._config.get("hidden_roots") or [])
        key = (rev, pinned, hidden)
        if self._verified_roots_cache["key"] == key:
            return self._verified_roots_cache["list"]
        roots: list[str] = []
        roots.extend(projects)
        roots.extend(pinned)
        roots.extend(hidden)
        verified: list[str] = []
        for r in dedupe(roots):
            c = canonical(r)
            if (Path(c) / ".saipen" / "STATE.md").is_file():
                verified.append(c)
        self._verified_roots_cache = {
            "key": key,
            "list": verified,
            "set": set(verified),
        }
        return verified

    def _known_roots(self) -> list[str]:
        """Canonical set of roots the file viewer may open files under.

        Only verified project roots -- anything the app knows about that does
        not hold a ``.saipen/STATE.md`` (a bare scan root such as ``V:\\``)
        is excluded, fail-closed."""
        return self._verified_project_roots()

    def _resolve_root(self, root_str: str) -> str | None:
        """The one resolver every root-taking JS method goes through (T-164).

        Returns the canonical spelling when *root_str* is a verified project
        root the app knows about; None for anything unknown, escaped, or not a
        real project. Callers must return a controlled error on None -- never
        a side effect."""
        try:
            c = canonical(root_str)
        except Exception:  # noqa: BLE001 - any path resolution failure denies
            return None
        self._verified_project_roots()
        if c not in self._verified_roots_cache["set"]:
            return None
        # PERF-009: the cached set is permission scope; the one requested root
        # still needs a fresh liveness proof so a just-deleted STATE.md is
        # caught at this boundary without re-statting the whole registry.
        if not (Path(c) / ".saipen" / "STATE.md").is_file():
            return None
        return c

    def _guard_protocol_write(self, root: str) -> str | None:
        """Reason direct `.saipen/` mutation of *root* is refused, or None.

        The single-writer invariant (T-183): SAIPENVIEW must not become writer
        #2 while the Core agent it launched owns the project's protocol files.
        An agent that is merely stored (finished) grants nothing -- only a live
        or launching process blocks."""
        if self._process_manager.is_running(root):
            return f"Core agent is running for {root}; direct .saipen mutation refused"
        return None

    def _guard_live_agent(self, root: str) -> dict | None:
        """Reason a backend Git tree mutation is refused, or None.

        CORE-001: while a Core agent launched by this viewer owns the project
        -- running, launching-but-not-yet-tracked, or stuck-but-unreaped -- any
        destructive tree mutation (commit/revert/clean) must be refused so
        SAIPENVIEW cannot clobber the agent's live, in-flight work. The preview
        fingerprint only guards against stale tree state BEFORE the call; it
        cannot protect against a concurrent live writer that mutates between
        fingerprint verification and the mutation. This guard is the
        authoritative backend invariant; UI disabling is secondary feedback.
        get_diff (read-only) is intentionally exempt.
        """
        pm = self._process_manager
        if pm.is_running(root) or pm.is_stuck(root):
            return {
                "ok": False,
                "code": "WRITER_BUSY",
                "error": (
                    f"Core agent is active on {root}; commit/revert/delete "
                    "refused to avoid destroying live agent work"
                ),
            }
        return None

    def _git_mutation_tx(self, root: str, fn, *args, **kwargs) -> dict:
        """Run a git_diff mutation under the per-root ownership transaction.

        Acquires the RootOwnership lock before fingerprint verification and
        retains it through the complete Git command. An agent reservation that
        slips in after the pre-check blocks on this lock until the mutation
        finishes, preventing the race where the guard passes and then a live
        agent overwrites the tree before git runs (CORE-001).
        """
        from saipenview.protocol_write import get_coordinator

        ownership = get_coordinator().ownership
        try:
            if not ownership.begin_app_tx(Path(root)):
                return {
                    "ok": False,
                    "code": "WRITER_BUSY",
                    "error": (
                        f"Core agent is active on {root}; "
                        "commit/revert/delete refused to avoid "
                        "destroying live agent work"
                    ),
                }
            return fn(root, *args, **kwargs)
        finally:
            ownership.end_app_tx(Path(root))

    def get_project_detail(self, root_str: str) -> dict | None:
        root = self._resolve_root(root_str)
        if not root:
            return None
        p = Path(root)
        proj = load_project(p)
        if not proj:
            return None
        pinned_set = set(self._config.get("pinned_roots") or [])
        d = _project_to_dict(proj, pinned_set)
        d["custom_commands"] = list(self._config.get("custom_commands") or [])
        d["log_tail"] = load_log_tail(p)
        # Pending backend-tracked external changes for THIS project (repair
        # mission P0): survives project switches, multiple roots/files, and
        # blocks collect until acknowledged or resolved.
        from saipenview.external_changes import get_registry

        d["pending_external_changes"] = [
            c.to_dict() for c in get_registry().pending(root)
        ]
        from saipenview.protocol_write import get_coordinator

        d["recovery"] = get_coordinator().recovery_status(root)
        d["todo_tickets"] = [
            {"id": t.ticket_id, "desc": t.description} for t in proj.board.todo
        ]
        d["blocked_tickets"] = [
            {"id": t.ticket_id, "desc": t.description, "blocker": t.blocker}
            for t in proj.board.blocked
        ]
        d["done_tickets"] = [
            {"id": t.ticket_id, "desc": t.description} for t in proj.board.done[-5:]
        ]
        return d

    def update_project_state(self, root_str: str, updates: dict) -> dict | None:
        from saipenview.parser import update_state

        root = self._resolve_root(root_str)
        if not root:
            return None
        guard = self._guard_protocol_write(root)
        if guard:
            return {
                "ok": False,
                "code": "WRITER_BUSY",
                "message": guard,
                "updated_detail": None,
            }
        p = Path(root)
        result = update_state(p, updates)
        if result.get("ok"):
            # PERF-001: targeted refresh instead of full rescan.
            self._refresh_one_project(root)
            return {
                "ok": True,
                "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                "updated_detail": self.get_project_detail(root),
            }
        return {
            "ok": False,
            "code": result.get("code", "VALIDATION_FAILED"),
            "message": result.get("message", "state update refused"),
            "updated_detail": None,
        }

    def set_hotkey_callback(self, callback) -> None:
        self._on_hotkeys_changed = callback

    def set_snap_hotkey_callback(self, callback) -> None:
        self._on_snap_hotkey_changed = callback

    def set_quit_callback(self, callback) -> None:
        self._on_quit = callback

    def quit(self) -> None:
        if self._on_quit:
            self._on_quit()

    def set_zoom_level(self, zoom: float) -> dict:
        self._mutate_config(lambda cfg: cfg.__setitem__("zoom_level", float(zoom)))
        return self.get_config()

    def move_by(self, dx: int, dy: int) -> None:
        if self._window:
            self._window.move_by(dx, dy)

    def set_sort_order(self, order: str) -> dict:
        self._mutate_config(lambda cfg: cfg.__setitem__("sort_order", order))
        with self._lock:
            self._projects.sort(key=lambda x: _project_sort_key(x, order))
        return self.get_config()

    def set_hotkeys(self, hotkeys: list[str]) -> dict:
        hotkeys = [h.strip() for h in hotkeys if h.strip()]
        if not hotkeys or not self._on_hotkeys_changed:
            return self.get_config()
        previous = self._config["hotkeys"]
        # W2-003: persist first, then bind. A failed persist keeps the
        # registered hotkey at its previous value (no runtime divergence).
        self._mutate_config(lambda cfg: cfg.__setitem__("hotkeys", hotkeys))
        try:
            self._on_hotkeys_changed(hotkeys)
        except (ValueError, KeyError):
            # Bind failed: restore the previous hotkey binding and revert
            # the persisted value so disk, memory, and runtime agree.
            try:
                self._on_hotkeys_changed(previous)
            except (ValueError, KeyError):
                pass
            self._mutate_config(lambda cfg: cfg.__setitem__("hotkeys", previous))
            return {"ok": False, "error": "hotkey binding failed; reverted to previous"}
        return self.get_config()

    def set_snap_hotkey(self, hotkeys: str | list[str]) -> dict:
        if isinstance(hotkeys, str):
            hotkeys = [h.strip() for h in hotkeys.split(",") if h.strip()]
        if not hotkeys or not self._on_snap_hotkey_changed:
            return self.get_config()
        previous = self._config["snap_hotkey"]
        # W2-003: persist first, then bind.
        self._mutate_config(lambda cfg: cfg.__setitem__("snap_hotkey", hotkeys))
        try:
            self._on_snap_hotkey_changed(hotkeys)
        except Exception:  # noqa: BLE001 - defensive catch for hotkey binding failure
            try:
                self._on_snap_hotkey_changed(
                    previous if isinstance(previous, list) else [previous]
                )
            except Exception as revert_err:  # noqa: BLE001 - defensive catch for hotkey rollback failure
                print(
                    f"SAIPENVIEW: snap hotkey rollback to {previous!r} also failed: {revert_err}",
                    file=sys.stderr,
                )
                self._mutate_config(
                    lambda cfg: cfg.__setitem__("snap_hotkey", previous)
                )
                return {
                    "ok": False,
                    "error": f"snap hotkey binding failed; rollback also failed: {revert_err}",
                }
            self._mutate_config(
                lambda cfg: cfg.__setitem__("snap_hotkey", previous)
            )
            return {"ok": False, "error": "snap hotkey binding failed; reverted"}
        return self.get_config()

    def set_scan_tuning(
        self, scan_depth: int, scan_delay_ms: int, rescan_interval: int
    ) -> dict:
        """Rebuilds the background scanner with new tuning."""
        self._mutate_config(
            lambda cfg: cfg.update(
                {
            "scan_depth": max(1, min(8, int(scan_depth))),
            "scan_delay_ms": max(0, int(scan_delay_ms)),
            "rescan_interval": max(10, int(rescan_interval)),
                }
            )
        )
        self._replace_background_scanner()
        return self.get_config()

    def set_scan_roots(self, roots: list[str] | None) -> list[dict]:
        self._mutate_config(lambda cfg: cfg.__setitem__("scan_roots", roots))
        self.background_scanner.stop()
        self._set_scanning(True)
        epoch = self._next_scan_epoch()
        projects = scan(**self._scan_kwargs())
        self._set_cache(projects, force=True, epoch=epoch)
        self._replace_background_scanner()
        return self.get_projects()

    def set_exclude_dirs(self, dirs: list[str]) -> list[dict]:
        self._mutate_config(lambda cfg: cfg.__setitem__("exclude_dirs", list(dirs)))
        return self.rescan()

    def clipboard_copy(self, text: str) -> bool:
        """Copy text to system clipboard via PowerShell (works in pywebview
        where navigator.clipboard is unavailable due to WebView2 secure-context
        requirement). The whole command travels as a base64-encoded UTF-16LE
        blob (-EncodedCommand) and the value is a single-quoted PS literal, so
        user-controlled clipboard text can never be parsed as PowerShell code
        (a `$(...)` payload stays inert data, not an invocation)."""
        try:
            # PS single-quoted literal: only ' needs doubling; $, `, " are inert.
            quoted = "'" + text.replace("'", "''") + "'"
            script = f"Set-Clipboard -Value {quoted}"
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                check=True,
                timeout=5,
            )
            return True
        except (OSError, subprocess.SubprocessError) as e:
            print(f"SAIPENVIEW: clipboard_copy failed: {e}", file=sys.stderr)
            return False

    def browse_folder(self) -> list[dict]:
        """Open native folder picker, add selected folder to scan roots (keeping every
        source already selected -- drives and previously browsed folders alike), then
        rescan the full merged set so the list shows all sources together, not just
        the one just picked."""
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title="Select folder to scan for SAIPEN projects"
        )
        root.destroy()
        if not folder:
            self._set_scanning(False)
            return self.get_projects()

        folder_str = canonical(folder)

        # CORE-004: derive and merge scan_roots inside the locked mutation.
        def _add_scan_root(cfg):
            existing = cfg.get("scan_roots")
            if existing is None:
                # was "auto all local drives" -- make that explicit so adding a
                # folder expands the source set instead of silently replacing it
                existing = _auto_roots()
            # Keep stale roots (T-165): a root whose drive is currently missing
            # is quarantined by scan(), not forgotten here -- dropping it on
            # every browse would defeat the auto-repick-on-return invariant
            # T-138 built. dedupe() canonicalises and collapses case/slash
            # variants (normalize_config runs again before persist).
            existing = dedupe(existing)
            if folder_str not in existing:
                existing.append(folder_str)
            cfg["scan_roots"] = existing

        self._mutate_config(_add_scan_root)
        self._set_scanning(True)
        epoch = self._next_scan_epoch()
        projects = scan(**self._scan_kwargs())
        self._set_cache(projects, force=True, epoch=epoch)
        self._replace_background_scanner()

        return self.get_projects()

    def start(self) -> None:
        # W2-022: subscribe to EventBus here, after full construction.
        # CORE-007: bind the generation at subscription time so a callback
        # captured by EventBus's pre-stop snapshot sees the old gen and aborts.
        # CORE-005: restartable -- stop() resets _event_subscribed, so a second
        # start binds a fresh generation-aware wrapper (no duplicate subs).
        if not self._event_subscribed:
            gen = self._stop_gen

            def _wrapped_file_changed(data, _gen=gen):
                self._on_file_changed(data, _gen=_gen)

            self._wrapped_file_changed = _wrapped_file_changed
            event_bus.subscribe("saipen.project_changed", _wrapped_file_changed)
            self._event_subscribed = True
        # CORE-005: a stopped watcher cannot be revived in place -- give it a
        # fresh Observer, then re-watch the currently known roots.
        self._watcher.revive()
        self._auto_scan = self._config.get("auto_scan", True)
        if self._auto_scan:
            self._set_scanning(True)
            # PERF-005: the BackgroundScanner's scan() already collects
            # linked worktrees in the same traversal (collect_worktrees=True),
            # so the eager prewalk here is redundant. Let the first scan
            # result establish both projects and worktrees.
            self.background_scanner.start()
        self._sync_watcher()

    def stop(self) -> None:
        # W2-011: bump generation BEFORE cancelling timers or unsubscribing.
        # EventBus.publish snapshots callbacks under lock then invokes them
        # outside the lock; a callback captured before this call may still run
        # and schedule new work. The generation gate in _do_root_refresh kills
        # that work regardless of unsubscribe/timer-cancellation ordering.
        self._stop_gen += 1
        self._process_manager.stop_all()
        self.background_scanner.stop()
        # W2-008: flush the external-change registry to disk so acknowledged
        # changes survive shutdown without a race between the last background
        # write-flush and process exit.
        from saipenview.external_changes import get_registry

        get_registry().flush()
        self._watcher.stop()
        # PERF-005: cancel all pending root-refresh timers.
        with self._root_refresh_lock:
            for t in self._root_refresh_timers.values():
                t.cancel()
            self._root_refresh_timers.clear()
        # PERF-008: clear the ticket search index.
        with self._lock:
            self._ticket_index.clear()
        # Unsubscribe the watcher handler: a stopped Api must not keep firing
        # _on_file_changed on later project_changed events. In production the
        # Api lives for the app lifetime, but tests construct many Apis, and a
        # leaked handler made every later watcher event push to a dead window.
        event_bus.unsubscribe(
            "saipen.project_changed",
            getattr(self, "_wrapped_file_changed", self._on_file_changed),
        )
        # T-536: clear all remaining subscribers so a stopped Api never
        # retains dangling callbacks. Without this, subscriber lists grow
        # across start/stop cycles in tests and leak memory in production
        # when the app is embedded (service mode restarts).
        event_bus.clear()
        # CORE-005: stop is idempotent, but restart must subscribe a fresh
        # generation wrapper. Leaving this true made start() believe its
        # callback still existed after unsubscribe.
        self._event_subscribed = False

    def set_auto_scan(self, enabled: bool) -> dict:
        # W2-003: persist first, then apply the runtime start/stop. A failed
        # persist leaves _auto_scan and the scanner at the previous value.
        self._mutate_config(lambda cfg: cfg.__setitem__("auto_scan", enabled))
        self._auto_scan = enabled
        if enabled:
            self._set_scanning(True)
            self.background_scanner.start()
        else:
            self.background_scanner.stop()
            self._set_scanning(False)
        return self.get_config()

    def get_autostart_enabled(self) -> bool:
        """Registry is the source of truth, not a mirrored config flag --
        sidesteps config/registry drift entirely (e.g. after a manual
        uninstall of the Run key, or the project folder getting moved)."""
        from saipenview import autostart

        return autostart.is_enabled()

    def set_autostart_enabled(self, enabled: bool) -> bool:
        from saipenview import autostart

        return autostart.set_enabled(enabled)

    def set_always_on_top(self, enabled: bool) -> dict:
        self._mutate_config(lambda cfg: cfg.__setitem__("always_on_top", enabled))
        if self._window:
            self._window.set_always_on_top(enabled)
        return self.get_config()

    def set_frameless(self, frameless: bool) -> dict:
        """Persist and apply the native-titlebar setting.

        Separate from toggle_frameless below because a checkbox knows the
        state it wants; a blind flip against an unknown current state is how
        the collapse button ended up ADDING a titlebar."""
        self._mutate_config(lambda cfg: cfg.__setitem__("frameless", frameless))
        if self._window:
            self._window.set_frameless(frameless)
        return self.get_config()

    def toggle_frameless(self) -> bool:
        """Toggle the window titlebar on/off via Windows API."""
        if self._window:
            return self._window.toggle_frameless()
        return False

    def collect_outbox(self, root_str: str, sub_name: str, entry_id: str) -> dict:
        """Collect one ready OUTBOX entry from a subSaipen into the main
        project. Returns the result dict from collect_outbox_entry()."""
        from saipenview.parser import collect_outbox_entry

        root = self._resolve_root(root_str)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_protocol_write(root)
        if guard:
            return {"ok": False, "error": guard}
        p = Path(root)
        # The GUI one-click collect on an exact entry IS the explicit named
        # collect authorization for `explicit`-policy producers.
        result = collect_outbox_entry(p, sub_name, entry_id, explicit=True)
        if result.get("ok"):
            # PERF-001: targeted refresh instead of full rescan.
            self._refresh_one_project(root)
            result["updated_detail"] = self.get_project_detail(root)
        return result

    def get_external_changes(self) -> list[dict]:
        """Every unacknowledged external change across all projects, backend-
        persisted (repair mission P0) -- a change to a hidden or background
        project never disappears from this list."""
        from saipenview.external_changes import get_registry

        return [c.to_dict() for c in get_registry().pending()]

    def acknowledge_external_change(
        self, root_str: str, path: str, token: int | None = None
    ) -> dict:
        """Explicit user acknowledge: clear one pending external change.

        When token is provided, acknowledgement is conditional -- only the
        exact generation the user saw is cleared; a newer write remains pending.
        """
        from saipenview.external_changes import get_registry

        # Normalize token to int when provided (frontend may send string)
        if token is not None:
            try:
                token = int(token)
            except (TypeError, ValueError):
                pass
        cleared = get_registry().acknowledge(root_str, path, token)
        return {"ok": cleared}

    def run_command(self, root_str: str, command: str) -> bool:
        """Open a new cmd.exe window in the project root and run a command.
        The window stays open (/k) so the user can see output."""
        root = self._resolve_root(root_str)
        if not root:
            print(
                f"SAIPENVIEW: run_command rejected {root_str!r}: not a verified project root",
                file=sys.stderr,
            )
            return False
        try:
            subprocess.Popen(["cmd.exe", "/k", f'cd /d "{root}" && {command}'])
            return True
        except (OSError, subprocess.SubprocessError) as e:
            print(
                f"SAIPENVIEW: run_command({root}, {command}) failed: {e}",
                file=sys.stderr,
            )
            return False

    def _search_board_for_tickets(self, board_path: Path, q: str) -> list[dict]:
        """Helper: read and search a BOARD.md, return matching tickets as
        [{id, desc, section}] or empty list on any error."""
        if not board_path.is_file():
            return []
        try:
            board = parse_board(read_doc(board_path))
            found = []
            for ticket in board.doing:
                if q in ticket.ticket_id.lower() or q in ticket.description.lower():
                    found.append(
                        {
                            "id": ticket.ticket_id,
                            "desc": ticket.description,
                            "section": "DOING",
                        }
                    )
            for ticket in board.todo:
                if q in ticket.ticket_id.lower() or q in ticket.description.lower():
                    found.append(
                        {
                            "id": ticket.ticket_id,
                            "desc": ticket.description,
                            "section": "TODO",
                        }
                    )
            for ticket in board.blocked:
                if q in ticket.ticket_id.lower() or q in ticket.description.lower():
                    found.append(
                        {
                            "id": ticket.ticket_id,
                            "desc": ticket.description,
                            "section": "BLOCKED",
                        }
                    )
            for ticket in board.done:
                if q in ticket.ticket_id.lower() or q in ticket.description.lower():
                    found.append(
                        {
                            "id": ticket.ticket_id,
                            "desc": ticket.description,
                            "section": "DONE",
                        }
                    )
            return found
        except OSError:
            return []

    @staticmethod
    def _tickets_from_board(board) -> list[dict]:
        """PERF-003: extract ticket index entries from an already-parsed Board.

        Avoids re-reading and re-parsing BOARD.md when the caller already
        holds the parsed ``ProjectStatus.board``.
        """
        section_map = {
            "doing": "DOING",
            "todo": "TODO",
            "done": "DONE",
            "blocked": "BLOCKED",
        }
        tickets: list[dict] = []
        for attr, section in section_map.items():
            for t in getattr(board, attr, []):
                tickets.append(
                    {
                        "id": t.ticket_id,
                        "desc": t.description,
                        "section": section,
                    }
                )
        return tickets

    def _build_ticket_index(
        self, root: str, *, pre_built: list[dict] | None = None
    ) -> None:
        """PERF-003/008: build in-memory ticket search index for one root.

        When *pre_built* is supplied (already-extracted from a parsed Board),
        skip all BOARD file I/O entirely.  Otherwise fall back to reading
        sub/translate boards from disk.
        """
        if pre_built is not None:
            with self._lock:
                self._ticket_index[root] = pre_built
            return
        tickets: list[dict] = []
        try:
            board_path = Path(root) / ".saipen" / "BOARD.md"
            tickets.extend(self._search_board_for_tickets(board_path, ""))
            # Also index sub-agent and translate boards.
            proj = next((p for p in self._projects if p["root"] == root), None)
            if proj:
                for sub in proj.get("subs") or []:
                    sub_path = sub.get("path", "")
                    if sub_path:
                        for t in self._search_board_for_tickets(
                            Path(sub_path) / "BOARD.md", ""
                        ):
                            t["sub_name"] = sub.get("name", "?")
                            tickets.append(t)
                translate = proj.get("translate")
                if translate and translate.get("path"):
                    for t in self._search_board_for_tickets(
                        Path(translate["path"]) / "BOARD.md", ""
                    ):
                        t["sub_name"] = translate.get("name", "saitranslate")
                        tickets.append(t)
        except OSError:
            pass
        with self._lock:
            self._ticket_index[root] = tickets

    def quick_search(self, query: str) -> list[dict]:
        """Search all cached projects by name AND read their BOARD.md
        (and sub-agent BOARD.md files) to find matching tickets.

        Returns list of {root, name, phase, matched_field,
        matched_tickets: [{id, desc, section}],
        sub_matched_tickets: [{sub_name, id, desc, section}].}"""
        q = query.strip().lower()
        if not q:
            return []
        results = []
        with self._lock:
            projects = list(self._projects)
        for p in projects:
            root = p["root"]
            name = p["name"]
            phase = p["phase"]
            matched_tickets = []
            sub_matched_tickets = []
            matched_field = None

            # Check project name
            if name.lower().find(q) != -1:
                matched_field = "name"

            # PERF-008: search the in-memory index instead of reading BOARD files.
            with self._lock:
                indexed = list(self._ticket_index.get(root, []))
            matched_tickets = []
            sub_matched_tickets = []
            for t in indexed:
                if q in t.get("id", "").lower() or q in t.get("desc", "").lower():
                    entry = {
                        "id": t["id"],
                        "desc": t["desc"],
                        "section": t["section"],
                    }
                    if "sub_name" in t:
                        entry["sub_name"] = t["sub_name"]
                        sub_matched_tickets.append(entry)
                    else:
                        matched_tickets.append(entry)

            if matched_field or matched_tickets or sub_matched_tickets:
                results.append(
                    {
                        "root": root,
                        "name": name,
                        "phase": phase,
                        "matched_tickets": matched_tickets,
                        "sub_matched_tickets": sub_matched_tickets,
                        "matched_field": matched_field or "ticket",
                    }
                )
        return results

    def reorder_ticket(
        self,
        root_str: str,
        ticket_id: str,
        section: str,
        before_ticket_id: str | None = None,
    ) -> dict | None:
        """Reorder a ticket within its section (drag-drop, T-175). Returns
        {ok, code, message, updated_detail} or None on unknown root."""
        from saipenview.parser import reorder_ticket

        root = self._resolve_root(root_str)
        if not root:
            return None
        guard = self._guard_protocol_write(root)
        if guard:
            return {
                "ok": False,
                "code": "WRITER_BUSY",
                "message": guard,
                "updated_detail": None,
            }
        p = Path(root)
        result = reorder_ticket(p, ticket_id, section, before_ticket_id)
        if result.get("ok"):
            return {
                "ok": True,
                "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                "updated_detail": self.get_project_detail(root),
            }
        return {
            "ok": False,
            "code": result.get("code", "VALIDATION_FAILED"),
            "message": result.get("message", "reorder refused"),
            "updated_detail": None,
        }

    def record_manual_work(
        self,
        root_str: str,
        description: str,
        operation_id: str | None = None,
        ack_tokens: list[tuple[str, int]] | None = None,
    ) -> dict:
        """Record a user's manual edit as a board entry (T-127).

        ``operation_id`` is generated at UI invocation and carried through
        retry/resume: idempotency is by operation id, never by human prose.
        Validated here (type/length/charset) so a malformed id cannot be
        persisted as evidence.
        """
        from saipenview.parser import record_manual_work

        root = self._resolve_root(root_str)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_protocol_write(root)
        if guard:
            return {"ok": False, "error": guard}
        if operation_id is not None:
            import re as _re

            if (
                not isinstance(operation_id, str)
                or not (1 <= len(operation_id) <= 64)
                or not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", operation_id)
            ):
                return {
                    "ok": False,
                    "code": "INVALID_ID",
                    "message": "operation_id must be 1-64 chars of [A-Za-z0-9._-]",
                }
        from saipenview.external_changes import get_registry
        result = record_manual_work(Path(root), description, operation_id)
        if result.get("ok") and ack_tokens:
            for pc in ack_tokens:
                if hasattr(pc, "rel_path"):
                    get_registry().acknowledge(str(root), pc.rel_path, pc.token)
                else:
                    get_registry().acknowledge(str(root), pc[0], pc[1])
            # The watcher (T-124) picks up the BOARD/LOG change and
            # targeted-refreshes the cache row.
            self._refresh_one_project(root)

        return result

    def toggle_ticket_status(
        self,
        root_str: str,
        ticket_id: str,
        action: str,
        blocker_reason: str | None = None,
    ) -> dict | None:
        """Move a ticket between sections on BOARD.md: start (TODO->DOING),
        done (DOING->DONE), reopen (DONE->TODO), block (->BLOCKED, with the
        reason appended as `| blocker:`), unblock (BLOCKED->TODO). Returns
        {ok, code, message, updated_detail} or None on unknown root."""
        from saipenview.parser import move_ticket

        root = self._resolve_root(root_str)
        if not root:
            return None
        guard = self._guard_protocol_write(root)
        if guard:
            return {
                "ok": False,
                "code": "WRITER_BUSY",
                "message": guard,
                "updated_detail": None,
            }
        p = Path(root)
        result = move_ticket(p, ticket_id, action, blocker_reason=blocker_reason)
        if result.get("ok"):
            # PERF-001: targeted refresh instead of full rescan.
            self._refresh_one_project(root)
            return {
                "ok": True,
                "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                "updated_detail": self.get_project_detail(root),
            }
        return {
            "ok": False,
            "code": result.get("code", "VALIDATION_FAILED"),
            "message": result.get("message", "ticket move refused"),
            "updated_detail": None,
        }

    def minimize_window(self) -> None:
        """Minimize the main window."""
        if self._window:
            self._window.minimize()

    def maximize_window(self) -> None:
        """Maximize the main window."""
        if self._window:
            self._window.maximize()

    def restore_window(self) -> None:
        """Restore the main window from minimized/maximized."""
        if self._window:
            self._window.restore()

    def close_window(self) -> None:
        """Close the main window (hides to tray)."""
        if self._window:
            self._window.hide()

    # ── Agent Engine Control (Wave 1) ─────────────────────────────────

    def get_engines(self) -> list[dict]:
        """Return all registered engines with availability status."""
        return [eng.to_dict() for _, eng in list_engines()]

    def launch_agent(self, root: str, engine_name: str, instruction: str) -> dict:
        """Launch an agent process on a project.

        Args:
            root: Project root path.
            engine_name: Engine identifier (e.g. 'claude-code', 'generic-cli').
            instruction: Prompt or command to send to the agent.

        Returns:
            Dict with 'ok' bool and details or 'error' string.
        """
        engine = get_engine(engine_name)
        if not engine:
            return {"ok": False, "error": f"Unknown engine: {engine_name}"}
        if not engine.detect():
            return {
                "ok": False,
                "error": f"Engine '{engine.display_name}' not found on this machine",
            }
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}

        # engine_overrides was a documented-but-dead config key (T-168): now it
        # is the real override surface -- path / extra_args / env per engine,
        # validated before anything launches.
        overrides = (self._config.get("engine_overrides") or {}).get(engine_name)
        if overrides:
            wrapped, err = _apply_engine_overrides(engine, overrides)
            if wrapped is None:
                return {"ok": False, "error": err}
            engine = wrapped

        result = self._process_manager.launch(engine, root, instruction)
        # W2-026: expose run_id so frontend can bind control calls to it
        if result.get("ok") and "run_id" not in result:
            result["run_id"] = None
        return result

    def stop_agent(self, root: str, expected_run_id: str | None = None) -> dict:
        """Kill a running agent process."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.kill(root, expected_run_id=expected_run_id)

    def add_human_note(self, root: str, note: str) -> dict:
        """Leave a note the NEXT agent will actually pick up.

        This used to append to the end of STATE.md, which put the line after
        the frontmatter's closing `---` -- outside the block every reader
        parses. `parse_frontmatter` returned None for it, and BOOT.md step 5
        ("human_note: set? Apply it this session, clear it, LOG the trace")
        looks in exactly the place the note never reached. So the UI's Note
        button wrote a message to the agent that no agent could ever read, and
        said "ok" while doing it.

        Goes through update_state, which rewrites the frontmatter block itself
        -- that also fixes the append-safety problem the plain "a" mode had:
        a STATE.md not ending on a line boundary would have had its last field
        extended rather than a new line added (SAIPEN 7.147.0).

        Newlines are stripped: the frontmatter is flat one-key-per-line, so an
        embedded newline would silently split the note into a bogus second key.
        """
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_protocol_write(root)
        if guard:
            return {"ok": False, "error": guard}
        state_md = Path(root) / ".saipen" / "STATE.md"
        if not state_md.exists():
            return {"ok": False, "error": "STATE.md not found"}
        flat = " ".join(str(note).split())
        if not flat:
            return {"ok": False, "error": "note is empty"}
        try:
            result = update_state(Path(root), {"human_note": flat})
            if not result.get("ok"):
                return {
                    "ok": False,
                    "code": result.get("code", "VALIDATION_FAILED"),
                    "message": result.get(
                        "message", "STATE.md has no frontmatter block"
                    ),
                }
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def get_diff(self, root: str) -> dict:
        """Full preview: tracked diff + untracked content + mutation scope."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return get_working_diff(root)

    def commit_agent_work(
        self, root: str, message: str, fingerprint: str | None = None
    ) -> dict:
        """Commit exactly the scope the preview showed (T-162)."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_live_agent(root)
        if guard:
            return guard
        return self._git_mutation_tx(root, commit_agent_work, message, fingerprint)

    def revert_agent_work(self, root: str, fingerprint: str | None = None) -> dict:
        """Restore tracked changes only; untracked files are untouched."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_live_agent(root)
        if guard:
            return guard
        return self._git_mutation_tx(root, revert_agent_work, fingerprint)

    def delete_untracked_files(self, root: str, fingerprint: str | None = None) -> dict:
        """Explicit separate operation: delete untracked files (T-162)."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_live_agent(root)
        if guard:
            return guard
        return self._git_mutation_tx(root, delete_untracked_files, fingerprint)

    def send_agent_input(
        self, root: str, text: str, expected_run_id: str | None = None
    ) -> dict:
        """Send text to a running agent's stdin."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.send_input(
            root, text, expected_run_id=expected_run_id
        )

    def get_agent_output(
        self, root: str, since_line: int = 0, expected_run_id: str | None = None
    ) -> dict:
        """Return new output lines since a given line number.

        W2-004: expected_run_id lets the caller express which run they
        expect.  If the active run differs the response carries a stale-run
        marker so the frontend discards it instead of appending to the wrong
        run's console.
        """
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.get_output(
            root, since_line, expected_run_id=expected_run_id
        )

    def get_agent_status(self, root: str, expected_run_id: str | None = None) -> dict:
        """Return status info for an agent process on a project.

        W2-004: expected_run_id lets the caller express which run they
        expect.  If the active run differs the response carries a stale-run
        marker so the frontend discards it instead of showing stale status.
        """
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.get_status(root, expected_run_id=expected_run_id)

    def list_running_agents(self) -> list[dict]:
        """Return status dicts for all tracked agent processes."""
        return self._process_manager.list_running()

    def running_agent_count(self) -> int:
        """PERF-004: count live agents without psutil introspection.

        The toolbar badge only needs a count. ``list_running_agents``
        invokes ``get_status()`` per agent (cpu_percent, memory_info),
        which is O(N) process-API work for a single toolbar number.
        """
        return self._process_manager.count_running()

    def get_agent_history(self, root: str, limit: int = 20) -> list[dict]:
        """Past agent runs for a project, newest first, across restarts."""
        root = self._resolve_root(root)
        if not root:
            return []
        return self._process_manager.sessions.history(root, limit=limit)

    def get_agent_transcript(self, run_id: str, max_lines: int = 2000) -> dict:
        """The stored output of one past run."""
        return self._process_manager.sessions.transcript(run_id, max_lines=max_lines)

    def get_last_agent_transcript(self, root: str, max_lines: int = 500) -> dict:
        """Last run for a project plus its transcript.

        This is what the panel shows when nothing is running: without it a
        restart presents an empty console and no evidence an agent was ever
        here, which is the whole defect this exists to close.
        """
        root = self._resolve_root(root)
        if not root:
            return {"found": False}
        last = self._process_manager.sessions.last_run(root)
        if not last:
            return {"found": False}
        body = self._process_manager.sessions.transcript(
            last["run_id"], max_lines=max_lines
        )
        return {"found": bool(body.get("found")), "run": last, **body}
