# Changelog

All notable changes to SAIPENVIEW are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Semantic versioning — see `saipenview/__init__.py`.

## [0.1.14] - 2026-08-07

### Fixed
- **Edit form no longer collapses during live poll (T-121).** The 5-second poll cycle called `loadDetail(selectedRoot)` unconditionally from `render()`, which kicked off an async detail fetch + `renderDetailPane` chain. The `stateEditActive` guard from T-066 fires inside the `.then()` callback, but by then the callback is already scheduled and a concurrent state change cannot be seen — the detail pane could rebuild and destroy the inline edit form. `render()` now skips `loadDetail` entirely when `stateEditActive` is true, making the decision deterministic. The same function's filtered-list-eviction path (`renderDetailPane(null)` when the selected project disappears from the list) also now honours `stateEditActive` instead of discarding the user's typed work.

## [0.1.13] - 2026-08-06

### Added
- **Path-safety layers (T-138).** A canonical path layer (`saipenview/paths.py`) turns every stored path into one true spelling — absolute, case-normalised, symlink-resolved, a single trailing separator on drive roots and nowhere else — applied at config load/save, scan, and every comparison, so slash/case/duplicate spellings of the same folder never drift apart. Scan roots pointing at a missing drive are **quarantined, not silently dropped**: they surface in the scan error log and stay in the list, so the drive comes back and the next scan picks it up automatically. The built-in file viewer is now boundary-hardened: it opens only `.md`/`.json` files that sit inside a known project root, and a path that escapes every root (including a `..` climb) or carries another extension is rejected on the Python side, not just hidden in the UI. New `python -m saipenview --dry-run` validates the config and path layers without starting a window — exit `0` on a clean config, `1` naming every missing/quarantined root or canonical mismatch.

### Fixed
- An explicit empty `scan_roots: []` ("scan nothing") is no longer promoted to `None` ("auto-scan all drives") during config canonicalization — the two are different answers and the promotion silently re-enabled auto-scan.

## [0.1.12] - 2026-08-06

### Added
- **All 16 Wintage colour palettes ship inside the app**, with a picker in Settings that switches live and needs no restart. They previously existed only as inputs to an external PowerShell installer that applied a palette by *rewriting* `saipenview/ui/static/style.css` on disk — the mechanism that destroyed the stylesheet twice (0.1.x, tickets T-096 and T-142) in a way that survived review both times, because the file it produced still parsed and still looked like itself. A theme is data now: `saipenview/assets/themes/*.json`, a `theme` config key, and CSS custom properties set on the root element at runtime. `goldendefault` reproduces the stylesheet's own `:root` token for token, so the app with themes and the app without them are identical until you pick something else. Palettes are validated before use, because the failure mode is silent — an undefined custom property renders as the initial value with no error anywhere

### Fixed
- **The UI is fluid at any window size and zoom.** Two root causes, neither visible without measuring. `zoom_level` is applied as `body.style.zoom`, but `vw`/`vh` resolve against the *unscaled* viewport — so at 125% a `90vw` box rendered at 112.5% of the window, and `max-height: 92vh` let the Settings dialog render 176px **taller** than the window at 1280x720/150%, pinning its own Save and Close buttons off-screen. Every viewport unit is gone; the app measures itself with a container query on `body`. Separately, the sidebar wrote an absolute pixel width and only ever recomputed it at boot and on drag, so a width chosen on a wide window ate the detail pane on a narrow one
- **Settings is no longer a 320px column on a 1920px screen.** `.modal-box` was capped at 320px regardless of window size, so eighteen fields stacked in one column with every label wrapped to two lines. Its body is a grid that finds its own column count — one narrow, three wide. Measured across 6 dialogs x 15 size/zoom combinations: 0/90 out of bounds, against 14/90 before
- **Agent Control was dead on every Windows project, silently.** `renderAgentPanel` built an element id by concatenating the project root and read it back with `querySelector('#agentControlTop-' + root)`. A drive letter and backslashes are not a valid selector, so `querySelector` threw — and since `renderDetailPane` calls that function as its last statement with no guard, the throw took the tail of the detail render with it. Also fixed in the same function: switching project kept the previous project's output, because the state variable was assigned three lines above the comparison that gates the rebuild
- **Four CSS custom properties were referenced but never declared** — `--bgRaised` (4 sites), `--surfaceBase` and `--text` — so the wiki article body, its active table-of-contents row, the file viewer's editor and the diff pane had been rendering with a fully transparent background since they shipped. Confirmed by measuring: `rgba(0, 0, 0, 0)` at all four before, real colours after. The audit now runs as a test over `style.css`, `index.html` and `app.js`, since two of the three dead tokens lived in inline styles
- **The protocol canary is green again.** The SAIPEN repo moved 7.176.0 → 7.201.0 and `SAIPEN_COMMANDS` gained `crew` and `test`. Per T-097's rule the releases (7.177.0..7.201.0) were read before the stamp moved: only the command set drifted, so `crew` and `test` were added and `BASELINE_VERSION` bumped. `crew` is decoded rather than copied — it is the serial factory circuit (`sc`), no parallel agents, distinct from the v8 Crew Mode GUI surface still frozen by T-150

