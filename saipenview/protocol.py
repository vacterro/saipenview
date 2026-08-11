"""The SAIPEN protocol's closed vocabularies, as this viewer understands them.

Every set here is a copy of a normative list that lives somewhere else --
`saipen/CORE.md`, `extensions/schemas/state.schema.json`,
`tools/validate.py`, `tools/saipen_engine/`. A copy is a liability: the
protocol moves, and a viewer that silently keeps grading against last month's
vocabulary is worse than one that doesn't grade at all, because it reports
confidently.

Two things hold that down:

* `BASELINE_VERSION` names the release these were read from. It is shown in
  the UI next to any conformance verdict, so a verdict is never anonymous.
* `tests/test_protocol_sync.py` reads the canonical files out of a project's
  `saipen_home` when one is reachable on this machine and asserts every set
  below still matches. On a machine without the protocol repo it skips --
  loudly, by name, not by silently passing.

That is the whole contract: the viewer may lag the protocol, but it may not
lag it *quietly*.
"""

from __future__ import annotations

BASELINE_VERSION = "7.223.0"

# CORE § 1.6 phase enum, also the `phase`/`transition_from` enum in
# extensions/schemas/state.schema.json.
PHASES: tuple[str, ...] = (
    "INIT",
    "PLAN",
    "SCOUT",
    "BUILD",
    "VERIFY",
    "REVIEW",
    "SHIP",
    "DONE",
    "BLOCKED",
    "VALIDATE",
    "HUNT",
    "MARKHUNT",
    "ADD",
    "CLEAN",
    "TRANSLATE",
    "PREPARE",
)

# CORE § 1.3 execution modes.
MODES: tuple[str, ...] = ("full", "read-only", "no-publish", "manual-verify")

# CORE § 1.2 required-field set. The schema's `required` array names eight;
# transition_from is the ninth and carries its own exception -- a fresh INIT
# has no previous phase to name. The portable floor (tests/validate.sh) probes
# exactly these nine for the same reason.
REQUIRED_STATE_FIELDS: tuple[str, ...] = (
    "phase",
    "task",
    "next_action",
    "blocker",
    "agent",
    "updated",
    "mode",
    "saipen_version",
    "transition_from",
)

# CORE § 1.2/§ 2.4: the ONE canonical persisted execution-intent enum
# (extensions/schemas/state.schema.json). Replaces the legacy `goal_mode`
# boolean.
EXECUTION_INTENTS: tuple[str, ...] = ("normal", "goal", "converge")

# CORE § 1.2: next_action MUST begin with one of these five. This is the
# whitelist that carries the weight -- the "is it vague?" blacklist is
# evadable by construction.
NEXT_ACTION_PREFIXES: tuple[str, ...] = (
    "WAIT:",
    "saipen ",
    "PHASE ",
    "RUN:",
    "RESUME:",
)

# CORE § 1.2: a WAIT carries a category token from a closed set of seven. The
# token is what mechanically separates a real gate from a vague stop.
WAIT_CATEGORIES: tuple[str, ...] = (
    "manual-verify",
    "destructive-op",
    "first-publish",
    "user brake",
    "blocked",
    "safety valve",
    "init",
)

# CORE § 1.10's closed command list (tools/validate.py's SAIPEN_COMMANDS).
# `userperson` and `improve` joined in the 7.2xx cycle; the shortcut table's
# `hh` also made `hunt` real in 7.148.0. Read this list as the authority on
# what may follow `saipen `, never as "the phases that are missing from
# PHASES".
SAIPEN_COMMANDS: frozenset[str] = frozenset(
    {
        "set",
        "init",
        "continue",
        "goal",
        "plan",
        "clean",
        "translate",
        "hunt",
        "markhunt",
        "prepare",
        "collect",
        "ship",
        "validate",
        "test",
        "crew",
        "status",
        "stop",
        "sub",
        "userperson",
        "improve",
    }
)

# CORE § 1.3: read-only cannot write, so every phase whose work product is a
# file write is unreachable from it.
READ_ONLY_BANNED_PHASES: tuple[str, ...] = (
    "INIT",
    "PLAN",
    "ADD",
    "BUILD",
    "SHIP",
    "CLEAN",
    "TRANSLATE",
)

# CORE § 1.6/§ 1.10: entered by explicit user command from ANY phase, so the
# transition table's FROM row does not restrict them (tools/saipen_engine/
# phases.py ANY_FROM).
ANY_FROM: frozenset[str] = frozenset(
    {"VALIDATE", "MARKHUNT", "CLEAN", "TRANSLATE", "PREPARE", "PLAN", "HUNT"}
)

