# Changelog

All notable changes to SAIPENVIEW are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Semantic versioning — see `saipenview/__init__.py`.

> **Release metadata defect (0.1.18..0.1.20).** Those three releases were
> tagged and pushed while the committed version files stayed at 0.1.17, so the
> wheels they describe carry METADATA `0.1.17` and no `v0.1.18` tag was ever
> created (the 0.1.18 commit shipped under the 0.1.19 release). Their
> changelog entries describe real code, but their release identity was false.
> Fixed forward by `tools/release_gate.py` + `tools/verify_wheel.py` (T-188):
> version now has one source (`saipenview/__init__.py`, derived dynamically
> by pyproject) and the gate fails any release whose tag, wheel, changelog and
> package version disagree.

## [0.1.26] - 2026-08-11

### Fixed

- **CI green on Python 3.10 (T-193).** The test surface now supports the
  declared `requires-python >=3.10` floor: `test_dependency_parity` falls
  back to `tomli` where `tomllib` does not exist (< 3.11), the `dev` extra
  carries that backport behind a `python_version` marker, and CI installs
  `-e ".[dev]"` so the 3.10 job can collect. Previously the 3.10 CI job died
  at collection with `ModuleNotFoundError: tomllib`.

- **Grandfathered-marker test no longer depends on live board (T-199).**
  CLEAN (E-435) pruned the 111 legacy `## DONE` tickets that carried the
  `| verify: grandfathered` markers, so the marker count on the board is
  legitimately zero. `test_grandfathered_marker_is_uniform` now asserts the
  single canonical format from `docs/conformance-legacy.md` and checks any
  live marker against it, instead of failing on an empty board.

## [0.1.25] - 2026-08-11

### Fixed

- **Full-suite shutdown crash (T-198).** `test_hotkey` lifecycle tests
  registered REAL global keyboard hooks via `keyboard.add_hotkey`, leaving
  the library's listener thread alive for the whole pytest process. At
  interpreter shutdown a live hook callback raised
  `STATUS_FATAL_USER_CALLBACK_EXCEPTION` (exit `0xC000041D`), and the same
  leak under pytest's capture layer produced the intermittent
  `OSError: [Errno 9] Bad file descriptor` on the terminal flush. The
  lifecycle tests now use a `_NoOpKeyboard` shim (mirroring the existing
  `TestListenerRegistration` fake), so the suite never installs a global
  hook. `test_hotkey` 19/19; three consecutive full-suite runs green with
  no `INTERNALERROR` and no `0xC000041D`.

## [0.1.24] - 2026-08-11

### Changed

- **README public-product pass (T-200, T-201).** Top positioning reworded from
  "desktop tray viewer" to "Local Windows control center for SAIPEN projects".
  New near-top sections: *Why SAIPENVIEW*, *At a glance*, *Engineering
  evidence*, *Safety boundaries*. Conformance section keeps its honest
  "second opinion, not a replacement for `tools/validate.py`" framing, now
  linking the canonical SAIPEN repository. Quick Start states plainly that
  `pip install saipenview` is not published yet. The 33 translated READMEs
  carry a lag notice pointing at the canonical English original.

### Fixed

- **Release-gate test is version-agnostic (T-197).** `tools/release_gate.py`
  gains a `--root` override; `test_release_gate_passes` runs the gate against
  a sandboxed bumped-version tree so it is green at every shipped HEAD.

## [0.1.23] - 2026-08-07

### Fixed

- **README/CONTRIBUTING code-mapping drift (T-194).** Architecture and
  Features doc claims reconciled with the tree at HEAD: engines list now
  includes `opencode` (9 adapters live, README and CONTRIBUTING both),
  both architecture trees list `sessions.py`, `themes.py`, `paths.py` and
  `protocol_write.py`, CONTRIBUTING's api method count corrected
  `66` → `85`, and its corner-snap hotkey claim updated `Alt+F14` → `Ctrl+Q`
  (T-180 shipped the ctrl+q default). Wiki package WIKI-013 from saiwiki,
  collected and verified fresh at 71ed3a5.

## [0.1.22] - 2026-08-07

### Added

- **Per-project write coordinator (T-183).** Every mutation of a project's
  `.saipen/` files now goes through one coordinator: per-root lock plus an
  optimistic fingerprint/CAS so an external change between our read and our
  commit is a controlled conflict, never a silent lost update; the only
  T-/E- id allocators in the codebase; and a deterministic refusal to mutate
  a project while a launched Core agent owns it.
- **Backend self-write attribution (T-190).** The frontend no longer guesses
  which root it wrote. The coordinator registers each successful
  per-`(root, file)` post-write fingerprint and the watcher compares the
  current content, pushing `origin=self|external` -- so a failed write can
  never suppress the "unrecorded external change" prompt and a real external
  edit is always reported. `MainWindow.evaluate_js` delegate added (the
  watcher push had been dead in production: the Api called a method that
  never existed).
