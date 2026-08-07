"""Persisted user settings: hotkeys, font size, scan roots, rescan interval.
Portable — config lives next to the app, not in %%APPDATA%%."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from saipenview.paths import canonical, dedupe

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
    # a second binding. ctrl+q is the user's requested snap default (T-180),
    # deliberately reverting the 4d291a0 decision that freed it because a
    # GLOBAL binding hijacks the combo in every app and ctrl+q is a ubiquitous
    # quit accelerator -- the user accepts that tradeoff.
    "snap_hotkey": ["ctrl+q"],
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
    # Colour palette (T-157). The value is a slug from saipenview/assets/themes;
    # "goldendefault" reproduces style.css's own :root token for token, so the
    # default config renders exactly what the app rendered before themes
    # existed. An unknown slug falls back to that default rather than failing --
    # see themes.resolve().
    "theme": "goldendefault",
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
    # Path canonicalization (T-138 layer 1): every persisted path is stored
    # once, in canonical form, so a comparison later never has to wonder about
    # slash/case/duplication drift. scan_roots=None (auto mode) stays None, and
    # an explicit empty list (scan nothing) must NOT become None -- the two are
    # different answers, and None would silently re-enable auto-scan.
    if isinstance(cfg.get("scan_roots"), list):
        cfg["scan_roots"] = dedupe(cfg["scan_roots"])
    for key in ("pinned_roots", "hidden_roots"):
        cfg[key] = dedupe(cfg.get(key))
    if cfg.get("selected_root"):
        cfg["selected_root"] = canonical(cfg["selected_root"])
    return cfg


_save_lock = threading.Lock()


def save_config(cfg: dict) -> None:
    with _save_lock:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
        # Canonicalize path fields on save too, so a hand-edited config or a
        # browser-typed path that slipped past a setter is cleaned on write.
        # An explicit empty scan_roots list stays an empty list (scan nothing);
        # None stays None (auto).
        if isinstance(merged.get("scan_roots"), list):
            merged["scan_roots"] = dedupe(merged["scan_roots"])
        for key in ("pinned_roots", "hidden_roots"):
            merged[key] = dedupe(merged.get(key))
        if merged.get("selected_root"):
            merged["selected_root"] = canonical(merged["selected_root"])
        # Atomic write (temp + replace) -- a crash/kill mid plain write leaves
        # truncated JSON, and load_config()'s JSONDecodeError fallback would
        # then silently reset every user preference to DEFAULTS.
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