### Notes
- `tests/test_protocol_sync.py` was **red on purpose** while the SAIPEN repo moved 7.176.0 → 7.201.0; it is green again at 7.201.0 (T-160)

## [0.1.11] - 2026-08-04

### Added
- **Agent Control panel strings translated into all 33 locales.** The panel's 25 keys (added in 0.1.10's engine work, English-only with runtime fallback) now ship translated in 22 real-translation locales (ar bg da de ded el es et fi fr hu id ko nl no pt ro ru th tr uk zh-CN) and `[XX]`-tagged placeholders in the 11 stub locales (cs he hi hr it ja pl sk sv vi zh), matching the existing stub convention. `node --check` clean on all 34 locale files; exactly 25 `agent.*` keys added per file, zero removals

### Changed
- **README translation mirrors caught up with the current English README.** All 33 `docs/i18n/README.*.md` dropped the removed buy-me-a-coffee support link and the whole At-a-Glance/screenshot section (both deleted from the English README after the previous translation pass), so the mirrors again mirror the live document. Structure verified per file: 9 headings == EN, `<br> --- ## 🚀` layout identical

## [0.1.10] - 2026-08-03

### Fixed
- **The app shut itself down within seconds of any typing.** Regression shipped in 0.1.8. `to_layout_independent` returned `keyboard.parse_hotkey`'s output, but `add_hotkey` re-parses its argument with `parse_hotkey_combinations`, whose first branch is `if _is_number(hotkey) or len(hotkey) == 1` — and a parsed *one-step* hotkey is a 1-tuple, so it matched that branch and was read as a single key whose "alternatives" were the modifiers. `ctrl+shift+alt+q` became `ctrl OR shift OR alt OR q`: 36 four-key combinations collapsed to 8 one-key ones. That hotkey is the kill switch and its handler is `os._exit(0)`, so pressing Ctrl anywhere terminated SAIPENVIEW with no window, no dialog, no log and exit code 0. Layout pinning now returns shapes `keyboard` parses as intended, and the pinned combinations are provably a strict subset of what the plain string form would match
- The kill switch is no longer a silent death: `force_destroy` writes a stack to `_data/force_exit.log` (and stderr) before exiting. Under `pythonw.exe` via `run.vbs`, `sys.stderr` is `None`, so this path previously left nothing at all behind
- Protocol baseline 7.175.0 -> 7.176.0, and a real vocabulary drift with it: `ANY_FROM` gained `HUNT`, because `saipen hunt` enters HUNT from any phase (RFC § 2.1). The canary caught this rather than the stamp check alone

### Notes
- Startup was measured on the real launch path and is **not** slow: 1.6–2.3s from `run.vbs` to the window being shown (imports 0.19s, `create_window` 0.26s, `webview.start` 0.59s). WebView2 initialisation is the floor. The reported slowness is most plausibly the shutdown bug above — the app died, its socket lingered, and the next launch either exited quietly at the single-instance guard or waited out its bind retries
- "Two instances running at once" was not real. `.venv\Scripts\pythonw.exe` is Python's venv launcher stub: it spawns the base interpreter as a child, so one launch always shows two `pythonw.exe` processes parented to each other. Port 47189 only ever had one listener

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
