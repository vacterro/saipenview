# Changelog

All notable changes to SAIPENVIEW are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Semantic versioning — see `saipenview/__init__.py`.

## [0.1.7] - unreleased

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
