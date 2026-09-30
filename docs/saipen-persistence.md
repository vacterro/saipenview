# SAIPEN memory persistence contract (T-172)

## Decision

This project's `.saipen/` is **machine-local by written contract**, with two
named exceptions that travel via git. It is a written decision, not a silent
`.gitignore` accident — the paragraphs below say why, and the handoff that
replaces git is specified at the bottom.

The exceptions are the **audit receipts** and the **closure travel** of
canonical memory, both added by the T-832/T-833 release amendment and both
committed by the release executor. Before that amendment the whole of `.saipen/`
was local-only; the two tables in [Authority receipts](#authority-receipts-amendment-t-832)
below are the current, authoritative answer, and `tests/test_persistence_contract.py`
pins exactly them.

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
| Canonical memory | `.saipen/BOARD.md`, `.saipen/LOG.md`, `.saipen/KNOWLEDGE/`, `.saipen/kitchen/digest.md` | work surface, audit trail, durable architecture notes, last-session digest | `KNOWLEDGE/`/`digest.md` via `tools/export_source.py`; `BOARD.md`/`LOG.md` additionally via the closure commit (T-832) |
| Local / ephemeral | `.saipen/STATE.md` (outside the closure commit), `.saipen/kitchen/` scratch, `.saipen/recovery/`, `.saipen/saitranslate/`, `.saipen/extensions/subs/*/` (instances), `saipenview/_data/` | machine paths, session state, locks, caches, generated translations, sub-instance state | never |

The **canonical memory** is what a successor needs to continue: the board,
the log, the knowledge. The **local** half is what must stay behind: anything
that names this machine or this session.

## Authority receipts (amendment, T-832)

The engine's release contract (`saipen_engine.release_contract.
source_authority_paths`) defines one further surface that **must** travel via
git: the source-receipt authority trees. A release commit that drops them
would leave a fresh clone unable to prove that every audited finding was
dispositioned, so the executor commits them on ship:

| Kind | Location | Contents | Travels |
|------|----------|----------|---------|
| Authority receipts | `.saipen/intake/`, `.saipen/archive/source/`, `.saipen/kitchen/release_scope/` | audit-handoff source receipts, requirement contracts, coverage dispositions, per-ticket release scope records | via git, committed by the release executor |
| Closure travel | `.saipen/STATE.md`, `.saipen/BOARD.md`, `.saipen/LOG.md`, `.saipen/logs/` (sealed segments), `.saipen/kitchen/digest.md`, `.saipen/kitchen/release_receipt.json` | canonical phase state, board, event history, digest and the published release receipt | via git, committed by the release executor in the closure commit |

These files are immutable audit evidence pinned by content digests
(`verify_integrity` refuses any body drift) and are committed exactly as
received — receipt prose may quote the machine paths the audit observed,
which is inert description, not live state. The closure-travel row exists
because the release executor's closure commit must carry the canonical
memory: a released tag without the E-### history cannot run recovery from a
fresh clone (the sealed-segment incident class). `.saipen/recovery/`, the
kitchen scratch, `.saipen/saitranslate/` and the sub-instance state remain
machine-local: they never travel via git and continue to move only through
the export/import handoff below.

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
# The closure-travel exceptions are NOT ignored (they ride the closure commit)
git check-ignore --no-index .saipen/BOARD.md   # must print nothing
git check-ignore --no-index .saipen/STATE.md   # must print nothing
# Machine state stays local, or it would carry this machine's paths into git
git check-ignore --no-index .saipen/recovery/x.json      # must print the path
git check-ignore --no-index .saipen/saitranslate/x.json  # must print the path
python tools/export_source.py                  # PASS: archive + manifest
```

`tests/test_persistence_contract.py` runs the same commands, so the document and
the suite can never drift into asserting two different contracts.

## Why git check-ignore says what it says

For a machine-local path (`recovery/`, `saitranslate/`, `KNOWLEDGE/`, sub-instance
state), `git check-ignore` printing the path **is** the contract working: those
never enter the repository and the handoff above is how the memory travels
instead.

For the closure-travel surfaces (`.saipen/STATE.md`, `BOARD.md`, `LOG.md`,
`logs/`) `check-ignore` printing **nothing** is the contract working: they are
negated in `.gitignore` so the release executor's closure commit can carry them.
If that negation were ever removed, a released tag would lose the E-### history
it needs to run recovery from a fresh clone.