- **Idempotent, grammar-safe mutations (T-191).** `record_manual_work` is
  LOG-first with idempotent resume (no unlogged orphan tickets);
  `collect_outbox_entry` is idempotent per `(sub, entry_id)` -- re-running
  after any partial step resumes, never duplicates -- and refuses a stale
  `source_head` handoff. External text is pipe-escaped for the closed BOARD
  grammar.
- **Deterministic file watcher (T-179 wave).** The load-sensitive full-suite
  flake family is fixed at the root: unguarded `subprocess.run().stdout`
  `.strip()` calls no longer crash worker threads, the watcher lifecycle is
  hardened (`_disposed` guard, per-watch debounce), and the test fixture that
  depended on `C:\Program Files` is now a deterministic temp dir with spaces.

### Changed

- **Release/version truth (T-188).** The version has ONE source
  (`saipenview/__init__.py`; pyproject derives it dynamically). New
  `tools/release_gate.py` and tag-identity checking in `tools/verify_wheel.py`
  fail any release whose package version, wheel METADATA, git tag and
  CHANGELOG heading disagree -- the defect that shipped v0.1.18..v0.1.20 with
  wheels identifying as 0.1.17.
- **Dependency floors aligned (T-189).** `watchdog>=4.0`, `psutil>=5.9.0`
  everywhere; nuitka moved to pyproject's `dev` extra. A parity test makes
  the two install paths agree.
- **Own `.saipen/` memory conformant (T-187).** Every validator FAIL cleared
  with an explicit legacy policy (`docs/conformance-legacy.md`); the split-
  brain LOG branch and stale markhunt board copies quarantined verbatim;
  protocol canary bumped through 7.210.0.

### Fixed

- **Real leak behind the flake (T-190).** `app.run()` returned early on a
  second instance without stopping the Api, leaking an event-bus subscriber
  and watcher that fired on every later file change -- the source of the
  "js push failed" spam, missing watcher events and `PermissionError`s that
  made full-suite runs unreliable. The early-return path now cleans up, and
  the test suite pins zero subscriber leaks per test.

## [0.1.21] - 2026-08-07

### Changed

- **Default window-snap hotkey is now `Ctrl+Q` (T-180).** `snap_hotkey`
  ships `["ctrl+q"]` instead of `["alt+f14"]`, reversing the 4d291a0
  decision that freed the combo — a global binding hijacks it in every app
  and it collides with common quit accelerators, a tradeoff the user
  explicitly accepted. The load-time migration that silently purged `ctrl+q`
  from any saved config is gone: a snap binding the user sets in Settings
  now survives restarts instead of being reset on the next launch. Settings
  placeholder, quick-help and all 34 locale/README translations follow.

### Removed

- `config.py`'s `_is_ctrl_q` load-time strip and its four migration tests
  (the strip existed only to clean configs that predated 4d291a0).

### Fixed

- Release version files reconciled: `pyproject.toml` and
  `saipenview/__init__.py` had lagged v0.1.18..v0.1.20 (tags shipped while
  the declared version stayed 0.1.17, so wheels carried stale METADATA).
  Reset to 0.1.21 so the tag, the wheel and the changelog agree again.

## [0.1.20] - 2026-08-07

### Added

- **Record manual work (T-127).** When a project's `.saipen/` files change from OUTSIDE the app — a hand edit, an external tool, a commit the app did not make — the detail pane shows a persistent "Unrecorded external change" bar with a **Record manual work** button. Clicking it asks for a short description and writes an explicit, user-attributed record: a `T-### Manual: <desc> | owner: user` ticket on the board, a valid LOG evidence line, and best-effort git context (current HEAD + dirty-file count). SAIPENVIEW never guesses who changed a file: the prompt is the attribution. The app's own writes are tracked so its actions never trigger the prompt.

## [0.1.19] - 2026-08-07

### Added

- **Agent run history browser (T-177).** The session store has always kept up to 50 runs per project, but the panel only ever auto-restored the last transcript — past runs were invisible. The Agent Control panel now has a history selector listing past runs (time, engine, status, line count); selecting one renders its stored lines into the output pane, guarded by the same project-switch check that protects live output.
- **`engine_overrides` settings editor (T-178).** The per-engine override surface (`path` / `extra_args` / `env`) was implemented in 0.1.15 but only reachable by hand-editing `config.json`. Settings now has an "Engine overrides (JSON)" editor; the save path uses the exact same validation as launch, so an invalid override is refused with a visible error and the saved value stays untouched.

### Fixed

