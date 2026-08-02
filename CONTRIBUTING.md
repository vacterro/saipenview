# Contributing to SAIPENVIEW

First off, thanks for taking the time to contribute! 🎉

This document covers the development workflow, coding conventions, and project structure so you can get productive quickly.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Running the App](#running-the-app)
- [Project Structure](#project-structure)
- [Coding Conventions](#coding-conventions)
- [Linting & Formatting](#linting--formatting)
- [Testing](#testing)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Workflow](#pull-request-workflow)
- [Release Process](#release-process)

---

## Development Setup

### Prerequisites

- **Windows 10 or 11** — SAIPENVIEW is a Windows-native desktop app using WebView2
- **Python 3.10+** (3.11 or 3.12 recommended)
- **Git**

### Clone & Setup

```bash
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Install Optional Dev Tools

```bash
pip install ruff pytest
```

Or with uv (faster):

```bash
uv venv
uv pip install -r requirements.txt
uv pip install ruff pytest
```

---

## Running the App

### From Source (with console output visible)

```bash
python -m saipenview
```

### Hidden (tray-only, no console)

Run `run.vbs` (double-click) or:

```batch
start /min pythonw -m saipenview
```

### Launch Scripts

Run `run.bat` (double-click) — tray-only app; console output visible only during the one-time `.venv` bootstrap. For a real console (stderr visible), use `python -m saipenview` from a terminal instead.

### Console Logging

All failures are logged to stderr unconditionally. To see them when running from `run.vbs` (which hides the console), redirect stderr to a file:

```batch
start /min pythonw -m saipenview 2> debug.log
```

### Build a Wheel

```bash
pip install build
python -m build --wheel
pip install dist\saipenview-*.whl
```

---

## Project Structure

```
saipenview/
├── app.py          — Entry wiring: tray + hotkey + window + api + single-instance guard
├── scanner.py      — Drive walk + background rescan loop
├── parser.py       — STATE.md/BOARD.md/LOG.md parsing, sub/translate rollup
├── textio.py       — One reader for every .saipen/ file (BOM, UTF-16, cp1251)
├── protocol.py     — The protocol's closed vocabularies + BASELINE_VERSION
├── conformance.py  — Grades a project against those vocabularies
├── api.py          — JS-facing pywebview bridge (66 public methods)
├── config.py       — Settings load/save (atomic writes)
├── tray.py         — pystray system-tray icon + context menu
├── hotkey.py       — Global hotkey registration (keyboard lib)
├── autostart.py    — Windows Registry autostart management
├── zone_picker.py  — Alt+F14 corner-snap zone picker (tkinter)
├── events.py       — In-process event bus
├── guard.py        — Single-instance lock + show-request handoff
├── git_diff.py     — Working-tree diff / commit / revert for agent actions
├── runtime.py      — Agent Engine process manager
├── watcher.py      — Watchdog file watcher on .saipen/ files
├── __init__.py     — Version constant
├── __main__.py     — CLI entry point
├── engines/        — Agent Engine: supported CLI engines (claude-code, codex, aider, gemini, cline, goose, agy, generic_cli)
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

### Key Design Decisions

- **Single process** — no background IPC, no separate server. The Python process hosts both the WebView2 window and the scan loop in one `ThreadPoolExecutor`.
- **Atomic writes** — config and cache use `temp-file + os.replace` so a crash can never truncate them.
- **Stale-read safe** — the 5s UI poll calls `refresh_known()` (re-reads only `.saipen/` files, no directory walk), so edits to `STATE.md` appear within seconds without a full drive scan.
- **No CSS transitions** — all visual effects (flash, heat, hover) are JavaScript-driven `hexBlend` recomputations, strictly following the vintage no-animation constraint.
- **Agent Engine layer** — `runtime.py`, `engines/`, `events.py`, `guard.py`, `git_diff.py`, `watcher.py` follow the same conventions as the rest of the package; `api.py` exposes its 66 public methods to the frontend.

---

## Coding Conventions

### Python

- **Target version**: Python 3.10 (ruff `target-version = "py310"`; the project supports >=3.10, tested on 3.10–3.12).
- **Line length**: 88 characters (ruff default; the codebase permits up to ~100 for readability).
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes, `UPPER_CASE` for constants.
- **Type hints**: Required on all public function signatures. Use `from __future__ import annotations` for cleaner forward references.
- **Imports**: Standard library first, then third-party, then local. One `import` per line. Use `from __future__ import annotations` at the top of every module.
- **Docstrings**: Required on all public modules, classes, and functions. Use triple-double-quotes (`"""..."""`). Keep them concise — explain *why*, not *what* (the code says what).
- **Error handling**: Use specific exception types. Log failures to `sys.stderr` with `SAIPENVIEW: <context>: {e}` format. Never use bare `except:`. If a failure path must silently degrade, log it first.
- **String formatting**: Use f-strings exclusively. Never use `%` formatting or `.format()`.
- **Context managers**: Use `with` for file I/O and resource management.
- **Testing**: Prefer `if __name__ == "__main__":` blocks for lightweight smoke tests. Formal pytest tests go in `tests/`.

#### Python Style Rules (ruff enforced)

```bash
ruff check saipenview/        # Check for issues
ruff format saipenview/       # Auto-format
ruff check --fix saipenview/  # Auto-fix fixable issues
```

All PRs must pass `ruff check` (zero warnings) and `ruff format --check`.

### JavaScript (app.js)

- **Line length**: 120 characters.
- **Naming**: `camelCase` for variables/functions, `PascalCase` for constructors, `UPPER_SNAKE_CASE` for constants.
- **DOM access**: Cache `document.getElementById()` lookups. Use `?.` optional chaining for safety.
- **Error handling**: API calls through `pywebview.api` must have `.catch()` handlers. Background operations log via `console.error()`. User-facing failures use `showToast()`.
- **Event delegation**: Prefer `document.querySelector()` + `closest()` over per-element listeners when handling dynamic content.
- **No framework dependencies**: The JS is vanilla — no React, no Vue, no jQuery.
- **No CSS transitions**: All visual effects use JavaScript `hexBlend()` recomputation per tick.

### CSS (style.css)

- **Theme system**: Use CSS custom properties (`var(--surface)`, `var(--textPrimary)`, etc.). Never hardcode colors.
- **No transitions**: The global `* { transition: none !important; }` reset forbids CSS transitions and animations.
- **Bevel system**: Use `.raised` class for 3D bevel borders (2px light top/left, 2px dark bottom/right).
- **No transparency**: All backgrounds are solid — `rgba()` and `opacity` are forbidden per the vintage theme.

---

## Linting & Formatting

### ruff (Python)

```bash
ruff check saipenview/
ruff format --check saipenview/
```

Expected output:

```
All checks passed!
13 files already formatted
```

### compileall (Python syntax)

```bash
python -m compileall saipenview/
```

### Pre-commit (recommended)

Install the pre-commit hook to auto-run ruff on every commit:

```bash
pip install pre-commit
# Create .pre-commit-config.yaml (see below)
pre-commit install
```

Minimal `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### Node.js (JavaScript)

```bash
node --check saipenview/ui/static/app.js
```



---

## Testing

SAIPENVIEW has a pytest suite (`tests/test_*.py`, 400+ tests). Contributions that add tests are especially welcome.

### Current Validation Approach

- **`py_compile`** — all `.py` files must compile without syntax errors.
- **`node --check`** — `app.js` must parse without syntax errors.
- **`ruff check`** — zero lint warnings.
- **Import chain** — every module must import cleanly (dependencies permitting).
- **Manual smoke test** — launch the app and verify the window renders without console errors.

### Test Guidelines (for new contributions)

- Test files go in `tests/test_*.py`.
- Use `pytest` with plain `assert` statements.
- Prefer property-based testing (Hypothesis) for parser functions.
- Mock `pywebview` and `tkinter` for unit tests — don't launch the real window.
- Add a `tests/conftest.py` with shared fixtures for sample `STATE.md`, `BOARD.md`, and `LOG.md` content.

---

## Commit Guidelines

### Format

```
<type>: <brief description>

<optional body — explain WHY, not what>
```

Types:

| Type       | When to use                                    |
|------------|------------------------------------------------|
| `feat`     | New user-facing feature                        |
| `fix`      | Bug fix                                        |
| `refactor` | Code restructuring (no behavior change)        |
| `style`    | Formatting, lint fixes only                    |
| `docs`     | Documentation changes (README, CONTRIBUTING)   |
| `chore`    | Build/tooling/infra changes                    |
| `perf`     | Performance optimization                       |

### Examples

```
feat: add Ctrl+Q corner-snap zone picker

Uses tkinter overlay window with 4 quadrants.
Cycles TL → TR → BL → BR on each press.
```

```
fix: prevent scan crash on corrupt MANIFEST.md

load_subs() now catches UnicodeDecodeError and falls
back to dir-scan instead of propagating the exception.
```

```
style: apply ruff format across all Python files
```

### Rules

- **First line**: ≤50 characters, imperative mood ("add", "fix", not "added", "fixed").
- **Body**: Wrap at 72 characters. Explain *why* the change was made, not *what* changed (the diff shows that).
- **References**: Link to issues with `#123` or `T-123`.
- **Atomic**: One commit per logical change. If you need to "fix the fix," squash before merging.

---

## Pull Request Workflow

### 1. Before Starting

- Check the [Issues](https://github.com/vacterro/saipenview/issues) page for existing discussion.
- For significant changes, open an issue first to discuss the design.

### 2. Branch Naming

```
feat/<short-description>
fix/<short-description>
docs/<short-description>
chore/<short-description>
```

Examples: `feat/add-file-filter`, `fix/scan-crash-utf8`, `docs/api-reference`.

### 3. Development Loop

```bash
git checkout -b feat/your-feature
# Make changes
ruff check saipenview/
ruff format saipenview/
node --check saipenview/ui/static/app.js
python -c "import py_compile, os; ..."  # validate all .py
# Smoke-test: python -m saipenview
git add -A
git commit -m "feat: your description"
```

### 4. Before Submitting

- [ ] `ruff check saipenview/` passes (zero warnings)
- [ ] `ruff format --check saipenview/` passes
- [ ] `node --check saipenview/ui/static/app.js` passes
- [ ] All `.py` files compile (`py_compile`)
- [ ] Smoke-tested: app launches without console errors
- [ ] Commit message follows the [guidelines](#commit-guidelines)
- [ ] Branch is up to date with `main`:
  ```bash
  git fetch origin
  git rebase origin/main
  ```

### 5. PR Description Template

```markdown
## Summary

Brief description of what this PR does.

## Related Issues

Closes #123

## Changes

- List of key changes (not a file list — why each matters)
- ...

## Testing

How was this tested? (manual smoke test, specific fixture, etc.)

## Screenshots

If applicable, add screenshots of the UI change.
```

### 6. Review Process

1. At least one maintainer review required.
2. All CI checks must pass (ruff, format, compile).
3. Address review feedback with additional commits.
4. Squash to a single clean commit before merge.
5. Merge via "Squash and merge" to keep history linear.

---

## Release Process

1. Ensure `saipenview/__init__.py` has the new version.
2. Update `CHANGELOG.md` with notable changes since last release.
3. Tag the release:
   ```bash
   git tag -a v0.1.0 -m "v0.1.0"
   git push origin v0.1.0
   ```
4. Build the wheel:
   ```bash
   python -m build --wheel
   ```
5. Create a GitHub Release from the tag, attaching the `.whl` file.
6. (Future) Publish to PyPI:
   ```bash
   pip install twine
   python -m twine upload dist/*
   ```

---

## Getting Help

- Open an [issue](https://github.com/vacterro/saipenview/issues) for bugs or feature requests.
- For questions, start a [discussion](https://github.com/vacterro/saipenview/discussions).

---

*SAIPENVIEW follows the [SAIPEN protocol](https://github.com/vacterro/saipenview) — every issue and PR is tracked as a ticket on the project's own BOARD.md.*
