# Conformance legacy policy (T-187)

SAIPENVIEW's own `.saipen/` memory carries history written before several
conformance rules hardened. The validator is the canonical grader and is NOT
modified to grandfather this project; instead each legacy defect is handled by
one of three documented, deterministic treatments below. Every treatment is
referenced from the artifact it touched.

## Cutoff

The legacy cutoff is **02.08.26 07:00 UTC** (v0.1.7 era). Entries before that
time were written against an earlier LOG skeleton and an earlier rule set.
The mechanical migrations below are applied once, preserve event IDs, text and
meaning, and are logged in LOG.md.

## Treatments

### 1. Legacy LOG skeleton lines (migrate)

Lines written in the pre-skeleton format (`2026-08-01T12:48:30Z [E-130] ...`,
date after the id, `| RUN:` separators, missing time on `DD.MM.YY`) are
mechanically migrated to the current skeleton `- DD.MM.YY HH:MM [E-N]
[parent: ...] [T-...] [agent: ...] TAXONOMY: text` preserving the event ID,
the text and the meaning. Where a timestamp component is missing it is
reconstructed deterministically from the neighbouring entries and the
reconstruction is noted in the migration DEC (E-428).

### 2. Duplicate/stale event or ticket IDs (quarantine verbatim)

A stale writer branch (reused E-### / duplicate T-###) is moved verbatim into
`.saipen/recovery/` and removed from the active graph, with a `# RECOVERY
SPLICE` marker and a canonical DEC in the active LOG. Evidence is preserved
byte-for-byte; no canonical ID is renumbered.

### 3. Rules that postdate the entry (grandfather marker)

Where a rule could not have been satisfied when the line was written and the
facts are unrecoverable, the line carries an explicit marker naming the
grandfathering, e.g.:

- `| verify: grandfathered 07.08.26 -- closed before the verify-required rule (see docs/conformance-legacy.md)`
  on legacy `## DONE` tickets that predate the verify field being required.
- `tickets=none (legacy line predates the tickets= closure rule; list never recorded)`
  on legacy markhunt completion lines whose closure list was never written.

The marker is the policy: it is explicit, bounded (only lines before the
cutoff), and testable (a NEW line carrying a marker FAILs, because the rule
was in force).

## Testability

A regression test in `tests/test_conformance_legacy.py` pins the policy:
- the cutoff date is constant;
- a synthetic NEW skeleton violation still FAILs (the migration did not
  disable the rule);
- a synthetic NEW DONE ticket without verify still FAILs.