- **The T-169 project-switch guard read the wrong element and was silently always-false.** `isCurrentProjectPanel` read `dataset.root` off the `#agentPanelContainer`, but the `data-root` lives on the `.agent-panel` *child* — so in the real DOM the guard never matched, which quietly disabled both the transcript auto-restore and (newly) the history picker. The node test stubbed the container with the attribute and passed while the app failed. Fixed to query the child; the test harness now mirrors the real DOM.

## [0.1.17] - 2026-08-07

### Fixed

- **The app can no longer "not start" with an off-screen window (T-176).** The saved window position could be Windows' own off-screen sentinel (-32000,-32000) or a coordinate on a monitor that was unplugged since the last save. The app launched and ran perfectly -- the WINDOW was just parked where no monitor exists, so a second launch handed off to it and nothing appeared anywhere. The saved position is now validated against the visible desktop (the union of every monitor) before it is restored; an off-screen position is dropped and the OS positions the window on a real monitor instead. The stale position also self-heals: the next save overwrites it.

## [0.1.16] - 2026-08-07

### Added

- **Real-time interactive ticket checkboxes (T-174).** Every ticket row now carries a real checkbox that IS its status: click a TODO ticket's box to start it (moves to DOING as an indeterminate `[/]`), click a DOING one to mark it done, click a DONE one to reopen, click a BLOCKED one to unblock. TODO/DOING rows also get a **Block** button that asks for a blocker reason and moves the ticket to BLOCKED with that reason recorded as a `| blocker:` field. All moves go through the single-writer board path and keep the checkbox-vs-section agreement the protocol requires.
- **Drag-to-reorder BOARD tasks (T-175).** A ticket row can be dragged to a new position within its section; the dropped order is written straight to BOARD.md, and since board order is priority, a drag is a re-prioritisation. Same-section only, drop-on-row inserts before the target, drop on empty space appends to the end.
- **SubSaipen readability pass (T-126).** Each sub gets an orientation glyph (saihunt 🔍, saiwiki 📖, saipython 🐍, saitranslate 🌐, saitest 🧪, crew 🔧, fallback 🤖) in both the sidebar row and the detail card, and each sub card now carries a phase-coloured left edge using the same tokens as the project rows — state reads at a glance.

### Fixed

- **The file-viewer reader no longer hides the ticket fields (T-125).** The reader view of BOARD.md stripped everything after the first `|`, so `| verify:` and `| blocker:` evidence — the whole point of a reviewer reading the board — was invisible. The field tail is now kept and rendered as a muted sub-line, and STATE.md's known protocol keys (phase/task/next_action/blocker/agent/updated) are highlighted.

## [0.1.15] - 2026-08-07

### Fixed

