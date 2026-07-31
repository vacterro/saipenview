"""Persisted user settings: hotkeys, font size, scan roots, rescan interval.
Portable — config lives next to the app, not in %%APPDATA%%."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

DEFAULTS = {
    "hotkeys": ["ctrl+alt+x", "alt+f15", "ctrl+q"],
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
    # Two slots per hotkey, same as "hotkeys" above. alt+f14 mirrors the
    # existing alt+f15 convention -- F13..F24 don't exist on normal keyboards,
    # so they're collision-free targets for a remapper/macro key.
    "snap_hotkey": ["alt+f14"],
    "collapse_hint_acknowledged": False,
    "collapsed_sections": {},
    "show_on_launch": True,  # False = start hidden in tray (old default)
    "always_on_top": True,  # matches the previously-hardcoded window.py behavior
    "flash_changes": True,
    # UI font (T-076). Verdana_m1 is the user's no-anti-aliasing Verdana
    # variant; the fallbacks below are appended at runtime so a machine
    # without it still renders in the same family.
    "font_family": "Verdana_m1",
    "custom_commands": [],  # [{label: string, command: string}, ...]
    "locale": "en",  # UI language: en | zh-CN
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
    return cfg


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
