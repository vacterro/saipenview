"""The SAIPEN protocol's closed vocabularies, as this viewer understands them.

Every set here is a copy of a normative list that lives somewhere else --
`saipen/RFC.md`, `extensions/schemas/state.schema.json`, `tools/validate.py`.
A copy is a liability: the protocol moves, and a viewer that silently keeps
grading against last month's vocabulary is worse than one that doesn't grade
at all, because it reports confidently.

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

BASELINE_VERSION = "7.205.2"

# RFC § 1.6 phase enum, also the `phase`/`transition_from` enum in
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

# RFC § 1.3 execution modes.
MODES: tuple[str, ...] = ("full", "read-only", "no-publish", "manual-verify")

# RFC § 1.2 required-field set. The schema's `required` array names eight;
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

# RFC § 1.2: next_action MUST begin with one of these five. This is the
# whitelist that carries the weight -- the "is it vague?" blacklist is
# evadable by construction.
NEXT_ACTION_PREFIXES: tuple[str, ...] = (
    "WAIT:",
    "saipen ",
    "PHASE ",
    "RUN:",
    "RESUME:",
)

# RFC § 1.2: a WAIT carries a category token from a closed set of seven. The
# token is what mechanically separates a real gate from a vague stop, and it
# tells the human what kind of answer unblocks the project.
WAIT_CATEGORIES: tuple[str, ...] = (
    "manual-verify",
    "destructive-op",
    "first-publish",
    "user brake",
    "blocked",
    "safety valve",
    "init",
)

# RFC § 1.10's closed command list. Most phases (ADD/BUILD/SCOUT...) are
# reached autonomously and are never words a next_action may invoke -- but
# "phase" and "command" are separate namespaces, not opposites: a few phases
# have a command of the same name, and HUNT gained one in 7.148.0. Read this
# list as the authority on what may follow `saipen `, never as "the phases
# that are missing from PHASES".
SAIPEN_COMMANDS: frozenset[str] = frozenset(
    {
        "set",
        "init",
        "continue",
        "goal",
        "plan",
        "clean",
        "translate",
        # Added by SAIPEN 7.148.0: the shortcut table had `hh` routing to HUNT,
        # a phase with no command behind it, so `saipen hunt` became real.
        "hunt",
        "markhunt",
        "prepare",
        # RFC § 1.10 `saipen collect <producer>`: consume one named producer's
        # already-prepared handoff. Distinct from the extension-wide
        # `saipen sub collect`, which is `sub` plus an argument, not this verb.
        "collect",
        "ship",
        "validate",
        # Added by SAIPEN 7.191.0/7.194.0: `saipen test` runs a project's
        # declared suite (read-only, reports PASS/FAIL, never fixes) and
        # `saipen crew` walks the whole factory circuit in order.
        "test",
        "crew",
        "status",
        "stop",
        "sub",
    }
)

# RFC § 1.3: read-only cannot write, so every phase whose work product is a
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

# RFC § 1.6/§ 1.10: entered by explicit user command from ANY phase, so the
# transition table's FROM row does not restrict them. SHIP is deliberately
# absent: `saipen ship` is a command from anywhere, but `phase: SHIP` is
# reachable only from REVIEW. A command is not a transition.
# HUNT joined this set when `saipen hunt` became a real command: RFC § 2.1
# says it "enters HUNT from any phase regardless of board state -- that command
# exists precisely to run the sweep now instead of waiting for this section to
# reach it". Read from the RFC and cross-checked against tools/validate.py's
# own ANY_FROM before copying, per T-097's rule.
ANY_FROM: frozenset[str] = frozenset(
    {"VALIDATE", "MARKHUNT", "CLEAN", "TRANSLATE", "PREPARE", "PLAN", "HUNT"}
)

# RFC § 1.6 transition table.
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

# RFC § 1.2 BOARD.md section headings -- all four MUST be present, even empty.
BOARD_HEADINGS: tuple[str, ...] = ("DOING", "TODO", "DONE", "BLOCKED")

# RFC § 2.4 safety-valve ceilings.
GOAL_WAVE_CAP = 3
GOAL_TICKET_CAP = 20

# RFC § 1.2: the checkbox and the section must agree. `[/]` belongs under
# DOING, `[x]` under DONE, `[ ]` under TODO or BLOCKED -- a blocked ticket is
# still open, so it keeps an empty box.
CHECKBOX_SECTIONS: dict[str, tuple[str, ...]] = {
    " ": ("TODO", "BLOCKED"),
    "/": ("DOING",),
    "x": ("DONE",),
}

# Phases that are working a specific ticket and so SHOULD name one.
TICKET_PHASES: tuple[str, ...] = ("SCOUT", "BUILD", "VERIFY", "REVIEW", "SHIP")
