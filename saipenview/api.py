"""JS-facing API exposed to the pywebview window as `pywebview.api`."""

# Agent engine layer (Wave 1)

from __future__ import annotations

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
    if not isinstance(overrides, dict):
        return None, "engine_overrides entry must be an object"
    path = overrides.get("path")
    extra = overrides.get("extra_args") or []
    env = overrides.get("env") or {}
    if path is not None and not isinstance(path, str):
        return None, "engine override 'path' must be a string"
    if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
        return None, "engine override 'extra_args' must be a list of strings"
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        return None, "engine override 'env' must be a dict of str -> str"
    return _EngineWithOverrides(engine, path, extra, env), None


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

    def __init__(self, on_hotkeys_changed=None, window=None):
        self._window = window
        self._lock = threading.Lock()
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
                    self._projects = json.load(f)
                self._projects = [
                    p for p in self._projects if not _is_garbage_root(Path(p["root"]))
                ]
                self._has_scanned = True
            except Exception as e:
                print(
                    f"SAIPENVIEW: cache at {self._cache_file} unreadable ({e}), starting fresh",
                    file=sys.stderr,
                )

        self._linked_worktrees: list[dict] = []
        self._process_manager = ProcessManager(
            buffer_size=self._config.get("agent_output_buffer_size", 5000)
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

        event_bus.subscribe("saipen.state_changed", self._on_file_changed)
        event_bus.subscribe("saipen.board_changed", self._on_file_changed)
        event_bus.subscribe("saipen.log_appended", self._on_file_changed)

    def _on_file_changed(self, data: dict) -> None:
        root = data["root"]
        file = data["file"]
        self.refresh_known()
        if self._window:
            try:
                self._window.evaluate_js(
                    f"if (window.onSaipenFileChanged) window.onSaipenFileChanged('{root}', '{file}')"
                )
            except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
                print(f"SAIPENVIEW: js push failed: {e}", file=sys.stderr)

    def _set_scanning(self, val: bool) -> None:
        with self._lock:
            self._scanning = val

    def _sort_order(self) -> str:
        return self._config.get("sort_order", "smart")

    def _set_cache(self, projects: list[ProjectStatus], force: bool = False) -> None:
        pinned_set = set(self._config.get("pinned_roots") or [])
        hidden_set = set(self._config.get("hidden_roots") or [])
        with self._lock:
            if not force and not projects and self._has_scanned and self._projects:
                self._scanning = False
                return
            items = [
                _project_to_dict(p, pinned_set)
                for p in projects
                if str(p.root) not in hidden_set and not _is_garbage_root(p.root)
            ]
            items.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
            self._projects = items
            self._has_scanned = True
            self._scanning = False
        # Refresh linked worktrees after every scan result — catches all
        # three paths: manual rescan, BackgroundScanner._loop, and browse.
        self._scan_linked_worktrees()
        # Atomic write (temp + replace) via the shared helper -- a crash mid
        # plain write left truncated JSON that __init__'s json.load choked on.
        self._write_cache()

    def get_projects(self) -> list[dict]:
        hidden_set = set(self._config.get("hidden_roots") or [])
        with self._lock:
            return [p for p in self._projects if p["root"] not in hidden_set]

    def refresh_known(self) -> list[dict]:
        """Re-read the .saipen/ files of roots we ALREADY know about.

        This is the cheap half of scanning: no directory walk, no drive sweep,
        just a re-parse of each known project's own small files. The expensive
        discovery sweep stays on its slow timer (rescan_interval) and is what
        finds NEW projects; this runs on the UI poll so an edit to a STATE.md
        shows up within seconds instead of up to rescan_interval later.

        Fixes both T-071 (list wasn't live) and T-072 (the sidebar served this
        stale cache while the detail pane did a live read, so the same project
        could show two different `updated` values at once).
        """
        with self._lock:
            roots = [p["root"] for p in self._projects]
        if not roots:
            return self.get_projects()

        pinned_set = set(self._config.get("pinned_roots") or [])
        hidden_set = set(self._config.get("hidden_roots") or [])
        fresh: list[dict] = []
        for root in roots:
            if root in hidden_set:
                continue
            with self._lock:
                prev = next((p for p in self._projects if p["root"] == root), None)
            try:
                # with_git=False: the git lookup is ~97% of load_project's cost
                # (two subprocesses). Git state can't change from a STATE.md
                # edit, so carry the previous values and let the slow full scan
                # refresh them.
                proj = load_project(Path(root), with_git=False)
            except (OSError, subprocess.SubprocessError) as e:
                # One unreadable project must not stop the refresh (same rule
                # _scan_one_root follows). Keep the last-known row instead.
                print(f"SAIPENVIEW: refresh_known({root}) failed: {e}", file=sys.stderr)
                proj = None
            if proj is None:
                if prev:
                    fresh.append(prev)
                continue
            row = _project_to_dict(proj, pinned_set)
            if prev:
                row["git_branch"] = prev.get("git_branch", "")
                row["git_dirty"] = prev.get("git_dirty", False)
            fresh.append(row)

        fresh.sort(key=lambda x: _project_sort_key(x, self._sort_order()))
        with self._lock:
            changed = fresh != self._projects
            self._projects = fresh
        # Persist so the next cold start doesn't fast-boot into stale rows.
        # _set_cache writes cache.json but only the slow full scan calls it, so
        # without this an edit made between scans was visible live yet lost on
        # restart. Written only when something ACTUALLY changed -- this runs on
        # the 5s poll and must not turn into a disk write every 5 seconds.
        if changed:
            self._write_cache()
        return self.get_projects()

    def _write_cache(self) -> None:
        try:
            tmp_path = self._cache_file.with_name(self._cache_file.name + ".tmp")
            with self._lock:
                snapshot = list(self._projects)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f)
            os.replace(tmp_path, self._cache_file)
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
        ):
            if k in settings:
                self._config[k] = settings[k]
        save_config(self._config)
        return self.get_config()

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
            return list(self._projects)

    def hide_project(self, root_str: str) -> list[dict]:
        hidden = list(self._config.get("hidden_roots") or [])
        if root_str not in hidden:
            hidden.append(root_str)
        self._config["hidden_roots"] = hidden
        save_config(self._config)
        with self._lock:
            self._projects = [p for p in self._projects if p["root"] != root_str]
            return list(self._projects)

    def unhide_project(self, root_str: str) -> list[dict]:
        hidden = list(self._config.get("hidden_roots") or [])
        if root_str in hidden:
            hidden.remove(root_str)
        self._config["hidden_roots"] = hidden
        save_config(self._config)
        return self.get_projects()

    def get_hidden_projects(self) -> list[dict]:
        hidden_set = set(self._config.get("hidden_roots") or [])
        if not hidden_set:
            return []
        pinned_set = set(self._config.get("pinned_roots") or [])
        raw = scan(
            list(hidden_set),
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
        )
        return [_project_to_dict(p, pinned_set) for p in raw]

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

    def read_file_text(self, file_path: str) -> str | None:
        ok, reason = validate_file_path(file_path, self._known_roots())
        if not ok:
            print(
                f"SAIPENVIEW: read_file_text rejected {file_path!r}: {reason}",
                file=sys.stderr,
            )
            return None
        try:
            if os.path.exists(file_path):
                # read_doc, not open(encoding="utf-8"): the file viewer opened
                # a UTF-16 STATE.md as an error toast and a BOM-carrying one
                # with a stray glyph on line 1.
                return read_doc(file_path)
        except OSError as e:
            print(
                f"SAIPENVIEW: read_file_text({file_path}) failed: {e}", file=sys.stderr
            )
        return None

    def write_file_text(self, file_path: str, content: str) -> bool:
        ok, reason = validate_file_path(file_path, self._known_roots())
        if not ok:
            print(
                f"SAIPENVIEW: write_file_text rejected {file_path!r}: {reason}",
                file=sys.stderr,
            )
            return False
        try:
            path = Path(file_path)
            # Normalise line endings so write_doc re-applies exactly one
            # convention: a CRLF file whose editor content already carries
            # \r\n would otherwise get doubled \r\r\n.
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            if path.is_file():
                # Preserve the original encoding and newline so saving one
                # field never re-encodes a UTF-16/BOM/CRLF file (T-164). New
                # files default to UTF-8 LF.
                _, enc, newline = read_doc_meta(path)
                write_doc(path, content, enc, newline)
            else:
                write_doc(path, content)
            return True
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
        d["todo_tickets"] = [
            {"id": t.ticket_id, "desc": t.description} for t in proj.board.todo
        ]
        d["blocked_tickets"] = [
            {"id": t.ticket_id, "desc": t.description} for t in proj.board.blocked
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
        p = Path(root)
        if update_state(p, updates):
            # force cache update
            self.rescan()
            return self.get_project_detail(root)
        return None

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
            return self.get_config()
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
            return self.get_config()
        self._config["snap_hotkey"] = hotkeys
        save_config(self._config)
        return self.get_config()

    def set_scan_tuning(
        self, scan_depth: int, scan_delay_ms: int, rescan_interval: int
    ) -> dict:
        """Rebuilds the background scanner with new tuning; does NOT force an immediate
        full scan -- unlike set_scan_roots, these are background-timing knobs, not a
        visible change the user expects reflected instantly. Applies from the next
        scheduled rescan or manual 'Rescan now'."""
        self._config["scan_depth"] = max(1, min(8, int(scan_depth)))
        self._config["scan_delay_ms"] = max(0, int(scan_delay_ms))
        self._config["rescan_interval"] = max(10, int(rescan_interval))
        save_config(self._config)
        self.background_scanner.stop()
        self.background_scanner = BackgroundScanner(
            on_result=self._set_cache,
            scan_roots=self._config["scan_roots"],
            interval_seconds=self._config["rescan_interval"],
            max_depth=self._config["scan_depth"],
            delay=self._config["scan_delay_ms"] / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
            on_scan_start=lambda: self._set_scanning(True),
        )
        if self._auto_scan:
            self.background_scanner.start()
        return self.get_config()

    def set_scan_roots(self, roots: list[str] | None) -> list[dict]:
        self._config["scan_roots"] = roots
        save_config(self._config)
        self.background_scanner.stop()
        self._set_scanning(True)
        projects = scan(roots)
        self._set_cache(projects, force=True)
        self.background_scanner = BackgroundScanner(
            on_result=self._set_cache,
            scan_roots=roots,
            interval_seconds=self._config["rescan_interval"],
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
            on_scan_start=lambda: self._set_scanning(True),
        )
        self.background_scanner.start()
        return self.get_projects()

    def set_exclude_dirs(self, dirs: list[str]) -> list[dict]:
        self._config["exclude_dirs"] = list(dirs)
        save_config(self._config)
        return self.rescan()

    def clipboard_copy(self, text: str) -> bool:
        """Copy text to system clipboard via PowerShell (works in pywebview
        where navigator.clipboard is unavailable due to WebView2 secure-context
        requirement). PowerShell escapes double-quotes inside double-quoted
        strings by doubling them: "" -> literal "."""
        try:
            cmd = f'Set-Clipboard -Value "{text.replace(chr(34), chr(34) + chr(34))}"'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True)
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
        projects = scan(
            existing,
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
        )
        # _set_cache owns the linked-worktree scan (T-165); the explicit call
        # removed here used to run the same walk a second time per browse.
        self._set_cache(projects, force=True)

        self.background_scanner.stop()
        self.background_scanner = BackgroundScanner(
            on_result=self._set_cache,
            scan_roots=existing,
            interval_seconds=self._config["rescan_interval"],
            max_depth=self._config.get("scan_depth", 6),
            delay=self._config.get("scan_delay_ms", 10) / 1000.0,
            extra_excludes=set(self._config.get("exclude_dirs", [])),
            on_scan_start=lambda: self._set_scanning(True),
        )
        self.background_scanner.start()

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
        p = Path(root)
        result = collect_outbox_entry(p, sub_name, entry_id)
        if result.get("ok"):
            # Refresh cache so the UI shows updated state
            self.rescan()
            result["updated_detail"] = self.get_project_detail(root)
        return result

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

            # Search main BOARD.md for matching tickets
            board_path = Path(root) / ".saipen" / "BOARD.md"
            matched_tickets = self._search_board_for_tickets(board_path, q)

            # Search each sub-agent's BOARD.md
            for sub in p.get("subs") or []:
                sub_path = sub.get("path", "")
                if sub_path:
                    sub_board = Path(sub_path) / "BOARD.md"
                    sub_matches = self._search_board_for_tickets(sub_board, q)
                    for mt in sub_matches:
                        mt["sub_name"] = sub.get("name", "?")
                        sub_matched_tickets.append(mt)

            # Also search translate sub if present
            translate = p.get("translate")
            if translate and translate.get("path"):
                t_board = Path(translate["path"]) / "BOARD.md"
                t_matches = self._search_board_for_tickets(t_board, q)
                for mt in t_matches:
                    mt["sub_name"] = translate.get("name", "saitranslate")
                    sub_matched_tickets.append(mt)

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

    def toggle_ticket_status(
        self, root_str: str, ticket_id: str, action: str
    ) -> dict | None:
        """Move a ticket between sections on BOARD.md: start (TODO->DOING),
        done (DOING->DONE), reopen (DONE->TODO). Returns updated project detail
        or None on failure."""
        from saipenview.parser import move_ticket

        root = self._resolve_root(root_str)
        if not root:
            return None
        p = Path(root)
        if move_ticket(p, ticket_id, action):
            self.rescan()
            return self.get_project_detail(root)
        return None

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
        state_md = Path(root) / ".saipen" / "STATE.md"
        if not state_md.exists():
            return {"ok": False, "error": "STATE.md not found"}
        flat = " ".join(str(note).split())
        if not flat:
            return {"ok": False, "error": "note is empty"}
        try:
            if not update_state(Path(root), {"human_note": flat}):
                return {"ok": False, "error": "STATE.md has no frontmatter block"}
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
        return commit_agent_work(root, message, fingerprint)

    def revert_agent_work(self, root: str, fingerprint: str | None = None) -> dict:
        """Restore tracked changes only; untracked files are untouched."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return revert_agent_work(root, fingerprint)

    def delete_untracked_files(self, root: str, fingerprint: str | None = None) -> dict:
        """Explicit separate operation: delete untracked files (T-162)."""
        root = self._resolve_root(root)
        if not root:
            return {"ok": False, "error": "unknown or unverified project root"}
        return delete_untracked_files(root, fingerprint)

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