- **Git diff/commit/revert show and touch exactly the same files (T-162).** The diff viewer only displayed staged+unstaged *tracked* changes while `Commit` ran `git add .` and `Revert` ran `git reset --hard` + `git clean -fd` — so Commit could include files that were never previewed, and Revert could delete untracked files that were equally invisible. The backend now reads the full mutation scope from `git status --porcelain=v1 -z` (staged / modified / deleted / renamed / untracked), shows it in the viewer, and every mutation is guarded by a fingerprint: if the working tree changed after the preview, the operation aborts with "refresh and review". Commit stages exactly the previewed paths (never `git add .`); Revert restores tracked changes only; deleting untracked files is a separate, explicitly-confirmed operation. Ignored files never enter any scope.
- **The protocol STATE/task bookkeeping can no longer silently go stale (T-161).** The conformance grader now FAILs a state that names a DONE ticket as its active task, a ticket-phase state whose task is not in `## DOING`, an active task with an empty `## DOING`, or a `PHASE SHIP T-###` pointing at an already-DONE ticket — the exact stale-state class this release's own protocol recovery started from.
- **The test-result parser had literal backspace bytes in its regexes (T-163).** `app.js` carried raw `0x08` control characters around `(\d+) failed` / `(\d+) passed` — a literal backspace, not the `\b` word boundary that was meant, so those branches could never match. Replaced with real `\b` boundaries, and `FAILED tests/test_x.py` (pytest's summary line) now counts as a failure. A source-hygiene test fails on any C0 control byte in `app.js`, and behaviour tests run the real parser under node.
- **The file viewer is no longer a disk-wide reader/writer (T-164).** The boundary was "inside any known root", and scan roots can be whole drives. File access is now limited to *verified project roots* (roots that actually hold a `.saipen/STATE.md`); a scan root is discovery scope, never file-access scope. Every root-taking API method resolves through one verified-root gate and returns a controlled error for anything unknown or escaped. Saving a file now preserves its original encoding and newline (a UTF-16 or BOM-carrying or CRLF file stays that way) and writes atomically — a failed write leaves the original byte-identical, with no temp debris.
- **Browse no longer forgets missing drives (T-165).** `browse_folder` filtered existing scan roots through `os.path.exists()`, dropping a temporarily-missing root on every browse — defeating the quarantine that keeps it and auto-repicks it when the drive returns. It now dedupes via the canonical path layer and keeps stale roots. Also removed a double linked-worktree scan: `rescan()` and `browse_folder()` both ran it once and `_set_cache()` ran it again.
- **Agent process lifecycle races closed (T-166).** Two concurrent launches of the same project could both pass the "is it running" check because the lock was released before `Popen`. Launch now holds a reservation under the lock, keyed by the canonical path (so case/slash spellings can't give one project two processes), and a concurrent launch gets a deterministic "already launching" error. One exactly-once finalizer now sets the exit code, closes the transcript and publishes `agent.finished` a single time — `kill()` previously published it once itself and the reader thread's EOF tail published it again. The output cursor is now the backend's canonical `next_since`, so a rolling buffer never re-sends lines.
- **stdin framing has one owner, and engines no longer fake interactivity (T-167).** The frontend sent `text + "\n"` and the backend wrote `text + "\n"` — two newlines for one intended line. The backend now strips trailing CR/LF and writes exactly one `\n`, rejects empty input, and keeps internal newlines in multiline input. Every engine declared `supports_stdin: True` on assumption; all of them launch one-shot headless (`codex exec`, `gemini --prompt --yolo`, `opencode run`, `agy -p`, `goose run -t`, `cline -y`, `aider -m --yes-always`), so the Send control is hidden until stdin support is proven for that engine — each engine file now carries the exact build command as its evidence comment.
- **The generic CLI is now really a shell command (T-168).** It promised quotes/pipes/`&&` and executed `instruction.split()` — a quoted path with spaces became four arguments. It now runs `cmd.exe /d /s /c <command>` with the project as working directory, the command text untouched, and the root never interpolated. The previously-dead `engine_overrides` config key is implemented and validated (`path` / `extra_args` / `env` per engine).
- **The file watcher watches every known project, not just running agents (T-124).** `SaipenWatcher` lived in the process manager, so only agent-launched projects were watched and the watch ended when the agent did. It now belongs to the Api and reconciles its watch set with the known projects; one filesystem event produces one targeted refresh of just that project, delivered to the frontend as JSON (an f-string interpolation of a Windows root with an apostrophe produced a syntax error in the page). Atomic `os.replace` writes, moved/created/deleted events, debounce bursts and a serialized cache write are all covered.
- **A stale async response can no longer repaint the wrong project's panel (T-169).** `restoreLastTranscript` and the agent status/output/launch/diff handlers wrote into whatever panel was showing when the promise resolved — switch projects mid-flight and the old project's transcript landed in the new one. Every DOM mutation is now guarded by "is this still the project being viewed", and a root is only marked as restored after a successful restore, so a transient failure retries instead of being blocked forever.
- **The Edit button survives a failure in the optional Agent Panel (T-122).** `renderDetailPane` rendered the agent panel *before* binding Edit/Folder/Terminal/Code/STATE/BOARD/LOG/Pin/Hide; a throw inside the panel silently skipped every binding below it, leaving Edit drawn but dead. The panel now runs last, inside an error boundary, and a persistent visible error region reports any render failure with the stage and project root.
- **Timing is deterministic and honest (T-123).** A timezone-naive `updated` stamp was silently treated as UTC (the 1–2h "timing is wrong" report) and a future stamp was clamped to "just now". The backend now normalizes valid stamps to explicit UTC; naive stamps are marked ambiguous and claim no age; future stamps render as "clock ahead". Bucket boundaries (59s/60s, 59m/60m, 23h/24h) are pinned by tests with a mocked clock, and the DST transition renders correctly on Europe/Tallinn.

### Added

- **Windows CI is a real gate (T-170).** A new blocking `tests-windows` job runs `pytest`, `compileall`, `ruff check`, `ruff format --check`, `node --check` and the control-byte test on `windows-latest` across Python 3.10/3.11/3.12; the build job now depends on it. mypy stays informational and is never a release gate. `tools/verify_wheel.py` builds from a clean checkout and proves the wheel's METADATA version equals `pyproject.toml`'s and `saipenview.__version__`'s, and that the installed wheel — not the source tree — imports and smokes cleanly.
- **Deterministic source export (T-171).** `tools/export_source.py` produces `dist/saipenview-src-<version>.tar.gz` from a clean `git archive` plus the canonical SAIPEN memory, with a manifest. The stray scratch probes at the repo root were reviewed and removed.
- **Explicit `.saipen` persistence contract (T-172).** `docs/saipen-persistence.md` documents that the project's SAIPEN memory is intentionally local-only — STATE carries a machine-local `saipen_home` and the board/log journal references machine paths, so tracking it raw would leak local paths — and defines the deterministic export/import handoff that replaces git for it.

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
