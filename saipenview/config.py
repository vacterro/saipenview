"""Persisted user settings: hotkeys, font size, scan roots, rescan interval.
Portable — config lives next to the app, not in %%APPDATA%%."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

DEFAULTS = {
    # Exactly two slots, matching FastPrompter's binding pair. ctrl+q used to
    # sit here as a third: a global hotkey hijacks the combo in EVERY app, and
    # ctrl+q is a ubiquitous quit accelerator, so it fired the toggle from
    # unrelated windows. Two bindings is also what README documents.
    "hotkeys": ["ctrl+alt+x", "alt+f15"],
    "zoom_level": 1.0,
    "scan_roots": None,  # None = autodetect local drives (excluding system drive)
    "rescan_interval": 300,
    "scan_depth": 6,
    "scan_delay_ms": 10,
    "exclude_dirs": [],
    "auto_scan": True,
    "window_width": 720,
    "window_height": 450,
    "window_x": None,
    "window_y": None,
    "filter_phase": "ALL",  # ALL | ACTIVE | DONE | BLOCKED
    "compact_mode": False,
    "pinned_roots": [],
    "hidden_roots": [],
    "selected_root": None,
    "search_query": "",
    "sort_order": "smart",
    "sidebar_width": 160,
    "show_hidden": False,
    # Same two-slot shape as "hotkeys" above; both are lists so either can hold
    # a second binding. alt+f14 mirrors the alt+f15 convention -- F13..F24
    # don't exist on normal keyboards, so they're collision-free targets for a
    # remapper/macro key. Only ONE default here on purpose: snap-corner is a
    # secondary action and there is no second combo that is safe to claim
    # globally without guessing at what the user already uses.
    "snap_hotkey": ["alt+f14"],
    "collapse_hint_acknowledged": False,
    "collapsed_sections": {},
    "show_on_launch": True,  # False = start hidden in tray (old default)
    "always_on_top": True,  # matches the previously-hardcoded window.py behavior
    # No native titlebar by default: the toolbar already carries minimize,
    # maximize, close-to-tray and Exit, so a titlebar is a second, worse copy
    # of controls that already exist. Dragging is unaffected -- app.js moves
    # the window from anywhere in the body. Set False to get Windows' own
    # titlebar back.
    "frameless": True,
    "flash_changes": True,
    # UI font (T-076). Verdana_m1 is the user's no-anti-aliasing Verdana
    # variant; the fallbacks below are appended at runtime so a machine
    # without it still renders in the same family.
    "font_family": "Verdana_m1",
    "custom_commands": [],  # [{label: string, command: string}, ...]
    "locale": "en",  # UI language: en | 33 more (see api.get_locales)
    "layout_swap": False,  # Swap sidebar/detail pane position
    "top_panel_collapsed": False,  # Toolbar collapsed state
    "file_viewer_default": "source",  # Default file viewer mode: source | reader
    # Agent engine layer (Wave 1)
    "default_engine": "claude-code",  # preferred engine name
    "engine_overrides": {},  # per-engine config: {"claude-code": {"path": "..."}}
    "agent_output_buffer_size": 5000,  # max lines in rolling output deque
}


def config_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "saipenview" / "_data" / "config.json"


def load_config() -> dict:
    path = config_path()
    cfg = dict(DEFAULTS)
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"SAIPENVIEW: config at {path} unreadable ({e}), using defaults",
                file=sys.stderr,
            )
            stored = {}
        cfg.update({k: v for k, v in stored.items() if k in DEFAULTS})
    # Migration: snap_hotkey was a string before v2, now a list
    if isinstance(cfg.get("snap_hotkey"), str):
        cfg["snap_hotkey"] = [cfg["snap_hotkey"]]
    # Migration: ctrl+q was freed in 4d291a0 and dropped from both DEFAULTS
    # lists for the reason spelled out above "hotkeys" -- a GLOBAL binding
    # hijacks the combo in every application, and ctrl+q is a ubiquitous quit
    # accelerator. Only the defaults were cleaned then; every config.json
    # already on disk kept shipping it under snap_hotkey, so the corner-snap
    # kept firing from unrelated windows. Strip it on load, and never leave a
    # slot empty -- a hotkey list with nothing in it registers nothing.
    snap = cfg.get("snap_hotkey")
    if isinstance(snap, list) and any(_is_ctrl_q(k) for k in snap):
        cfg["snap_hotkey"] = [k for k in snap if not _is_ctrl_q(k)] or list(
            DEFAULTS["snap_hotkey"]
        )
    return cfg


def _is_ctrl_q(combo: object) -> bool:
    """`ctrl+q` in any of the spellings the settings field accepts."""
    return isinstance(combo, str) and combo.replace(" ", "").lower() == "ctrl+q"


_save_lock = threading.Lock()


def save_config(cfg: dict) -> None:
    with _save_lock:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
        # Atomic write (temp + replace) -- a crash/kill mid plain write leaves
        # truncated JSON, and load_config()'s JSONDecodeError fallback would
        # then silently reset every user preference to DEFAULTS.
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
