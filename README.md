<p align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Local Windows control center for SAIPEN projects.</strong><br>
    Auto-discovers every <code>.saipen/</code> workspace on your drives, inspects live
    state and conformance, manages tickets and files, and launches supported AI
    coding agents from one portable desktop interface.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</p>

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW dashboard" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
</p>

---

## Why SAIPENVIEW

SAIPEN deliberately keeps project state in plain files — `.saipen/STATE.md`,
`.saipen/BOARD.md`, `.saipen/LOG.md` — so any agent can resume a project with
one command and no chat history. That design is the point of the protocol, but
the moment you run several SAIPEN projects (and their sub-agents), working with
them means opening each file by hand and re-running validation to learn what is
actually healthy and what is drifting.

SAIPENVIEW turns that file-backed state into one live local workspace:

- **Every project in one view** — automatically discovered `.saipen/` workspaces across your drives, with live phase, task, next action, blocker, git branch and dirty state.
- **Conformance at a glance** — a project can read perfectly and still violate the protocol; each row carries a version-aware verdict so that fails first, not last.
- **Interaction, not just inspection** — tickets, files, human notes, manual-work records and sub-agent outbox collection are one click away.
- **Optional agent launching** — supported AI CLIs (Claude Code, Codex, Aider, Gemini, OpenCode and more) can be started, monitored and stopped per project.
- **A companion, not the authority** — SAIPENVIEW reports what a project's own files say and grades them against a pinned copy of the protocol; the canonical SAIPEN tooling always wins disagreements.

## At a glance

| | |
|---|---|
| **Discovery** | automatic `.saipen/` scanning (custom roots, excludes, linked git worktrees) + filesystem watching + background rescans |
| **Live state** | phase, task, next action, blocker, git branch/dirty, tickets, sub-agents, run history |
| **Conformance** | version-aware verdicts per project, with rule, file/line and clause citations |
| **Interaction** | BOARD ticket moves, STATE edits, file viewer, human notes, manual-work records, outbox collection |
| **Sub-agents** | nested display, OUTBOX counts, stale-protocol warnings, one-click collect |
| **Agent engines** | launch / monitor / stop supported AI CLIs with buffered output and persisted transcripts |
| **Portable Windows app** | tray workflow, global hotkeys, no install beyond Python + WebView2 |

---

## Quick Start

From source — this works today:

```bat
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m saipenview
```

Or use the bundled launch scripts — both auto-create `.venv` and install dependencies:

| Script | Behavior |
|---|---|
| `run.vbs` | Hidden (tray-only), silent |
| `run.bat` | Tray-only launch; console visible only during one-time venv/deps bootstrap |

> **Not published to PyPI yet.** `pip install saipenview` is planned, not live —
> the package is not published, so that command will not install anything.
> Current releases are git tags on this repository; the supported install path
> is from source above.

### Requirements

- **Windows 10 / 11** — WebView2 runtime (pre-installed on Windows 11; on
  Windows 10 it is present on systems with a current Microsoft Edge)
- **Python 3.10+**
- Dependencies: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

---

## Engineering evidence

What is under the UI, each claim pointed at its artifact:

