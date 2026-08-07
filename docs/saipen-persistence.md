# SAIPEN memory persistence contract (T-172)

## Decision

This project's `.saipen/` is **intentionally local-only**. It is not tracked
in git, and it will not be tracked in git. This is a written decision, not a
silent `.gitignore` accident — the two paragraphs below say why, and the
handoff that replaces git is specified at the bottom.

## Why local-only

`.saipen/STATE.md` carries `saipen_home`, an absolute machine-local path to
the protocol install. `.saipen/LOG.md` and `.saipen/BOARD.md` are the audit
trail and the work surface: their event text and ticket prose routinely
reference absolute paths (`V:\...`, `C:\...`) because that is what a protocol
journal records. `config` scan roots and the `cache.json` under
`saipenview/_data/` are the same class. Committing any of that raw would put
machine-local paths into the repository, which is the one thing a persistence
contract must never do — a clone would carry dead paths that look alive.

Tracking sanitized copies instead (paths stripped) would diverge from the
live files on the next checkpoint, so the tracked copy would lie by
definition. Local-only is the honest state.

## The split

| Kind | Location | Contents | Travels |
|------|----------|----------|---------|
| Canonical memory | `.saipen/BOARD.md`, `.saipen/LOG.md`, `.saipen/KNOWLEDGE/`, `.saipen/kitchen/digest.md` | work surface, audit trail, durable architecture notes, last-session digest | via `tools/export_source.py` only |
| Local / ephemeral | `.saipen/STATE.md`, `.saipen/kitchen/` scratch, `.saipen/logs/`, `.saipen/recovery/`, `.saipen/saitranslate/`, `.saipen/extensions/subs/*/` (instances), `saipenview/_data/` | machine paths, session state, locks, caches, generated translations, sub-instance state | never |

The **canonical memory** is what a successor needs to continue: the board,
the log, the knowledge. The **local** half is what must stay behind: anything
that names this machine or this session.

## Handoff (deterministic export / import)

`saipen stop`/`SHIP` and releases are the handoff points.

- **Export**: `python tools/export_source.py` builds
  `dist/saipenview-src-<version>.tar.gz` from a clean `git archive` plus the
  canonical memory (`.saipen/BOARD.md`, `.saipen/LOG.md`,
  `.saipen/KNOWLEDGE/`, `.saipen/kitchen/digest.md`) and writes
  `MANIFEST.txt` of exactly what went in. Local/runtime/cache content cannot
  enter it by construction.
- **Import** (a fresh clone on this or another machine):
  1. extract the archive,
  2. run `saipen set` — it bootstraps a fresh `.saipen/STATE.md` pointing at
     **this machine's** `saipen_home` (the one thing the export deliberately
     did not carry),
  3. the canonical memory is already present, so the board, the log and the
     knowledge are readable immediately and continuation needs no context
     transfer.

The protocol home is therefore never "resolved from a stale path": each
machine writes its own. A clone without the export has no `.saipen/` at all —
that is the "not initialized" state, and `saipen set` is its fix.

## Verification (run at release)

```text
git check-ignore .saipen/BOARD.md        # must print the path (local-only contract)
git check-ignore .saipen/STATE.md        # must print the path
git ls-files | grep -i "V:\|C:\\"        # must be empty (no local paths tracked)
python tools/export_source.py            # PASS: archive + manifest
```

## Why git check-ignore says ignored

`git check-ignore .saipen/BOARD.md` printing the path is the contract working:
`.saipen/` is ignored **by decision**, and the handoff above is how the memory
travels instead. If the ignore were ever removed, the machine paths would
enter the repository — that is the failure mode this document exists to
prevent.
