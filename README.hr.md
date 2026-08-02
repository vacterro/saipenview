<!-- HR TRANSLATION STUB -->
<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Desktop tray viewer for every SAIPEN project on your machine</strong>
    <br>
    Autodiscovers <code>.saipen/</code> projects across local drives — live phase, task, blocker, git status, tickets, and sub-agents.
    <br>
    One vintage dark-golden Win95-themed dashboard.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Support Developer](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ At a Glance

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Dashboard Screenshot" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Every SAIPEN project, sub-agent, ticket, and git status — all in one view.</em>
</p>

<br>

---

## 🚀 Features

<table>
<tr>
<td width="50%">

### 🔍 Discovery
- **Auto-scan** local drives for `.saipen/` projects
- **Custom roots** — pick folders or entire drives
- **Smart excludes** — `node_modules`, `.git`, system dirs
- **Background rescan** — configurable interval (default 300s)
- **Linked worktrees** — detects git worktrees for easy setup

### 📊 Dashboard
- Live **phase**, **task**, **next action**, **blocker**
- **Git branch** + dirty-state indicator per project
- **Filter** by phase (All / Active / Done / Stuck / custom)
- **Sort** — Smart, Recent, Oldest, A–Z, Z–A
- **Search** — name/root filter + deep ticket search
- **Pin** projects to top, **hide** irrelevant ones
- **Flash highlight** — changed projects glow & fade over 20s
- **Heat coloring** — stale projects cool, fresh projects warm

</td>
<td width="50%">

### 🧩 Sub-Agents
- **Nested display** — `saiwiki`, `saihunt`, `saitranslate` indented under parent
- **Outbox counts** — ready/blocked/draft/reviewed at a glance
- **One-click collect** — fold ready entries into main project
- **Stale warning** — detects out-of-date protocol files

### 🎮 Interaction
- **File viewer** — read & edit STATE.md, BOARD.md, LOG.md
  - Source mode (editable) + Reader mode (rendered)
- **Interactive tickets** — Start / Done buttons update BOARD.md live
- **Quick actions** — contextual `npm run dev`, `cargo test`, etc.
- **Custom commands** — user-defined action buttons
- **Collapsible sections** — per-project, persisted
- **Resizable sidebar** — drag to resize

### ⌨️ Hotkeys & Window
- **Show/Hide** — `Ctrl+Alt+X` (configurable)
- **Snap corners** — `Ctrl+Q` cycles TL → TR → BL → BR
- **Zoom** — `Ctrl+MouseWheel`, `Ctrl+`+`/`-`
- **System tray** — minimize to tray, start hidden
- **Always-on-top** toggle
- **Autostart** — optional Windows startup
- **Frameless mode** — toggle titlebar off for ultra-minimal view

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Quick Start

<table>
<tr>
<th width="33%">🐍 Run from source</th>
<th width="33%">📜 Launch scripts</th>
<th width="33%">📦 Install (future)</th>
</tr>
<tr>
<td>

```bash
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m saipenview
```

</td>
<td>

| Script | Behavior |
|---|---|
| `run.vbs` | Hidden (tray-only) |
| `run.bat` | Visible (console open) |
Both auto-create `.venv` & install deps.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Coming soon ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Usage

| Action | How |
|---|---|
| **Show / Hide** | `Ctrl+Alt+X` or `Alt+F15` (both configurable) |
| **Snap corner** | `Ctrl+Q` — cycles Top-Left → Top-Right → Bottom-Left → Bottom-Right |
| **Kill switch** | `Ctrl+Shift+Alt+Q` — force-quit the process |
| **Zoom in / out** | `Ctrl+MouseWheel` or `Ctrl` + `+` / `-` |
| **Zoom reset** | `Ctrl+0` |
| **Toggle toolbar** | `Alt+D` — collapse/expand the toolbar panel |
| **Search projects** | Type in search box; tick `D` for deep ticket search |
| **Filter** | Dropdown: All / Live / Done / Stuck, or click a phase pill |
| **Sort** | Smart / Recent / Oldest / A–Z / Z–A |
| **Rescan** | Click `Rescan` or wait for background timer (default 300s) |
| **Browse folder** | Click `Browse` to add a folder to the scan set |
| **Settings** | ⚙ button opens the settings modal |
| **Help wiki** | `?` button opens the built-in mini-wiki |
| **Right-click project** | Copy root path, filter by phase, open folder |
| **Double-click section** | Opens the connected file (STATE.md, BOARD.md, LOG.md) |
| **Drag window** | Drag the title bar (or anywhere in frameless mode) |

### Modals

| Modal | What it does |
|---|---|
| **Settings** | Zoom, hotkeys, scan tuning, autostart, always-on-top, font, flash toggle, file viewer default, custom commands, locale, scan roots |
| **File Viewer** | Read & edit STATE.md, BOARD.md, LOG.md — Source (raw) or Reader (rendered) mode |
| **Help** | Comprehensive mini-wiki covering every feature, shortcut, and concept |
| **Confirm** | Vintage-styled DOM dialog (replaces native `confirm()`) |

<br>

---

## 🧬 SAIPEN Protocol

SAIPENVIEW is a companion for projects using the **SAIPEN Protocol** — a state-machine framework that guides AI agents through project work in defined phases:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                         ↓
                    HUNT / CLEAN
```

Each SAIPEN project stores its state in three canonical files:

| File | Purpose |
|---|---|
| `.saipen/STATE.md` | Machine-readable frontmatter — phase, task, next action, blocker |
| `.saipen/BOARD.md` | Ticket board — DOING / TODO / DONE / BLOCKED sections |
| `.saipen/LOG.md` | Chronological event log — every command and its outcome |

**SubSaipen agents** (`saiwiki`, `saihunt`, `saitranslate`) live in `.saipen/extensions/subs/` and communicate via `kitchen/OUTBOX.md` — the protocol's built-in cross-agent message bus. SAIPENVIEW discovers all of them and renders a unified dashboard.

### Conformance

Showing what a project *says* is only half of it. A project can read perfectly
in the list — a phase, a task, a next action — while being a state the protocol
rejects, and until you ran `tools/validate.py` by hand there was no way to tell
those two apart.

Every row carries a verdict badge, and the detail pane lists what is wrong:

| Verdict | Meaning |
|---|---|
| `OK` | Nothing found in this project's own `.saipen/` files |
| `N WARNS` | Legal, but drifting — a stale checkpoint, a non-standard LOG verb |
| `N FAILS` | A state the protocol rejects: a `WAIT:` with no category, a checkbox that disagrees with its section, a `needs:` pointing at a ticket that does not exist, a UTF-16 `STATE.md` no other SAIPEN tool can read |

Each finding names the rule, the file and line, and the clause it comes from,
so it can be looked up rather than taken on faith.

This is a **second opinion, not a replacement** for `tools/validate.py`. It
re-checks only what a project's own files can decide, and it grades against a
copy of the protocol's vocabularies — so the SAIPEN version it was read from is
printed under every verdict. The viewer is allowed to lag the protocol. It is
not allowed to lag it quietly.

> 💡 *The name "SAIPENVIEW" says it all — it provides a **view** into every **SAIPEN** project on your machine.*

<br>

---

## ⚙️ Configuration

Config is portable — stored next to the app, not `%APPDATA%`:

```
saipenview/_data/config.json
```

Key defaults:

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["alt+f14"],
  "zoom_level":       1.0,
  "font_family":      "Verdana_m1",
  "scan_roots":       null,
  "rescan_interval":  300,
  "scan_depth":       6,
  "scan_delay_ms":    10,
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "flash_changes":    true,
  "locale":           "en"
}
```

Set `scan_roots: null` to autodetect all local drives.  
Set to a list of paths (e.g. `["V:\\", "D:\\projects"]`) to limit scanning.  
All settings are also configurable through the **Settings** modal in the app.

<br>

---

## 🏗️ Architecture

```
saipenview/
├── app.py              Entry wiring — tray, hotkey, window, api
├── api.py              JS-facing pywebview bridge (30+ methods)
├── scanner.py          Drive walk + background rescan loop
├── parser.py           STATE.md / BOARD.md / LOG.md parsing
├── textio.py           One reader for every .saipen/ file — BOM, UTF-16, cp1251
├── protocol.py         The protocol's closed vocabularies + BASELINE_VERSION
├── conformance.py      Grades a project against those vocabularies
├── config.py           Settings load/save (atomic writes)
├── tray.py             pystray system-tray icon + menu
├── hotkey.py           Global hotkey registration (keyboard lib)
├── autostart.py        Windows Registry autostart management
├── zone_picker.py      Ctrl+Q corner-snap overlay (tkinter)
├── ui/
│   ├── window.py       pywebview window — show/hide/toggle/snap
│   └── static/
│       ├── index.html
│       ├── style.css   Vintage dark-golden Win95 theme
│       └── app.js      Frontend logic (~2600 lines)
├── assets/
│   └── tray_icon.png
├── screenshots/        README screenshots
└── _data/              Runtime config + cache (gitignored)
```

### Design principles

- **Single process** — no background IPC, no separate server; one Python process hosts both the WebView2 window and the scan loop in a `ThreadPoolExecutor`
- **Atomic writes** — every file write uses temp-file + `os.replace`; a crash can never truncate config or cache
- **Stale-read safe** — the 5s UI poll calls `refresh_known()` (re-reads only `.saipen/` files, no directory walk). Edits to STATE.md appear within seconds without triggering a full drive scan
- **No CSS transitions** — all visual effects (flash, heat, hover) are JavaScript-driven `hexBlend` recomputations, strictly following the vintage theme's zero-animation constraint
- **Vintage theme** — dark brown surfaces, golden text/accents, 3D beveled borders, zero anti-aliasing, Verdana_m1 font

<br>

---

## 🧪 Development

```bash
# Clone & enter
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Create venv & install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run
python -m saipenview
```

For detailed setup, coding conventions, and PR workflow, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Requirements

- **Windows 10 / 11** — WebView2 runtime (pre-installed on Win11, auto-installs on Win10)
- **Python 3.10+**
- Dependencies: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 License

MIT — see [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Built with 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95 aesthetic</sub>

<br>

---

## 📸 More Screenshots

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detail pane with tickets, sub-agents, and file viewer.</em>
</p>

<br>

</div>
