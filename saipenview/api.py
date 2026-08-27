"""JS-facing API exposed to the pywebview window as `pywebview.api`."""

# Agent engine layer (Wave 1)

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
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


def _project_to_dict(
    project: ProjectStatus, pinned_roots: set[str] | None = None
) -> dict:
    root_str = str(project.root)
    is_pinned = bool(pinned_roots and root_str in pinned_roots)
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


class Api:
    """Owns the cached scan result + user config; BackgroundScanner refreshes off-thread."""

    def __init__(self, on_hotkeys_changed=None, window=None, debounce_delay: float = 0.1):
        self._window = window
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._projects: list[dict] = []
        self._has_scanned = False
        self._scanning = False
        self._config = load_config()
        self._auto_scan = self._config.get("auto_scan", True)
        self._on_hotkeys_changed = on_hotkeys_changed
        self._on_snap_hotkey_changed = None
        self._on_quit = None
        self._cache_file = config_path().parent / "cache.json"
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
                valid_rows = []
                for p in candidate:
                    if isinstance(p, dict) and isinstance(p.get("root"), str):
                        valid_rows.append(p)
                    else:
                        # Any poisoned entry poisons the whole cache -- fail
                        # closed and start fresh rather than silently dropping
                        # rows (CORE-013 hardening). A row with a non-dict type,
                        # a missing root, or a non-string root would crash the
                        # row consumers downstream.
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
        # PERF-008: in-memory ticket search index, keyed by root.
        self._ticket_index: dict[str, list[dict]] = {}
        # PERF-002: when True, refresh_known() must do a full re-parse (startup,
        # or just after a scan replaced the cache). Between scans the watcher
        # already keeps _projects current, so an idle poll may short-circuit
        # and skip the re-parse entirely.
        self._full_refresh_pending = True
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
        )

        event_bus.subscribe("saipen.project_changed", self._on_file_changed)
        # The watcher belongs to the Api/project registry, not the
        # ProcessManager (T-124): every known project is watched, agent
        # launch/finish has nothing to do with it.
        self._watcher = SaipenWatcher()

        # CORE-004 / T-542: debounce state must be INSTANCE-owned.
        self._debounce_delay = debounce_delay
        self._root_refresh_timers: dict[str, threading.Timer] = {}
        self._root_refresh_lock = threading.RLock()
        # Exact files observed to change per root with immediate origin attribution:
        # root -> {fname: origin}
        self._root_refresh_files: dict[str, dict[str, str]] = {}

    def _on_file_changed(self, data: dict) -> None:
        root = data["root"]
        changed_file = data.get("file")
        origin = "external"
        if changed_file:
            from saipenview.external_changes import get_registry
            from saipenview.protocol_write import get_coordinator

            coord = get_coordinator()
            changed_path = Path(root) / ".saipen" / changed_file
            try:
                if coord.self_writes.has_live(root, changed_file):
                    # PERF-004: a live self-write record exists, so this file is
                    # in our write window -- but an EXTERNAL edit can land in the
                    # same sub-second window AFTER our write. We must still verify
                    # the file's CURRENT fingerprint against the registered one,
                    # not blindly trust has_live(): otherwise an outside change
                    # would be mislabeled "self" and its external-change evidence
                    # never recorded. Hashing one changed file is bounded cost.
                    fp = coord.fingerprint(changed_path)
                    origin = "self" if coord.self_writes.consume(root, changed_file, fp) else "external"
                    if origin == "external":
                        get_registry().record(root, changed_file, fp)
                else:
                    # No self-write candidate for this file: it cannot be ours,
                    # so classify external WITHOUT hashing (PERF-004 win) and
                    # record the external evidence.
                    origin = "external"
                    fp = coord.fingerprint(changed_path)
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
                timer = threading.Timer(self._debounce_delay, self._do_root_refresh, args=(root,))
                timer.daemon = True
                self._root_refresh_timers[root] = timer
                timer.start()

        if should_run_now:
            self._do_root_refresh(root)

    def _do_root_refresh(self, root: str) -> None:
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
        """A change to this .saipen artifact moves the ticket index."""
        low = fname.lower()
        return "ticket" in low or low.startswith("state") or "board" in low

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
        pinned_set = set(self._config.get("pinned_roots") or [])
        try:
            proj = load_project(Path(root), with_git=False)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"SAIPENVIEW: targeted refresh({root}) failed: {e}", file=sys.stderr)
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
                self._projects = [p for p in self._projects if p["root"] != root]
                self._registry_rev += 1
                self._ticket_index.pop(root, None)
                vanished = True
            else:
                row = _project_to_dict(proj, pinned_set)
                row["git_branch"] = prev.get("git_branch", "")
                row["git_dirty"] = prev.get("git_dirty", False)
                for i, p in enumerate(self._projects):
                    if p["root"] == root:
                        self._projects[i] = row
                        break
                self._projects.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
                # CORE-007: bump rev on existing-row replacement so concurrent
                # refresh_known detects the mutation and retries instead of
                # clobbering with a stale parse.
                self._registry_rev += 1

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
        if affects_index:
            # PERF-008: rebuild the ticket index for this root.
            self._build_ticket_index(root)
        if affects_cache:
            self._write_cache()

    def _sync_watcher(self) -> None:
        """Reconcile the watcher's watch set with the known projects (T-124)."""
        with self._lock:
            roots = [p["root"] for p in self._projects]
        self._watcher.sync(roots)

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
        )
        if self._auto_scan:
            self.background_scanner.start()

    def _sort_order(self) -> str:
        return self._config.get("sort_order", "smart")

    def _set_cache(
        self,
        projects,
        force: bool = False,
        complete: bool = True,
        worktrees=None,
    ) -> None:
        """Update the project cache from a scan result.

        CORE-011: accepts either a ScanOutcome or a plain list of
        ProjectStatus. A complete empty result replaces the cache; an
        incomplete/failed result preserves existing rows.
        PERF-001/PERF-003: prefers worktrees passed through from the scan
        (ScanOutcome or the ``worktrees`` kwarg) so the linked-worktree walk
        is never done twice.
        """
        from saipenview.scanner import ScanOutcome

        if isinstance(projects, ScanOutcome):
            complete = projects.complete
            project_list = projects.projects
            worktrees = projects.worktrees
        else:
            project_list = projects
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
        with self._lock:
            # CORE-011: preserve old cache only for incomplete/failed scans.
            # A complete empty scan replaces cache with empty (vanished
            # projects must be removed).
            # CORE-005: incomplete-result safety is unconditional -- force
            # controls complete-only replacement, never authorizes an
            # incomplete erase of the existing registry.
            if not complete and self._has_scanned and self._projects:
                self._scanning = False
                return
            if not force and not project_list and complete and self._has_scanned and self._projects:
                # Complete scan returned zero projects: all previous ones vanished.
                pass  # fall through to set empty
            self._projects = items
            self._registry_rev += 1
            self._has_scanned = True
            self._scanning = False
        # PERF-003: if the scan already collected worktrees, use them directly.
        # Fall back to a standalone walk only for non-scan callers.
        if worktrees is not None:
            with self._lock:
                self._linked_worktrees = worktrees
        else:
            self._scan_linked_worktrees()
        # Atomic write (temp + replace) via the shared helper -- a crash mid
        # plain write left truncated JSON that __init__'s json.load choked on.
        self._write_cache()
        # PERF-008: rebuild ticket index for all current roots.
        with self._lock:
            roots = [p["root"] for p in self._projects]
        for r in roots:
            self._build_ticket_index(r)
        # Watch exactly what we know about (T-124).
        self._sync_watcher()
        # PERF-002: a scan just replaced the cache with freshly-discovered
        # roots; the next idle short-circuit must do one reconciliation parse
        # so newly-found roots get their ticket index built here (in
        # refresh_known), not only in the scanner path.
        self._full_refresh_pending = True

    def get_projects(self) -> list[dict]:
        hidden_set = set(self._config.get("hidden_roots") or [])
        with self._lock:
            return [p for p in self._projects if p["root"] not in hidden_set]

    def refresh_known(self) -> list[dict]:
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
        if not full_refresh_was_pending and not self._scanning:
            # Idle (no scan, no startup reconciliation pending): the watcher
            # already maintains _projects, so skip the re-parse entirely
            # (PERF-002 win). The previous code never cleared this flag, which
            # forced every 5s poll into an O(projects) reparse.
            self._refresh_changed_roots = []
            return self.get_projects()
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
            for root in list(prev_by_root.keys()):
                prev = prev_by_root.get(root)
                transient = False
                try:
                    proj = load_project(Path(root), with_git=False)
                except (OSError, subprocess.SubprocessError) as e:
                    print(f"SAIPENVIEW: refresh_known({root}) failed: {e}", file=sys.stderr)
                    proj = None
                    transient = True
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
                    row["git_branch"] = prev.get("git_branch", "")
                    row["git_dirty"] = prev.get("git_dirty", False)
                fresh.append(row)
                # CORE-007: detect change by full-row diff, not just the parent
                # STATE 'updated'. A SubSaipen-only change (e.g. a sub BOARD ticket)
                # must still be flagged so the sidebar refreshes and the ticket
                # index rebuilds -- otherwise it stays invisible in UI/search.
                if prev is None or row != prev:
                    changed_roots.append(root)

            fresh.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
            with self._lock:
                if self._registry_rev == rev0:
                    # No concurrent mutation while we reparsed: commit our view.
                    changed = fresh != self._projects
                    self._projects = fresh
                    self._registry_rev += 1
                    break
                # Conflict: a concurrent mutation happened. Retry (the next
                # attempt re-reads the now-current registry).
        else:
            # Exhausted retries: trust the live registry, do not clobber it.
            self._refresh_changed_roots = []
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
        self._refresh_changed_roots = changed_roots
        return self.get_projects()

    def _write_cache(self) -> None:
        try:
            import tempfile

            with self._lock:
                snapshot = list(self._projects)
            # One writer lock + a unique temp name per write (T-124): a shared
            # <name>.tmp would let two concurrent writes clobber each other's
            # temp before os.replace, and a crashed first writer would leave
            # its temp for the second to replace.
            with self._cache_lock:
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(self._cache_file.parent), prefix="cache.json."
                )
                tmp_path = Path(tmp_name)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(snapshot, f)
                    os.replace(tmp_path, self._cache_file)
                finally:
                    try:
                        if tmp_path.exists():
                            tmp_path.unlink()
                    except OSError:
                        pass
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
            }

    def get_scan_errors(self) -> list[str]:
        return get_scan_errors()

    def get_scan_error_log(self) -> list[dict]:
        return get_scan_error_log()

    def get_scan_progress(self) -> dict:
        return get_scan_progress()

    def get_changed_roots(self) -> list[str]:
        """PERF-002: return roots that changed since last refresh_known(),
        then clear the list. The frontend uses this to skip sidebar rebuild
        and detail reload when nothing changed."""
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
        self._set_scanning(True)
        projects = scan(
            self._config["scan_roots"],
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
        )
        # _set_cache owns the linked-worktree scan (T-165): calling it here too
        # would run the same worktree walk twice per rescan.
        self._set_cache(projects, force=True)
        return self.get_projects()

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
        self._config["locale"] = code
        save_config(self._config)
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
            self._config["theme"] = resolved
            save_config(self._config)
        return {"slug": resolved, "tokens": tokens}

    def get_config(self) -> dict:
        return dict(self._config)

    def save_view_config(self, settings: dict) -> dict:
        # CORE-015: runtime and persisted state must be identical. Build the
        # candidate, normalize it via the canonical normalizer (including path
        # canonicalization), persist exactly that normalized candidate, then
        # replace live _config with the same values. Callers never see raw
        # invalid values that differ from disk.
        from saipenview.config import normalize_config
        from saipenview.paths import canonical, dedupe
        candidate = dict(self._config)
        for k in (
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
        ):
            if k in settings:
                candidate[k] = settings[k]
        # Normalize via canonical normalizer (type/range/enum validation)
        normalized = normalize_config(candidate)
        if isinstance(normalized.get("scan_roots"), list):
            normalized["scan_roots"] = dedupe(normalized["scan_roots"])
        for key in ("pinned_roots", "hidden_roots"):
            normalized[key] = dedupe(normalized.get(key))
        if normalized.get("selected_root"):
            try:
                normalized["selected_root"] = canonical(normalized["selected_root"])
            except Exception:
                pass
        # Persist the exact normalized candidate
        save_config(normalized)
        # Replace live config with what was persisted (load back to be sure)
        self._config = normalized
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
        self._config["engine_overrides"] = dict(overrides)
        save_config(self._config)
        return {"ok": True, "config": self.get_config()}

    def toggle_pin(self, root_str: str) -> list[dict]:
        pinned = list(self._config.get("pinned_roots") or [])
        if root_str in pinned:
            pinned.remove(root_str)
        else:
            pinned.append(root_str)
        self._config["pinned_roots"] = pinned
        save_config(self._config)
        with self._lock:
            for p in self._projects:
                p["is_pinned"] = p["root"] in pinned
            self._projects.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
            # CORE-007: bump rev so concurrent refresh_known sees the mutation.
            self._registry_rev += 1
            return list(self._projects)

    def hide_project(self, root_str: str) -> list[dict]:
        hidden = list(self._config.get("hidden_roots") or [])
        if root_str not in hidden:
            hidden.append(root_str)
        self._config["hidden_roots"] = hidden
        save_config(self._config)
        # CORE-006: hiding is a visibility toggle only. The project stays in the
        # internal registry and under the watcher; get_projects() filters it from
        # the UI. No row is deleted, so unhide needs no rescan.
        return self.get_projects()

    def unhide_project(self, root_str: str) -> list[dict]:
        hidden = list(self._config.get("hidden_roots") or [])
        if root_str in hidden:
            hidden.remove(root_str)
        self._config["hidden_roots"] = hidden
        save_config(self._config)
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
                text = read_doc(path)
                # CORE-001: for protocol files, return the canonical version
                # so the caller can prove they're saving against the same
                # revision they read. A codec failure is not a green light to
                # hand back raw text -- that would leak a non-CAS-readable
                # path whose subsequent save would always be refused as stale.
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
                        # readable but its save could never carry a matching
                        # edit_version, so the editor would always be rejected
                        # with no signal to the user about why.
                        print(
                            f"SAIPENVIEW: read_file_text({file_path}) protocol "
                            f"codec failed: {e}",
                            file=sys.stderr,
                        )
                        return None
        except OSError as e:
            print(
                f"SAIPENVIEW: read_file_text({file_path}) failed: {e}", file=sys.stderr
            )
        return None

    def write_file_text(self, file_path: str, content: str, edit_version: str | None = None) -> bool:
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
                import codecs
                import hashlib
                from saipenview import saio
                from saipenview.protocol_write import _role_for
                from saipenview import textio as _textio

                expected = edit_version if path.is_file() else None
                rel = str(path.relative_to(root)).replace("\\", "/")
                role = _role_for(rel)

                def _planner(r, attempt):
                    if path.is_file():
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
                        no_bom = False
                        if codec_enc.endswith("-nobom"):
                            codec_enc = codec_enc[: -len("-nobom")]
                            no_bom = True
                        elif codec_enc == "utf-8-sig":
                            codec_enc = "utf-8"
                        # Detect BOM from raw bytes (independent of encoding name).
                        bom = b""
                        for bom_bytes, _ in _textio._BOMS:
                            if raw.startswith(bom_bytes):
                                bom = bom_bytes
                                break
                    else:
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
                        missing_paths=[] if path.is_file() else [rel],
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
            # W2-003: ordinary files beneath a verified root must also
            # participate in the per-root ownership transaction so that a
            # live agent cannot be clobbered by a direct editor write.
            root = get_coordinator().root_for(path)
            if root:
                ownership = get_coordinator().ownership
                if not ownership.begin_app_tx(Path(root)):
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
                if root:
                    ownership.end_app_tx(Path(root))
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
        until it is verified to be a project root (T-164)."""
        roots: list[str] = []
        with self._lock:
            roots.extend(str(p["root"]) for p in self._projects)
        roots.extend(self._config.get("pinned_roots") or [])
        roots.extend(self._config.get("hidden_roots") or [])
        verified: list[str] = []
        for r in dedupe(roots):
            c = canonical(r)
            if (Path(c) / ".saipen" / "STATE.md").is_file():
                verified.append(c)
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
        if c not in self._verified_project_roots():
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

    def _git_mutation_tx(
        self, root: str, fn, *args, **kwargs
    ) -> dict:
        """Run a git_diff mutation under the per-root ownership transaction.

        Acquires the RootOwnership lock before fingerprint verification and
        retains it through the complete Git command. An agent reservation that
        slips in after the pre-check blocks on this lock until the mutation
        finishes, preventing the race where the guard passes and then a live
        agent overwrites the tree before git runs (CORE-001).
        """
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
            return {"ok": False, "code": "WRITER_BUSY", "message": guard,
                    "updated_detail": None}
        p = Path(root)
        result = update_state(p, updates)
        if result.get("ok"):
            # PERF-001: targeted refresh instead of full rescan.
            self._refresh_one_project(root)
            return {"ok": True, "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                    "updated_detail": self.get_project_detail(root)}
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
        self._config["zoom_level"] = float(zoom)
        save_config(self._config)
        return self.get_config()

    def move_by(self, dx: int, dy: int) -> None:
        if self._window:
            self._window.move_by(dx, dy)

    def set_sort_order(self, order: str) -> dict:
        self._config["sort_order"] = order
        save_config(self._config)
        with self._lock:
            self._projects.sort(key=lambda x: _project_sort_key(x, order))
        return self.get_config()

    def set_hotkeys(self, hotkeys: list[str]) -> dict:
        hotkeys = [h.strip() for h in hotkeys if h.strip()]
        if not hotkeys or not self._on_hotkeys_changed:
            return self.get_config()
        previous = self._config["hotkeys"]
        try:
            self._on_hotkeys_changed(hotkeys)
        except (ValueError, KeyError):
            self._on_hotkeys_changed(previous)  # revert to last-known-good
            # W2-010: surface the failure as {ok:false} so the Settings runSeq
            # counts it as failed (not silently applied).
            return {"ok": False, "error": "hotkey binding failed; reverted to previous"}
        self._config["hotkeys"] = hotkeys
        save_config(self._config)
        return self.get_config()

    def set_snap_hotkey(self, hotkeys: str | list[str]) -> dict:
        if isinstance(hotkeys, str):
            hotkeys = [h.strip() for h in hotkeys.split(",") if h.strip()]
        if not hotkeys or not self._on_snap_hotkey_changed:
            return self.get_config()
        previous = self._config["snap_hotkey"]
        try:
            self._on_snap_hotkey_changed(hotkeys)
        except Exception:  # noqa: BLE001 - defensive catch for hotkey binding failure
            # Hotkey registration failed (invalid combo, keyboard lib error, etc.)
            # Try to restore previous hotkeys silently
            try:
                self._on_snap_hotkey_changed(
                    previous if isinstance(previous, list) else [previous]
                )
            except Exception as revert_err:  # noqa: BLE001 - defensive catch for hotkey rollback failure
                # Both the new binding AND the rollback failed -- the user now
                # has NO working snap hotkey, which is exactly the state that
                # must not happen quietly.
                print(
                    f"SAIPENVIEW: snap hotkey rollback to {previous!r} also failed: {revert_err}",
                    file=sys.stderr,
                )
                # W2-010: report the failure as {ok:false} so the Settings
                # runSeq does not count a dead hotkey as applied.
                return {
                    "ok": False,
                    "error": f"snap hotkey binding failed; rollback also failed: {revert_err}",
                }
            # New binding failed but rollback succeeded: still a failure.
            return {"ok": False, "error": "snap hotkey binding failed; reverted"}
        self._config["snap_hotkey"] = hotkeys
        save_config(self._config)
        return self.get_config()

    def set_scan_tuning(
        self, scan_depth: int, scan_delay_ms: int, rescan_interval: int
    ) -> dict:
        """Rebuilds the background scanner with new tuning."""
        self._config["scan_depth"] = max(1, min(8, int(scan_depth)))
        self._config["scan_delay_ms"] = max(0, int(scan_delay_ms))
        self._config["rescan_interval"] = max(10, int(rescan_interval))
        save_config(self._config)
        self._replace_background_scanner()
        return self.get_config()

    def set_scan_roots(self, roots: list[str] | None) -> list[dict]:
        self._config["scan_roots"] = roots
        save_config(self._config)
        self.background_scanner.stop()
        self._set_scanning(True)
        projects = scan(**self._scan_kwargs())
        self._set_cache(projects, force=True)
        self._replace_background_scanner()
        return self.get_projects()

    def set_exclude_dirs(self, dirs: list[str]) -> list[dict]:
        self._config["exclude_dirs"] = list(dirs)
        save_config(self._config)
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

        existing = self._config.get("scan_roots")
        if existing is None:
            # was "auto all local drives" -- make that explicit so adding a folder
            # expands the source set instead of silently replacing it
            existing = _auto_roots()
        # Keep stale roots (T-165): a root whose drive is currently missing is
        # quarantined by scan(), not forgotten here -- dropping it on every
        # browse would defeat the auto-repick-on-return invariant T-138 built.
        # dedupe() canonicalises and collapses case/slash variants.
        existing = dedupe(existing)
        if folder_str not in existing:
            existing.append(folder_str)
        self._config["scan_roots"] = existing
        save_config(self._config)

        self._set_scanning(True)
        projects = scan(**self._scan_kwargs())
        self._set_cache(projects, force=True)
        self._replace_background_scanner()

        return self.get_projects()

    def start(self) -> None:
        self._auto_scan = self._config.get("auto_scan", True)
        if self._auto_scan:
            self._set_scanning(True)
            self._scan_linked_worktrees()
            self.background_scanner.start()

    def stop(self) -> None:
        self._process_manager.stop_all()
        self.background_scanner.stop()
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
        event_bus.unsubscribe("saipen.project_changed", self._on_file_changed)

    def set_auto_scan(self, enabled: bool) -> dict:
        self._auto_scan = enabled
        self._config["auto_scan"] = enabled
        save_config(self._config)
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
        self._config["always_on_top"] = enabled
        save_config(self._config)
        if self._window:
            self._window.set_always_on_top(enabled)
        return self.get_config()

    def set_frameless(self, frameless: bool) -> dict:
        """Persist and apply the native-titlebar setting.

        Separate from toggle_frameless below because a checkbox knows the
        state it wants; a blind flip against an unknown current state is how
        the collapse button ended up ADDING a titlebar."""
        self._config["frameless"] = frameless
        save_config(self._config)
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

    def acknowledge_external_change(self, root_str: str, path: str, token: int | None = None) -> dict:
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

    def _build_ticket_index(self, root: str) -> None:
        """PERF-008: build in-memory ticket search index for one root.

        Called after project load/refresh; avoids re-reading BOARD files on
        every search query.
        """
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
            return {"ok": False, "code": "WRITER_BUSY", "message": guard,
                    "updated_detail": None}
        p = Path(root)
        result = reorder_ticket(p, ticket_id, section, before_ticket_id)
        if result.get("ok"):
            return {"ok": True, "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                    "updated_detail": self.get_project_detail(root)}
        return {
            "ok": False,
            "code": result.get("code", "VALIDATION_FAILED"),
            "message": result.get("message", "reorder refused"),
            "updated_detail": None,
        }

    def record_manual_work(
        self, root_str: str, description: str, operation_id: str | None = None
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
        # CORE-013: capture pending external changes BEFORE the transaction so
        # we can conditionally ack only the exact tokens the user saw. A newer
        # write racing after the prompt keeps its newer token pending.
        from saipenview.external_changes import get_registry
        pending_before = list(get_registry().pending(str(root)))
        result = record_manual_work(Path(root), description, operation_id)
        if result.get("ok"):
            for pc in pending_before:
                get_registry().acknowledge(str(root), pc.rel_path, pc.token)
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
            return {"ok": False, "code": "WRITER_BUSY", "message": guard,
                    "updated_detail": None}
        p = Path(root)
        result = move_ticket(p, ticket_id, action, blocker_reason=blocker_reason)
        if result.get("ok"):
            # PERF-001: targeted refresh instead of full rescan.
            self._refresh_one_project(root)
            return {"ok": True, "code": result.get("code", "COMMITTED"),
                    "message": result.get("message", ""),
                    "updated_detail": self.get_project_detail(root)}
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

        return self._process_manager.launch(engine, root, instruction)

    def stop_agent(self, root: str) -> dict:
        """Kill a running agent process."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.kill(root)

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
        return self._git_mutation_tx(
            root, commit_agent_work, message, fingerprint
        )

    def revert_agent_work(self, root: str, fingerprint: str | None = None) -> dict:
        """Restore tracked changes only; untracked files are untouched."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_live_agent(root)
        if guard:
            return guard
        return self._git_mutation_tx(
            root, revert_agent_work, fingerprint
        )

    def delete_untracked_files(self, root: str, fingerprint: str | None = None) -> dict:
        """Explicit separate operation: delete untracked files (T-162)."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        guard = self._guard_live_agent(root)
        if guard:
            return guard
        return self._git_mutation_tx(
            root, delete_untracked_files, fingerprint
        )

    def send_agent_input(self, root: str, text: str) -> dict:
        """Send text to a running agent's stdin."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.send_input(root, text)

    def get_agent_output(self, root: str, since_line: int = 0) -> dict:
        """Return new output lines since a given line number."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.get_output(root, since_line)

    def get_agent_status(self, root: str) -> dict:
        """Return status info for an agent process on a project."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return self._process_manager.get_status(root)

    def list_running_agents(self) -> list[dict]:
        """Return status dicts for all tracked agent processes."""
        return self._process_manager.list_running()

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