- **Python desktop application** on pywebview/WebView2 with a pystray tray icon and global hotkeys — `saipenview/app.py`, `ui/window.py`, `tray.py`, `hotkey.py`.
- **Drive/project discovery** — parallel per-root scans (`scanner.py`), a background rescan loop (default every 300s), linked-git-worktree detection, and a watchdog watcher on each project's `.saipen/` directory (`watcher.py`) that targeted-refreshes only the changed project.
- **Cheap live updates** — the 5s UI poll calls `refresh_known()`, which re-reads only known projects' `.saipen/` files (no directory walk); git state is carried forward because it cannot change from a STATE.md edit.
- **Encoding-normalized text I/O** — `textio.py` sniffs BOMs, detects BOM-less UTF-16, and falls back utf-8 → cp1251 before decoding lossily; `write_doc` preserves the original encoding and newline convention of a `.saipen/` file while writing atomically.
- **Version-aware conformance layer** — `conformance.py` grades each project against the closed vocabularies copied into `protocol.py`; every verdict prints the `BASELINE_VERSION` it was read against, and `tests/test_protocol_sync.py` re-compares those vocabularies against a reachable canonical SAIPEN repo.
- **Atomic writes** — config, cache and protocol-file writes all use temp-file + `os.replace`, so a crash mid-write leaves the previous file intact rather than exposing a truncated one (`config.py`, `textio.write_doc`).
- **Coordinated protocol mutations** — `protocol_write.py` is the one write coordinator for every `.saipen/` mutation: per-root lock, optimistic fingerprint/CAS (an external change between read and commit is a controlled conflict, never a lost update), and the only E-/T- id allocators in the codebase. Direct mutation is refused while a launched agent owns the project.
- **Path canonicalization + root-boundary checks** — `paths.py` stores one canonical spelling (absolute, case-normalised, symlink-resolved) and the file viewer/editor rejects any path that escapes a verified project root or carries a non-allowed extension, fail-closed.
- **Multi-engine subprocess management** — `runtime.py` + `engines/` manage launch, output capture (rolling 5000-line buffer), stdin gating per engine capability, kill/stop-all, and per-run transcripts persisted across restarts (`sessions.py`).
- **Single-instance guard** — `guard.py` holds a loopback socket; a second launch sends a `SHOW` request over it so the existing window comes to front instead of a second instance starting.
- **Git integration** — `git_diff.py` previews a working tree with a mutation-scope fingerprint; Commit stages exactly the previewed scope, Revert restores tracked changes only, and deleting untracked files is a separate explicit operation.
- **Tests + lint** — ~50 test modules covering conformance, the write coordinator, path boundary, encoding, git scope, engines, scanner, watcher, guard and UI; CI (`.github/workflows/ci.yml`) runs pytest on Windows (Python 3.10/3.11/3.12) plus `compileall`; Ruff is pinned and configured with bugbear/bandit/flake8/import rules (`pyproject.toml`).

---

## Safety boundaries

SAIPENVIEW can edit files and launch commands, so the boundaries are stated
plainly — each one matches implemented behavior:

- **File viewer/editor** opens only `.md`/`.json` files inside a *verified* project root (a directory holding `.saipen/STATE.md`). A scan root such as a whole drive is discovery scope, never file-access scope; paths that escape every root are rejected on the Python side, fail-closed.
- **Stored paths** (`scan_roots`, `pinned_roots`, `hidden_roots`, `selected_root`) are canonicalized before any comparison, so slash/case/symlink variants never compare as two different paths.
- **Missing roots are quarantined, not dropped** — they stay in the list and are reported in the scan error log, so when the drive returns the next scan picks them up again.
- **`engine_overrides`** are shape-validated (`path` string, `extra_args` list of strings, `env` dict of strings) before a launch or a save.
- **stdin gating** — the console "Send" control is offered only for engines with proven stdin support; currently no engine adapter advertises it (all are one-shot command launches), so the control stays hidden rather than promising input that would not be read.
- **Protocol writes** go through the central write coordinator with per-root locking and CAS, and are refused for a project while a Core agent runs there — SAIPENVIEW never becomes a silent second writer.
- **`generic-cli` is a deliberate shell escape hatch, not a sandbox.** It runs a user-supplied command through `cmd.exe /d /s /c` with the project as working directory. Quotes, pipes and `&&` work. Only a local user who already controls the machine can supply that command, and only they are responsible for what it runs.
- **Git Revert** restores tracked changes only; deleting untracked files requires the separate, explicitly-labelled operation.

---

## Features

### Discovery

- **Auto-scan** local drives for `.saipen/` projects (system drive is excluded
  from auto-scan by default; add it as a custom root to include it)
- **Custom roots** — pick folders or entire drives
- **Smart excludes** — `node_modules`, `.git`, system dirs, temp/build trees
- **Background rescan** — configurable interval (default 300s)
- **Filesystem watching** — `STATE.md`/`BOARD.md`/`LOG.md` changes refresh only the changed project
- **Linked worktrees** — detects git worktrees for easy setup

### Dashboard

- Live **phase**, **task**, **next action**, **blocker**
- **Git branch** + dirty-state indicator per project
- **Filter** by phase (All / Live / Done / Stuck / custom)
- **Sort** — Smart, Recent, Oldest, A–Z, Z–A
- **Search** — name/root filter + deep ticket search (`Ctrl+F`)
- **Pin** projects to top, **hide** irrelevant ones
- **Flash highlight** — changed projects glow and fade over 20s
- **Heat coloring** — stale projects cool, fresh projects warm

