# SAIPENVIEW

**Desktop tray viewer for every SAIPEN project on your machine.**  
Autodiscovers `.saipen/` projects across local drives and shows live phase, task, blocker, git status, tickets, and sub-agents — all in one vintage dark-golden Win95-themed dashboard.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-orange)
[![PyPI](https://img.shields.io/badge/pypi-v0.1.0-blue)]()


---

## Features

- **Auto-discovery** — walks local drives (user-configurable roots) for directories containing `.saipen/STATE.md`, excludes system dirs, `node_modules`, `.git`, etc.
- **Live dashboard** — see every project's current SAIPEN phase, task, next action, blocker, and git status at a glance
- **Sub-agent rollup** — `saiwiki`, `saihunt`, `saitranslate` and any other subSaipen show indented under their parent with phase/task/outbox counts
- **Git integration** — branch name and dirty-state indicator per project
- **Built-in file viewer** — read/SAVE STATE.md, BOARD.md, and LOG.md right in the app with a smart reader mode (rendered fields, grouped tickets, parsed events)
- **Quick actions** — contextual one-click commands (`npm run dev`, `pytest`, `cargo build`, `make`) auto-detected from project type
- **Interactive tickets** — Start / Done buttons next to tickets move them between TODO/DOING/DONE on the BOARD.md
- **Linked worktree detection** — finds `.git`-as-file worktrees without `.saipen/` for easy setup
- **Flash highlight** — recently-changed projects glow and fade over 20 seconds
- **Edit-temperature heat** — stale projects show cooler color, hot projects glow warm (24h window)
- **Collapsible sections** — per-project collapse state persisted across sessions
- **Resizable sidebar** — drag to resize the project list / detail pane split
- **Window snap** — `Ctrl+Q` cycles through four corners (TL/TR/BL/BR)
- **System tray** — minimize to tray, toggle with hotkeys, start hidden
- **Global hotkeys** — two configurable bindings for show/hide, two for snap corner
- **CSS zoom** — `Ctrl+MouseWheel` or `Ctrl+/-` for instant UI scaling (75%–200%)
- **Always-on-top** toggle
- **Autostart** — optional Windows startup via `HKCU\...\Run`

## Screenshots

> *Screenshots coming soon. The UI uses a custom vintage theme with dark brown surfaces, golden accents, 3D bevels, and zero anti-aliasing.*

---

## Quick Start

### Option 1: Run from source

```bash
git clone https://github.com/vac345/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m saipenview
```

### Option 2: Launch scripts

| Script | Behavior |
|---|---|
| `run.vbs` | Launches **hidden** (no console window, tray-only) |
| `run.bat` | Launches **visible** (console window stays open) |

Both scripts auto-detect or create a `.venv`, install dependencies if missing, then start the app.

### Option 3: Install via pip (future)

```bash
pip install saipenview
saipenview
```

---

## Usage

| Action | How |
|---|---|
| **Show/hide window** | `Ctrl+Alt+X` or `Alt+F15` (both configurable) |
| **Snap to corner** | `Ctrl+Q` cycles TL → TR → BL → BR |
| **Force quit** | `Ctrl+Shift+Alt+Q` kills the process entirely |
| **Zoom** | `Ctrl+MouseWheel`, `Ctrl+`+`/`-`, `Ctrl+0` resets |
| **Toggle collapse** | `Alt+D` collapses/expands the toolbar |
| **Search** | Type in the search box; tick `D` for deep ticket search |
| **Filter** | Dropdown: All / Live / Done / Stuck, or click a phase pill |
| **Sort** | Smart / Recent / Oldest / A–Z / Z–A |
| **Rescan** | Click `Rescan` or wait for the background timer (default 300s) |
| **Browse** | Click `Browse` to add a specific folder to the scan set |
| **Settings** | Gear button ⚙ opens the settings modal |
| **Help** | `?` button opens a built-in wiki modal |
| **Right-click** project | Copy root path, filter by phase, open folder |
| **Double-click** section | Opens the connected file (STATE.md, BOARD.md, etc.) |

### Modals

- **Settings** — zoom, hotkeys, scan tuning, autostart, always-on-top, font family, flash toggle, file viewer default, custom commands, locale, root drives/folders
- **File Viewer** — Source (editable) / Reader (rendered) mode for STATE.md, BOARD.md, LOG.md
- **Help** — comprehensive mini-wiki covering every feature, shortcut, and concept
- **Confirm** — vintage-styled DOM confirmation dialog (replaces `confirm()`)

---

## SAIPEN Protocol

SAIPENVIEW is a companion app for projects using the **SAIPEN protocol** (Self-Adaptive Iterative Protocol for Enhanced Navigation) — a state-machine protocol that guides AI agents through project work in phases:

`INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE`
plus `HUNT` (bug chasing) and `CLEAN` (debt reduction).

Each SAIPEN project carries its state in `.saipen/STATE.md`, its work-in-progress in `.saipen/BOARD.md`, and its history in `.saipen/LOG.md`. SubSaipen agents live in `.saipen/extensions/subs/<name>/` and communicate via `kitchen/OUTBOX.md`.

SAIPENVIEW discovers all these files and renders them in a single, cohesive dashboard.

---

## Configuration

Portable — config lives next to the app, not `%APPDATA%`:

```
saipenview/_data/config.json
```

Key settings (defaults shown):

```json
{
  "hotkeys": ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey": ["ctrl+q", "alt+f14"],
  "zoom_level": 1.0,
  "font_family": "Verdana_m1",
  "scan_roots": null,
  "rescan_interval": 300,
  "scan_depth": 6,
  "scan_delay_ms": 10,
  "auto_scan": true,
  "show_on_launch": true,
  "always_on_top": true,
  "flash_changes": true,
  "locale": "en"
}
```

Set `scan_roots: null` to autodetect all local drives. Set to a list of paths
(e.g. `["V:\\", "D:\\projects"]`) to limit scanning. You can also configure
everything through the Settings modal in the app.

---

## Architecture

```
saipenview/
├── app.py          — Entry wiring: tray + hotkey + window + api
├── scanner.py      — Drive walk + background rescan loop
├── parser.py       — STATE.md/BOARD.md/LOG.md parsing, sub/translate rollup
├── api.py          — JS-facing pywebview bridge (30+ methods)
├── config.py       — Settings load/save (atomic writes)
├── tray.py         — pystray system-tray icon + context menu
├── hotkey.py       — Global hotkey registration (keyboard lib)
├── autostart.py    — Windows Registry autostart management
├── zone_picker.py  — Ctrl+Q corner-snap zone picker (tkinter)
├── ui/
│   ├── window.py   — pywebview window show/hide/toggle/drag/snap
│   └── static/     — Frontend assets
│       ├── index.html
│       ├── style.css  (vintage dark-golden theme)
│       └── app.js
├── assets/
│   └── tray_icon.png
└── _data/          — Runtime config + cache (gitignored)
```

### Key design decisions

- **Single process** — no background IPC, no separate server; the Python process hosts both the WebView2 window and the scan loop in one ThreadPoolExecutor
- **Atomic writes** — config and cache both use temp-file + `os.replace` so a crash can never truncate them
- **Stale-read safe** — the 5s UI poll calls `refresh_known()` (re-reads only `.saipen/` files, no directory walk), so edits to STATE.md appear within seconds without triggering a full drive scan
- **No CSS transitions** — all visual effects (flash, heat, hover) are JavaScript-driven hexBlend recomputations every tick, strictly following the vintage theme's no-animation constraint

---

## Development

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run from source
python -m saipenview

# Build wheel
python -m build --wheel

# Install from wheel
pip install dist/saipenview-*.whl
```

---

## Requirements

- **Windows** (10 / 11) — WebView2 runtime (installed by default on Win11, auto-installs on Win10)
- **Python** 3.10+
- Dependencies: `pystray`, `keyboard`, `pywebview`, `Pillow`

---

## License

MIT — see [LICENSE](LICENSE).

---

## Why "SAIPENVIEW"?

It provides a **view** into every **SAIPEN** project on your machine. SAIPEN's state-machine phases, sub-agents, and outbox protocol are all designed to make AI-assisted project work transparent — and SAIPENVIEW makes that transparency visible at a glance.
