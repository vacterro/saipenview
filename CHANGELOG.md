# Changelog

All notable changes to SAIPENVIEW are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Semantic versioning — see `saipenview/__init__.py`.

## [0.1.9] - 2026-08-03

### Fixed
- Gemini adapter never ran headless. `engines/gemini.py` built `gemini prompt <instruction>`, and Gemini CLI has no `prompt` subcommand — the string fell through to the default `gemini [query..]` positional and opened an *interactive* session whose query happened to start with the word "prompt", then waited for a human a subprocess pipe never provides. Now `--prompt <instruction> --yolo`, with `GEMINI_CLI_TRUST_WORKSPACE=true` in the launch env because the live repro then stopped on "not running in a trusted directory"
- Claude Code adapter passed `--project-dir`, which is not a Claude Code flag; the project directory is the process cwd, which `runtime.py` already sets. Also added the `--verbose` that `--output-format stream-json` requires in print mode
- Aider adapter used `--yes`, which only worked by argparse prefix matching; the flag is `--yes-always`
- Agent transcripts no longer die with the process. Output lived in an in-memory `deque(maxlen=5000)` and nowhere else, so closing SAIPENVIEW erased both the transcript and any evidence a run had happened
- Killing an agent was recorded as a crash. `kill()` set the status *after* `terminate()`, but terminate makes stdout hit EOF and the reader thread reaches its own tail first — so the stored record said `failed` while the live status said `killed`
- Two agent runs started in the same second shared a session id and silently overwrote each other's transcript
- Hotkey parsing lost `,` and `+` as keys. Both are hotkey syntax *and* real keys, so a naive split turned `","` into two empty strings and dropped the comma from `ctrl+,`
- Protocol baseline 7.171.0 -> 7.175.0 (stamp-only, no vocabulary drift; the SAIPEN repo shipped four releases while this was being written)

### Added
- OpenCode adapter (`opencode run <message>`). It was installed, already owned tickets on this project's own board, and was the one agent SAIPENVIEW could not launch
- Agent run history and stored transcripts (`saipenview/sessions.py`): one metadata + transcript pair per run under `_data/sessions/`, capped at 50 runs per project and 5 MB per transcript. New `get_agent_history`, `get_agent_transcript` and `get_last_agent_transcript` API methods; the Agent Control console reloads the last stored transcript when nothing is running, labelled so old output is never mistaken for live. A run left mid-flight by a dead SAIPENVIEW reads back as `interrupted`, not as an agent still working

### Changed
- `default_engine` had been a config key read by nothing, so the launcher always opened on whatever the registry listed first. It now preselects the configured engine when that engine is actually installed, and remembers the last one launched

## [0.1.8] - 2026-08-02

### Fixed
- Global hotkeys are layout-independent. `keyboard.add_hotkey("ctrl+q")` resolved the letter through the *active* Windows layout, so with a Russian (or any non-Latin) layout selected the combo bound to the wrong physical key — and on a machine with no Latin layout installed at all it raised `ValueError` and the hotkey silently never registered. Character keys now bind to their US scan-code positions; modifiers and F-keys still go through `keyboard`, which is already layout-independent for those
- Wintage's theme installer no longer rolls SAIPENVIEW's stylesheet back in time. `Invoke-Saipenview` recolours from `style.css.bak`, and that backup was taken once and never refreshed — so every run rewrote `style.css` as `<old snapshot> + new colours`, deleting the `--dangerText` token, the `.conf-list` collapse rule, the Agent Panel block and the `.bmac-btn` rule. This is the CSS that "regenerated itself" to a file matching no commit in this repo's history. Fixed upstream in Wintage (`desktop/install.ps1`): the backup's shape is compared against the live file and re-taken when the app's own CSS has moved on
- Project name stays readable when the window is narrow or collapsed. `.detail-title` had no `min-width: 0` anywhere, so the branch badge, conformance badge and phase pill pushed the name straight out of the box; collapsed mode hid the whole header, name included. The name now truncates with an ellipsis instead of vanishing, and collapsed mode drops the path and action bar rather than the title
- Protocol baseline 7.164.0 -> 7.171.0 (stamp-only, no vocabulary drift)

### Changed
- Conformance section is hidden when there is nothing to report. A clean verdict rendered a card saying "no findings" on every conforming project; the `OK` badge in the header already says it in one glyph
- Agent Control explains itself: a one-line description of what it launches and where the output goes, plus a tooltip on every control (engine picker, instruction box, Launch, Note, Stop, Diff, Send, and the Continue/Hunt/Clean shortcuts). All strings are i18n keys instead of hardcoded English
- Repo root holds one `README.md` again — the 33 translations moved to `docs/i18n/`, with every language bar and relative link retargeted, and all 33 now linked instead of 5. Dropped the tracked `scratch_t119.py` and the stray `nul` file

## [0.1.7] - 2026-08-02

### Added
- Full locale wiring: all 34 `locale-*.js` loaded by `index.html`, 33 languages selectable in Settings, `api.get_locales()` returns 34 with native names (was hardcoded en/zh-CN)

### Fixed
- 11 STUB locale files (cs he hi hr it ja pl sk sv vi zh) declared `const LOCALE_EN` — a second global declaration that would break page load once wired; each now declares its own `LOCALE_XX`
- README translations refreshed to HEAD: snap hotkey `Alt+F14` (Ctrl+Q/Strg+Q gone), 18-key config example, full architecture trees, protocol phase diagram, Agent Engine docs; ru/ee/ded fully retranslated (were mojibake / broken UTF-8 / abridged)
- Protocol baseline 7.161.0 -> 7.164.0 (stamp-only, no vocabulary drift)

## [0.1.6] - 2026-08-02

### Fixed
- README/CONTRIBUTING docs sync: hotkey rows (snap is `Alt+F14`, not `Ctrl+Q`), config example, architecture trees (all 19 modules + `engines/`), run.bat behavior claim, protocol phase diagram, Python target (3.10)
- README Agent Engine feature documented (launch, live status, output console, kill)

### Added
- CHANGELOG.md (this file)

## [0.1.5]

### Fixed
- Hotkeys: drop global `ctrl+q` default, survive one bad binding (3e02e1a)
- App could refuse to start silently with exit code 0 (f5ab52a)
- Human note written where no agent could read it; protocol synced to 7.149.0 (5b7b66f)
- Unreadable FAIL text, dead Conformance collapse, comments graded as entries (472a066)

## [0.1.4]

### Added
- Complete agent IDE + exception handling refactor — T-083, T-097, T-099–T-107 (846e91d)

### Changed
- Perf: stop polling, re-rendering and disk-writing while the window is hidden (69230f3)
- Scan: exclude garbage paths, cap the overall scan, free `ctrl+q` (4d291a0)

## [0.1.3]

### Added
- Grade `.saipen` projects, and read them at all (42100e3)
- Docs: record the reader and the grader (bb04adf)

### Fixed
- Dead collapse arrows on short lists; sync two stale docs (4b0c9f7)

## [0.1.2]

### Added
- SingleInstanceGuard extracted to guard.py + 283-test suite (3c568a1)
- i18n runtime layer + wiki delivery layer (9e359d4)
- Meta tags, favicon in index.html (d803deb)

### Changed
- CI restore with continue-on-error on lint/typecheck (a6f5f4a)
- Ruff lint fixes, CI hardening, shell injection fix (9360141)

## [0.1.1]

### Added
- saiwiki + saitranslate content — OUTBOX closed, delivery layer wired (7429cdd)

## [0.1.0] - initial release