# CORE § 1.6 transition table (tools/saipen_engine/phases.py VALID_TRANSITIONS).
VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "INIT": ("PLAN", "BLOCKED"),
    "PLAN": ("SCOUT", "BUILD", "DONE", "BLOCKED"),
    "SCOUT": ("BUILD", "BLOCKED"),
    "BUILD": ("VERIFY", "BLOCKED"),
    "VERIFY": ("REVIEW", "SCOUT", "BUILD", "BLOCKED"),
    "REVIEW": ("SHIP", "BUILD", "SCOUT", "BLOCKED"),
    "SHIP": ("DONE", "BUILD", "BLOCKED"),
    "DONE": ("SCOUT", "PLAN", "HUNT", "BLOCKED"),
    "VALIDATE": ("SCOUT", "PLAN", "DONE", "BLOCKED"),
    "HUNT": ("ADD", "PLAN", "SCOUT", "BLOCKED"),
    "MARKHUNT": ("DONE", "BLOCKED"),
    "ADD": ("BUILD", "PLAN", "SCOUT", "DONE", "BLOCKED"),
    "CLEAN": ("DONE", "BLOCKED"),
    "TRANSLATE": ("DONE", "BLOCKED"),
    "PREPARE": ("DONE", "BLOCKED"),
    "BLOCKED": ("PLAN", "SCOUT", "DONE"),
}

# extensions/subs/PROTOCOL.md § 2 status table.
OUTBOX_STATUSES: tuple[str, ...] = ("ready", "draft", "blocked", "reviewed", "stale")

# CORE § 1.2 BOARD.md section headings -- all four MUST be present, even empty.
BOARD_HEADINGS: tuple[str, ...] = ("DOING", "TODO", "DONE", "BLOCKED")

# tools/saipen_engine/board.py KNOWN_FIELDS -- the closed ticket-field set.
# A literal `|` in a description must be escaped `\|`; anything that parses as
# `field: value` but is not in this set is an unknown-field violation.
TICKET_FIELDS: frozenset[str] = frozenset(
    {
        "needs",
        "owner",
        "claim_time",
        "blocker",
        "verify",
        "review_passes",
        "verify_attempts",
        "source_reports",
        "recurrence",
        "weak_model",
    }
)

# CORE § 1.2: the checkbox and the section must agree. `[/]` belongs under
# DOING, `[x]` under DONE, `[ ]` under TODO or BLOCKED -- a blocked ticket is
# still open, so it keeps an empty box. The section IS the status; the
# checkbox is how a human skims it.
CHECKBOX_SECTIONS: dict[str, tuple[str, ...]] = {
    " ": ("TODO", "BLOCKED"),
    "/": ("DOING",),
    "x": ("DONE",),
}

# tools/saipen_engine/phases.py TICKET_BEARING_PHASES: the five phases whose
# next_action MUST name a ticket.
TICKET_PHASES: frozenset[str] = frozenset(
    {"SCOUT", "BUILD", "VERIFY", "REVIEW", "SHIP"}
)

# tools/saipen_engine/log.py VALID_TAXONOMIES -- the closed set new LOG events
# may be built with. Older history legitimately carries other verbs (notably
# `H`), so the *reader* allowance is wider than this; this set is what a
# writer may produce.
LOG_TAXONOMIES: frozenset[str] = frozenset(
    {"DEC", "RUN", "WAIT", "REVERT", "NOTE", "OPS"}
)

# tools/validate.py's taxonomy allowance when READING a log: anything outside
# this set warns for new entries. Kept distinct from LOG_TAXONOMIES on purpose
# -- one is the write contract, the other is the read tolerance.
LOG_READ_TAXONOMIES: frozenset[str] = frozenset({"RUN", "DEC", "H"})

# CORE § 1.2's tolerance for a LOG clock ahead of real UTC. tools/validate.py
# LOG_CLOCK_SLACK = 300 (5 minutes): the 3-hour bound was exactly what let a
# guessed (not read) clock sail through for ~30 minutes and still look clean.
LOG_CLOCK_SLACK_SECONDS = 300

# tools/validate.py PACKAGE_HANDOFF_FIELDS: every field a `status: ready`
# OUTBOX entry MUST bind before a collect may consume it. Absence of any of
# them is an incomplete package, not a judgement call.
PACKAGE_HANDOFF_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "producer",
        "source_head",
        "source_tree_fingerprint",
        "role_revision",
        "coverage",
        "payload",
        "verified",
        "instructions",
    }
)

# extensions/schemas/state.schema.json x-current-schema-version: the STATE
# revision whose `last_event`/`style_contract` markers are REQUIRED once a
# checkpoint writes it.
STATE_SCHEMA_VERSION = 3

# CORE § 2.4 safety-valve ceilings.
GOAL_WAVE_CAP = 3
GOAL_TICKET_CAP = 20