### Sub-Agents

- **Nested display** — any subSaipen registered in the project's
  `.saipen/extensions/subs/MANIFEST.md` (e.g. `saiwiki`, `saihunt`,
  `saitranslate`, `saipython`, `saitest`, `saiui`, or custom names) is shown
  indented under its parent
- **Outbox counts** — `ready` / `draft` / `blocked` / `reviewed` / `stale` at a glance
- **One-click collect** — fold ready entries into the main project
- **Stale warning** — detects out-of-date protocol files

### Agent Engine

- **Launch supported AI CLIs** in a project — `claude-code`, `codex`, `aider`,
  `gemini`, `cline`, `goose`, `agy`, `opencode`, `generic-cli`
- **Live status** — running/exit state, CPU, elapsed time per project
- **Output console** — buffered agent output (default 5000 lines); stdin input
  only for engines with proven stdin support (currently none advertise it)
- **Kill / stop all** — per-project kill and global stop
- **Run history** — past runs and transcripts persist across restarts
- **`generic-cli` is a shell command** — the instruction runs through
  `cmd.exe /d /s /c` with the project as working directory; quotes, pipes and
  `&&` work. See *Safety boundaries*.
- **`engine_overrides`** — per-engine `{"path": <exe>, "extra_args": [...], "env": {...}}` validated before launch
- **Single-instance guard** — only one app instance; a second launch re-shows the window

### Interaction

- **File viewer/editor** — read & edit `.md`/`.json` files inside verified
  project roots; source mode (editable) + reader mode (rendered)
- **Interactive tickets** — Start / Done / Block / Reopen / Unblock buttons
  update BOARD.md live
- **Human note** — a note the next agent actually picks up from STATE.md
- **Record manual work** — log a manual edit as a BOARD entry
- **Quick actions** — contextual `npm run dev`, `cargo test`, etc. based on project files
- **Custom commands** — user-defined action buttons
- **Collapsible sections** — per project, persisted
- **Resizable sidebar** — drag to resize

### Hotkeys & Window

- **Show/Hide** — `Ctrl+Alt+X` / `Alt+F15` (configurable)
- **Snap corners** — `Ctrl+Q` cycles TL → TR → BL → BR
- **Zoom** — `Ctrl+MouseWheel`, `Ctrl` + `+` / `-`, `Ctrl+0` resets
- **Force-quit** — `Ctrl+Shift+Alt+Q`
- **Deep search** — `Ctrl+F`
- **Toggle toolbar** — `Alt+D`
- **System tray** — minimize to tray, start hidden
- **Always-on-top** toggle
- **Autostart** — optional Windows startup (HKCU Run key)
- **Frameless mode** — toggle the titlebar off for an ultra-minimal view; drag anywhere to move the window

---

## SAIPEN Protocol

SAIPENVIEW is a companion for projects using the **SAIPEN Protocol** — a
state-machine framework that guides AI agents through project work in defined
phases:

```
INIT → PLAN → SCOUT → BUILD → VERIFY → REVIEW → SHIP → DONE
```

