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
    # Agent Control dock in the detail pane. Hidden by default (ALEKS does
    # not use it; toggleable from Settings).
    "show_agent_panel": False,
    # Default collapse state for project rows (sub-rows / task / blocker all
    # hidden). Last `projects_unfolded_tail` projects are always unfolded so a
    # wide sidebar does not dead-end the user.
    "projects_collapsed_by_default": True,
    "projects_unfolded_tail": 5,
    # Per-project user overrides {root: true if collapsed}. Absent root = use
    # the default rule.
    "collapsed_projects": {},
}


# Test/embedding override hook. When set, config_path() returns it instead of
# the default on-disk location. Consulted at CALL time, so it is robust to
# modules that import config_path lazily or during object construction (a plain
# monkeypatch of the bound name leaks across tests because those modules capture
# the patched value at import time and are never re-patched).
_CONFIG_PATH_OVERRIDE: Path | None = None


def config_path() -> Path:
    if _CONFIG_PATH_OVERRIDE is not None:
        return _CONFIG_PATH_OVERRIDE
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "saipenview" / "_data" / "config.json"


def normalize_config(raw: dict) -> dict:
    """One pure normalization step: require a dict, validate each known key's
    type/range/closed-enum/list shape, preserve unrelated valid keys and
    default only invalid ones. Returns the cleaned config without side effects.
    """
    if not isinstance(raw, dict):
        return dict(DEFAULTS)
    cfg = {}
    # --- Integer / range-validated keys ---
    _int_keys = {
        "rescan_interval": (10, 9999, 300),
        "scan_depth": (1, 8, 6),
        "scan_delay_ms": (0, 60000, 10),
        "window_width": (100, 10000, 720),
        "window_height": (100, 10000, 450),
        "sidebar_width": (80, 1000, 160),
        "agent_output_buffer_size": (100, 100000, 5000),
    }
    for key, (lo, hi, default) in _int_keys.items():
        v = raw.get(key)
        try:
            v = int(v)
            if v < lo:
                v = default
            elif v > hi:
                # Canonical cap on the high side (e.g. scan_depth max 8).
                # A value that is simply too large is clamped; a value that is
                # negative / nonsensical is reset to the default instead.
                v = hi
        except (TypeError, ValueError):
            v = default
        cfg[key] = v
    # --- Float keys ---
    v = raw.get("zoom_level")
    try:
        v = float(v)
        if not (0.25 <= v <= 4.0):
            v = 1.0
    except (TypeError, ValueError):
        v = 1.0
    cfg["zoom_level"] = v
    # --- Optional int-or-None keys ---
    for key in ("window_x", "window_y"):
        v = raw.get(key)
        if v is None:
            cfg[key] = None
        else:
            try:
                cfg[key] = int(v)
            except (TypeError, ValueError):
                cfg[key] = None
    # --- String keys (closed enum) ---
    _str_keys = {
        "filter_phase": ("ALL", "ACTIVE", "DONE", "BLOCKED"),
        "sort_order": ("smart", "name_asc", "name_desc", "recent", "oldest"),
        "file_viewer_default": ("source", "reader"),
    }
    for key, allowed in _str_keys.items():
        v = raw.get(key)
        cfg[key] = v if isinstance(v, str) and v in allowed else DEFAULTS[key]
    # --- Plain string keys ---
    for key in ("font_family", "theme", "locale", "selected_root", "default_engine"):
        v = raw.get(key)
        cfg[key] = v if isinstance(v, str) else DEFAULTS[key]
    # --- Search query (freeform string) ---
    cfg["search_query"] = (
        raw.get("search_query", DEFAULTS["search_query"])
        if isinstance(raw.get("search_query"), str) else DEFAULTS["search_query"]
    )
    # --- Boolean keys ---
    for key in (
        "auto_scan", "compact_mode", "show_hidden", "always_on_top",
        "frameless", "flash_changes", "show_on_launch",
        "collapse_hint_acknowledged", "layout_swap", "top_panel_collapsed",
        "show_agent_panel", "projects_collapsed_by_default",
    ):
        v = raw.get(key)
        if isinstance(v, bool):
            cfg[key] = v
        elif isinstance(v, str):
            cfg[key] = v.lower() in ("true", "1", "yes")
        elif isinstance(v, (int, float)):
            cfg[key] = bool(v)
        else:
            cfg[key] = DEFAULTS[key]
    # --- tail-count for default-unfolded ---
    v = raw.get("projects_unfolded_tail")
    try:
        v = int(v)
        if v < 0: v = 0
        elif v > 50: v = 50
    except (TypeError, ValueError):
        v = DEFAULTS["projects_unfolded_tail"]
    cfg["projects_unfolded_tail"] = v
    # --- scan_roots (None or list) ---
    v = raw.get("scan_roots")
    if v is None:
        cfg["scan_roots"] = None
    elif isinstance(v, list) and all(isinstance(x, str) for x in v):
        cfg["scan_roots"] = v
    else:
        cfg["scan_roots"] = DEFAULTS["scan_roots"]
    # --- List keys ---
    for key in ("hotkeys", "snap_hotkey", "exclude_dirs", "pinned_roots", "hidden_roots"):
        v = raw.get(key)
        if key == "snap_hotkey" and isinstance(v, str):
            v = [v]
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            cfg[key] = v
        else:
            cfg[key] = list(DEFAULTS[key]) if isinstance(DEFAULTS[key], list) else DEFAULTS[key]
    # --- Complex / dict keys ---
    v = raw.get("collapsed_sections")
    cfg["collapsed_sections"] = v if isinstance(v, dict) else {}
    v = raw.get("engine_overrides")
    cfg["engine_overrides"] = v if isinstance(v, dict) else {}
    # T-179: {root: bool} map. Untrusted roots are dropped silently to keep a
    # renamed/removed project from haunting every future render.
    v = raw.get("collapsed_projects")
    if isinstance(v, dict):
        cfg["collapsed_projects"] = {
            str(k): bool(val) for k, val in v.items() if isinstance(k, str)
        }
    else:
        cfg["collapsed_projects"] = {}
    # custom_commands: list of {label, command} dicts
    v = raw.get("custom_commands")
    if isinstance(v, list) and all(
        isinstance(c, dict) and isinstance(c.get("label"), str) and isinstance(c.get("command"), str)
        for c in v
    ):
        cfg["custom_commands"] = v
    else:
        cfg["custom_commands"] = []
    # Canonical normalizer: unknown keys are NOT preserved. load_config and
    # save_config already strip to known keys on disk; normalizing inline keeps
    # the in-memory config free of stray keys that could mask typos.
    return cfg


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
        if isinstance(stored, dict):
            cfg.update({k: v for k, v in stored.items() if k in DEFAULTS})
    # Normalize all known keys with type/range/closed-enum validation
    cfg = normalize_config(cfg)
    # Path canonicalization (T-138 layer 1): every persisted path is stored
    # once, in canonical form, so a comparison later never has to wonder about
    # slash/case/duplication drift.
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
        # Normalize before saving: every setter -> candidate -> normalize ->
        # persist ensures the disk file is always valid (CORE-012).
        # Strip unknown keys so the persisted file only carries known config.
        known = {k: v for k, v in cfg.items() if k in DEFAULTS}
        merged = normalize_config(known)
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