Other phases — `HUNT`, `ADD`, `MARKHUNT`, `CLEAN`, `TRANSLATE`, `PREPARE`,
`VALIDATE`, `BLOCKED` — are reached by command or by specific rows of the
transition table (the full table and the closed vocabularies live in
`saipenview/protocol.py`). The canonical protocol and its tooling are
maintained in the [SAIPEN repository](https://github.com/vacterro/saipen).

Each SAIPEN project stores its state in three canonical files:

| File | Purpose |
|---|---|
| `.saipen/STATE.md` | Machine-readable frontmatter — phase, task, next action, blocker |
| `.saipen/BOARD.md` | Ticket board — DOING / TODO / DONE / BLOCKED sections |
| `.saipen/LOG.md` | Chronological event log — every command and its outcome |

**SubSaipen agents** live in `.saipen/extensions/subs/<name>/` (registered in
`MANIFEST.md`) and communicate via `kitchen/OUTBOX.md` — the protocol's
built-in cross-agent message bus. SAIPENVIEW discovers all of them and renders
a unified dashboard.

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
copy of the protocol's vocabularies carried in `saipenview/protocol.py`. That
copy is pinned to a named `BASELINE_VERSION`, which is printed under every
verdict — a verdict is never anonymous. `tests/test_protocol_sync.py` re-checks
the copy against a reachable canonical SAIPEN repo, and `tools/validate.py` in
the [canonical SAIPEN repository](https://github.com/vacterro/saipen) remains
authoritative.

The viewer is allowed to lag the protocol. It is not allowed to lag it quietly.

> 💡 *The name "SAIPENVIEW" says it all — it provides a **view** into every **SAIPEN** project on your machine.*

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW detail pane — tickets, sub-agents, conformance and file viewer" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
</p>

---

## Configuration

Config is portable — stored next to the app, not `%APPDATA%`:

```
saipenview/_data/config.json
```

Key defaults (abridged — the full `DEFAULTS` dict lives in `saipenview/config.py`):

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["ctrl+q"],
  "zoom_level":       1.0,
  "font_family":      "Verdana_m1",
  "theme":            "goldendefault",
  "scan_roots":       null,
  "rescan_interval":  300,
  "scan_depth":       6,
  "scan_delay_ms":    10,
  "exclude_dirs":     [],
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "frameless":        true,
  "flash_changes":    true,
  "locale":           "en",
  "default_engine":   "claude-code",
  "file_viewer_default": "source",
  "layout_swap":      false
}
```

- Set `scan_roots: null` to autodetect all local drives (system drive excluded).
- Set it to a list of paths (e.g. `["V:\\", "D:\\projects"]`) to limit scanning.
- `default_engine` / `engine_overrides` / `agent_output_buffer_size` drive the Agent Engine (see Features).
- `theme` is a slug from `saipenview/assets/themes/` — 16 palettes ship with the
  app (Dark Golden, Claude Code, Antigravity, K-Lite, FreeBuff, CodeNomad,
  Default, Golden Vintage, Golden Default, Vintage Dark, Vintage Classic, OLED,
  Dracula, Nord, Solarized Dark, Custom). Switching is live and needs no
  restart; the palette is applied by setting CSS custom properties at runtime,
  so `style.css` is never rewritten to change a colour. `goldendefault`
  reproduces the stylesheet's own defaults exactly, and an unknown slug falls
  back to it.
- All settings are also configurable through the **Settings** modal in the app.

### Path safety & dry-run

Paths the app stores — `scan_roots`, `pinned_roots`, `hidden_roots`,
`selected_root` — are kept in a **canonical form**: absolute, case-normalised,
symlink-resolved, with a single trailing separator on drive roots and nowhere
else. A folder added as `v:\projects/` is stored and compared as
`V:\projects`, so slash/case/duplicate spellings of the same path never appear
as two entries.

Scan roots that point at a missing drive or folder are **quarantined, not
dropped**: they are reported in the scan error log and stay in the list, so
when the drive comes back the next scan picks it up automatically.

The built-in file viewer only opens `.md`/`.json` files that sit inside a
verified project root — a path that escapes every root or carries another
extension is rejected on the Python side, not just hidden in the UI.

Validate the config and path layers without starting the app:

```
python -m saipenview --dry-run
```

Exit code `0` = config clean, `1` = missing/quarantined roots or a canonical
mismatch, each named on stdout.

---

## Architecture

```
saipenview/
├── app.py              Entry wiring — tray, hotkey, window, api, single-instance guard
├── api.py              JS-facing pywebview bridge (77 public methods)
├── scanner.py          Drive walk + parallel per-root scan + background rescan loop
├── parser.py           STATE.md / BOARD.md / LOG.md parsing, tickets, subs, git status
├── textio.py           One reader/writer for every .saipen/ file — BOM, UTF-16, cp1251
├── protocol.py         The protocol's closed vocabularies + BASELINE_VERSION
├── conformance.py      Grades a project against those vocabularies
├── config.py           Settings load/save (atomic writes)
├── tray.py             pystray system-tray icon + menu
├── hotkey.py           Global hotkey registration (keyboard lib)
├── autostart.py        Windows Registry autostart management
├── zone_picker.py      Ctrl+Q corner-snap overlay (tkinter)
├── events.py           In-process event bus (EventBus)
├── guard.py            Single-instance lock + show-request handoff
├── git_diff.py         Working-tree diff / commit / revert for agent actions
├── runtime.py          Agent Engine — process manager for launched agents
├── sessions.py         Agent run history + stored transcripts
├── watcher.py          Watchdog file watcher on .saipen/ files
├── themes.py           Colour themes — palette + hexBlend computation
├── paths.py            Path canonicalization + file-boundary checks
├── protocol_write.py   Write coordinator — atomic .saipen mutations, CAS + E/T allocation
├── engines/            Supported CLI engines (claude-code, codex, aider, gemini,
│                       cline, goose, agy, generic-cli, opencode)
├── ui/
│   ├── window.py       pywebview window — show/hide/toggle/snap
│   └── static/         Frontend (index.html, style.css, app.js, 34 UI locales)
├── assets/             Tray icon + colour-theme palettes
├── screenshots/        README screenshots
└── _data/              Runtime config + cache (gitignored)
```

### Design principles

- **One foreground process** — the window, tray, watcher, scanner and API live
  in a single Python process; there is no separate server or background
  daemon. The only loopback socket exists in `guard.py` for the
  single-instance handoff: a second launch sends `SHOW` so the existing
  window comes to front, then exits.
- **Atomic writes** — config, cache and protocol-file writes use temp-file +
  `os.replace`, so a crash mid-write never exposes a partially written file.
- **Stale-read safe** — the 5s UI poll calls `refresh_known()` (re-reads only
  `.saipen/` files, no directory walk) while the watchdog handles immediate
  per-project refreshes. Edits to STATE.md appear within seconds without
  triggering a full drive scan.
- **No animation** — visual effects (flash, heat) are JavaScript-driven
  `hexBlend` recomputations; the stylesheet disables transitions/animations
  to stay within the vintage zero-animation constraint.
- **Vintage theme** — dark brown surfaces, golden text/accents, 3D beveled
  borders, no anti-aliasing, Verdana.

---

## Development

```bat
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m saipenview
```

For detailed setup, coding conventions, and the PR workflow, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Translations

`README.md` is the canonical documentation. Translated copies are generated
from it and may lag the English original — when a translation and the English
text disagree, the English version is authoritative.

<details>
<summary>Read this README in your language</summary>

| Code | Link | Code | Link | Code | Link |
|---|---|---|---|---|---|
| AR | [README.ar.md](docs/i18n/README.ar.md) | IT | [README.it.md](docs/i18n/README.it.md) | SV | [README.sv.md](docs/i18n/README.sv.md) |
| BG | [README.bg.md](docs/i18n/README.bg.md) | JA | [README.ja.md](docs/i18n/README.ja.md) | TH | [README.th.md](docs/i18n/README.th.md) |
| CS | [README.cs.md](docs/i18n/README.cs.md) | KO | [README.ko.md](docs/i18n/README.ko.md) | TR | [README.tr.md](docs/i18n/README.tr.md) |
| DA | [README.da.md](docs/i18n/README.da.md) | NL | [README.nl.md](docs/i18n/README.nl.md) | UK | [README.uk.md](docs/i18n/README.uk.md) |
| DE | [README.de.md](docs/i18n/README.de.md) | NO | [README.no.md](docs/i18n/README.no.md) | VI | [README.vi.md](docs/i18n/README.vi.md) |
| EE | [README.ee.md](docs/i18n/README.ee.md) | PL | [README.pl.md](docs/i18n/README.pl.md) | ZH | [README.zh.md](docs/i18n/README.zh.md) |
| EL | [README.el.md](docs/i18n/README.el.md) | PT | [README.pt.md](docs/i18n/README.pt.md) | ZH-CN | [README.zh-CN.md](docs/i18n/README.zh-CN.md) |
| ES | [README.es.md](docs/i18n/README.es.md) | RO | [README.ro.md](docs/i18n/README.ro.md) | ДЕД | [README.ded.md](docs/i18n/README.ded.md) |
| FI | [README.fi.md](docs/i18n/README.fi.md) | RU | [README.ru.md](docs/i18n/README.ru.md) | FR | [README.fr.md](docs/i18n/README.fr.md) |
| SK | [README.sk.md](docs/i18n/README.sk.md) | HE | [README.he.md](docs/i18n/README.he.md) | HR | [README.hr.md](docs/i18n/README.hr.md) |
| HI | [README.hi.md](docs/i18n/README.hi.md) | HU | [README.hu.md](docs/i18n/README.hu.md) | ID | [README.id.md](docs/i18n/README.id.md) |

</details>
