"""Grades one `.saipen/` project against the protocol, without running it.

The viewer already showed what a project *says*: phase, task, next_action,
board counts. This module answers the other half -- whether what it says is
legal. A project can look perfectly healthy in the list (`phase: DONE`,
`next_action: WAIT: ...`) while `tools/validate.py` would reject it, and until
this existed the viewer had no way to tell those two apart.

Scope, deliberately: this is a **read-only second opinion**, not a
reimplementation of `tools/validate.py`. It re-checks the rules that can be
decided from a project's own `.saipen/` files alone -- state shape, board
grammar, log ordering, sub OUTBOX vocabulary. It does not check the protocol
repo's own internals (cross-document drift, CONFORMANCE row IDs, shipped-doc
coverage); those need the protocol sources, not a project.

Where it disagrees with `tools/validate.py`, the validator wins. This is why
`FINDINGS` carry a `cite` and why `protocol.BASELINE_VERSION` is shown next to
every verdict: a second opinion that hides which edition it read is worse than
no second opinion.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from saipenview import protocol
from saipenview.textio import encoding_of, read_doc

FAIL = "fail"
WARN = "warn"

_STATE_FILE = ".saipen/STATE.md"
_BOARD_FILE = ".saipen/BOARD.md"
_LOG_FILE = ".saipen/LOG.md"

# RFC § 1.2 board grammar. The four-section headings, the ticket line, and the
# closed field list that follows the description after ` | `.
_HEADING_RE = re.compile(r"^##\s+(\S.*?)\s*$")
_TICKET_RE = re.compile(r"^- \[([ x/])\] (T-\d+)\s*(.*)$")
_LOOSE_TICKET_RE = re.compile(r"^- \[([ x/])\] (\S+)\s*(.*)$")
_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
# The closed ticket-field set is OWNED by protocol.py, synced mechanically from
# tools/saipen_engine/board.py by tests/test_protocol_sync.py. A copy here
# would be the second stale copy this file shipped before the mission.
_KNOWN_TICKET_FIELDS = protocol.TICKET_FIELDS
# A literal pipe inside a description is escaped `\|`; hide it before splitting
# so an escaped pipe never invents a field.
_PIPE_SENTINEL = "\x00"

_LOG_ENTRY_RE = re.compile(r"^-\s+(\d{2}\.\d{2}\.\d{2})\s+(\d{2}:\d{2})\s+\[E-(\d+)\]")
_LOG_ANY_EVENT_RE = re.compile(r"^-\s+.*?\[E-(\d+)\]")
# RFC § 1.2's Event Graph skeleton, as `tools/validate.py` enforces it. This
# grader used to look only at lines that already carried an `[E-###]` and skip
# everything else -- so a line that was not an entry at all was invisible to
# it, and the project came back clean while the canonical validator FAILed on
# exactly that line. Coverage, not content: the same shape as a check that
# walks a curated file list instead of the shipped surface.
_LOG_SKELETON_RE = re.compile(
    r"^- (?:\d{2}\.\d{2}\.\d{2} \d{2}:\d{2} )?"
    r"\[E-(\d+)\]"
    r"(?: \[parent: E-(\d+)\])?"
    r"(?: \[(T-[^\]]*)\])?"
    r"(?: \[agent: [^\]]+\])?"
    r"(?: \[op: [^\]]+\])?"
    r" ([A-Z]+): (.*)$"
)
# The taxonomy is closed for new entries; older logs carry other verbs, so
# this is a warning rather than a failure, the same split the validator makes.
# Owned by protocol.py (synced from tools/validate.py's read allowance).
_LOG_TAXONOMY = protocol.LOG_READ_TAXONOMIES
_TICKET_REF_RE = re.compile(r"^T-(?:\d+|none)$")
_ISO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})Z$")

# Beyond this the `updated` stamp stops describing a live project. Not a
# protocol rule -- purely the viewer telling a human "nobody has touched this".
_STALE_DAYS = 30
# A STATE `updated` stamp ahead of UTC. Canonical validate.py does NOT bound
# `updated` against the clock (it checks only the UTC form); this is the
# viewer's own honesty heuristic and is cited as such, never as a protocol rule.
_FUTURE_UPDATED_WARN_HOURS = 3


@dataclass
class Finding:
    """One rule verdict. `rule` is stable and machine-readable; `message` is
    for a human; `cite` names the clause so the human can go read it."""

    rule: str
    severity: str
    message: str
    cite: str
    file: str = ""
    line: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    baseline: str = protocol.BASELINE_VERSION

    @property
    def fails(self) -> int:
        return sum(1 for f in self.findings if f.severity == FAIL)

    @property
    def warns(self) -> int:
        return sum(1 for f in self.findings if f.severity == WARN)

    @property
    def verdict(self) -> str:
        if self.fails:
            return FAIL
        if self.warns:
            return WARN
        return "pass"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "fails": self.fails,
            "warns": self.warns,
            "baseline": self.baseline,
            "findings": [f.to_dict() for f in self.findings],
        }


class _Collector:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def fail(self, rule, message, cite, file="", line=0) -> None:
        self.findings.append(Finding(rule, FAIL, message, cite, file, line))

    def warn(self, rule, message, cite, file="", line=0) -> None:
        self.findings.append(Finding(rule, WARN, message, cite, file, line))


# --- STATE.md -------------------------------------------------------------


def _parse_utc(stamp: str) -> datetime.datetime | None:
    m = _ISO_RE.match(stamp.strip())
    if not m:
        return None
    try:
        return datetime.datetime.strptime(stamp.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


def _is_int(value: str | None) -> bool:
    if value is None:
        return False
    try:
        int(str(value).strip())
    except (TypeError, ValueError):
        return False
    return True


def check_state(state: dict[str, str], root: Path, c: _Collector) -> None:
    state_path = root / ".saipen" / "STATE.md"

    if not state_path.is_file():
        c.fail(
            "state.missing",
            "no .saipen/STATE.md -- a cold agent has nothing to boot from",
            "RFC § 1.2",
            _STATE_FILE,
        )
        return

    enc = encoding_of(state_path)
    if enc != "utf-8":
        # This viewer reads it anyway. Nothing else does: tools/validate.py
        # opens it as utf-8-sig and the portable floor greps it byte-wise, so
        # a UTF-16 STATE.md fails every other tool while looking fine here.
        c.fail(
            "state.encoding",
            f"STATE.md is {enc}, not plain UTF-8 -- readable here, but "
            f"tools/validate.py and the grep-based portable floor cannot "
            f"read it, so the project is unvalidatable everywhere else",
            "KNOWLEDGE/traps.md",
            _STATE_FILE,
        )

    if not state:
        c.fail(
            "state.frontmatter",
            "STATE.md has no parsable `---` frontmatter block",
            "RFC § 1.2",
            _STATE_FILE,
        )
        return

    # Duplicated frontmatter keys: the closed single-valued grammar MUST NOT
    # silently pick a winner (repair mission P1).
    seen_keys: set[str] = set()
    for line in read_doc(state_path).splitlines():
        line = line.strip()
        if line.startswith("---") or ":" not in line:
            continue
        key = line.partition(":")[0].strip()
        if key in seen_keys:
            c.fail(
                "state.duplicate_field",
                f"STATE.md defines {key!r} more than once -- single-valued "
                f"grammar MUST NOT silently pick a winner",
                "RFC § 1.2",
                _STATE_FILE,
            )
        seen_keys.add(key)

    phase = state.get("phase")
    mode = state.get("mode")
    next_action = state.get("next_action", "")

    # RFC § 1.2's nine. transition_from carries the fresh-INIT exception:
    # there is no previous phase to name at bootstrap.
    for fname in protocol.REQUIRED_STATE_FIELDS:
        if fname == "transition_from" and phase == "INIT":
            continue
        if fname not in state or state.get(fname, "") == "":
            c.fail(
                f"state.missing.{fname}",
                f"STATE.md missing required field `{fname}`",
                "RFC § 1.2",
                _STATE_FILE,
            )

    if phase and phase not in protocol.PHASES:
        c.fail(
            "state.phase.enum",
            f"phase {phase!r} is not one of the 16 enum values",
            "RFC § 1.6",
            _STATE_FILE,
        )
    if mode and mode not in protocol.MODES:
        c.fail(
            "state.mode.enum",
            f"mode {mode!r} is not one of {'/'.join(protocol.MODES)}",
            "RFC § 1.3",
            _STATE_FILE,
        )

    t_from = state.get("transition_from")
    if t_from and t_from not in protocol.PHASES:
        c.fail(
            "state.transition_from.enum",
            f"transition_from {t_from!r} is not one of the 16 enum values",
            "RFC § 1.6",
            _STATE_FILE,
        )
    elif (
        t_from
        and phase
        and t_from != phase
        and phase in protocol.PHASES
        and phase not in protocol.ANY_FROM
    ):
        allowed = protocol.VALID_TRANSITIONS.get(t_from, ())
        if phase not in allowed:
            c.fail(
                "state.transition.illegal",
                f"{t_from} -> {phase} is not in the transition table "
                f"({t_from} allows {'/'.join(allowed) or 'nothing'})",
                "RFC § 1.6",
                _STATE_FILE,
            )

    if mode == "read-only" and phase in protocol.READ_ONLY_BANNED_PHASES:
        c.fail(
            "state.readonly.phase",
            f"mode: read-only cannot be in {phase} -- that phase's work "
            f"product is a file write",
            "RFC § 1.3",
            _STATE_FILE,
        )

    if state.get("saipen_version") and not _is_int(state["saipen_version"]):
        c.fail(
            "state.saipen_version.type",
            f"saipen_version {state['saipen_version']!r} is not an integer",
            "RFC § 1.2",
            _STATE_FILE,
        )

    _check_next_action(next_action, c)
    _check_goal_mode(state, c)
    _check_updated(state.get("updated", ""), c)

    # CORE § 1.2's voice marker: at the current schema revision the marker is
    # REQUIRED, not "validate it when present". Its VALUE is decided by
    # STYLE.md (outside this project's own files, so the second opinion can
    # only check presence); the canonical validator checks the value.
    try:
        sv_int = int(state.get("schema_version", ""))
    except (TypeError, ValueError):
        sv_int = None
    if (
        sv_int == protocol.STATE_SCHEMA_VERSION
        and not str(state.get("style_contract", "")).strip()
    ):
        c.fail(
            "state.style_contract.missing",
            f"STATE.md schema_version {protocol.STATE_SCHEMA_VERSION} requires "
            f"a style_contract marker -- a checkpoint that never opened "
            f"STYLE.md cannot write it, and absence is that failure",
            "RFC § 1.2",
            _STATE_FILE,
        )

    if (
        phase in protocol.TICKET_PHASES
        and state.get("task", "none") in ("none", "", None)
        and "ticket-less maintenance" not in next_action.lower()
    ):
        c.warn(
            "state.task.absent",
            f"phase {phase} works a specific ticket but task is none",
            "RFC § 1.2",
            _STATE_FILE,
        )


def _check_next_action(next_action: str, c: _Collector) -> None:
    if not next_action:
        return
    if not next_action.startswith(protocol.NEXT_ACTION_PREFIXES):
        c.fail(
            "next_action.prefix",
            f"next_action must start with one of "
            f"{'/'.join(protocol.NEXT_ACTION_PREFIXES)} -- a cold agent "
            f"cannot execute {next_action!r}",
            "RFC § 1.2",
            _STATE_FILE,
        )
        return

    if next_action.startswith("WAIT:"):
        body = next_action[len("WAIT:") :].strip().lower()
        if not any(body.startswith(cat) for cat in protocol.WAIT_CATEGORIES):
            c.fail(
                "next_action.wait.category",
                f"WAIT carries no category token -- must be "
                f"`WAIT: <category> -- <question>` with category one of "
                f"{'/'.join(protocol.WAIT_CATEGORIES)}",
                "RFC § 1.2",
                _STATE_FILE,
            )
        # CORE § 1.2 bounds a WAIT to ONE sentence: a stop instruction
        # carrying session status or queued work is read by the next agent as
        # a work queue. Same shape as the canonical second-sentence check --
        # a period followed by whitespace + a capital or backtick.
        wait_body = re.sub(
            r"\s*\[[^\]]*\]\s*$", "", next_action[len("WAIT:") :].strip()
        )
        if re.search(r"\.\s+(?=[A-Z`])", wait_body):
            c.fail(
                "next_action.wait.one_sentence",
                "WAIT body starts a second sentence -- a stop instruction "
                "carrying session status or queued work is one the next agent "
                "executes as a work queue; keep it to one sentence",
                "RFC § 1.2",
                _STATE_FILE,
            )
    elif "?" in next_action:
        c.fail(
            "next_action.question",
            "next_action asks a question outside a WAIT: -- questions belong "
            "in a categorised WAIT so the human knows what unblocks it",
            "RFC § 1.2",
            _STATE_FILE,
        )

    if next_action.startswith("saipen "):
        rest = next_action[len("saipen ") :].split()
        verb = rest[0].strip(".\"'") if rest else ""
        if verb and verb not in protocol.SAIPEN_COMMANDS:
            c.fail(
                "next_action.command",
                f"`saipen {verb}` is not a defined command -- a cold agent "
                f"must decline an unrecognised command and stop. Phases like "
                f"HUNT/ADD are reached autonomously, never invoked by name",
                "RFC § 1.10",
                _STATE_FILE,
            )


def _check_goal_mode(state: dict[str, str], c: _Collector) -> None:
    # CORE § 2.4's canonical intent enum. The legacy `goal_mode` boolean stays
    # readable during migration; the counters rule is the same for both.
    intent = str(state.get("execution_intent", "")).strip().lower()
    legacy_goal = str(state.get("goal_mode", "")).strip().lower() == "true"
    if intent and intent not in protocol.EXECUTION_INTENTS:
        c.fail(
            "state.execution_intent.enum",
            f"execution_intent {state['execution_intent']!r} is not one of "
            f"{'/'.join(protocol.EXECUTION_INTENTS)}",
            "RFC § 2.4",
            _STATE_FILE,
        )
        return
    if intent != "goal" and not legacy_goal:
        return
    for counter in ("goal_waves", "goal_tickets"):
        if not _is_int(state.get(counter)):
            c.fail(
                f"goal.{counter}",
                f"goal intent is running but {counter} is missing or not an "
                f"integer -- the safety valve cannot survive a restart without it",
                "RFC § 2.4",
                _STATE_FILE,
            )
    waves, tickets = state.get("goal_waves"), state.get("goal_tickets")
    if _is_int(waves) and int(waves) > protocol.GOAL_WAVE_CAP:
        c.fail(
            "goal.waves.cap",
            f"goal_waves {waves} exceeds the cap of "
            f"{protocol.GOAL_WAVE_CAP} -- the valve should already have tripped",
            "RFC § 2.4",
            _STATE_FILE,
        )
    if _is_int(tickets) and int(tickets) > protocol.GOAL_TICKET_CAP:
        c.fail(
            "goal.tickets.cap",
            f"goal_tickets {tickets} exceeds the cap of "
            f"{protocol.GOAL_TICKET_CAP} -- the valve should already have tripped",
            "RFC § 2.4",
            _STATE_FILE,
        )


def _check_updated(updated: str, c: _Collector) -> None:
    if not updated:
        return
    stamp = _parse_utc(updated)
    if stamp is None:
        c.fail(
            "state.updated.format",
            f"updated {updated!r} is not the required UTC form YYYY-MM-DDTHH:MM:SSZ",
            "RFC § 1.2",
            _STATE_FILE,
        )
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    ahead = (stamp - now).total_seconds() / 3600
    if ahead > _FUTURE_UPDATED_WARN_HOURS:
        c.warn(
            "state.updated.future",
            f"updated is {ahead:.1f}h in the future -- a local clock was "
            f"written where UTC was required (viewer heuristic; canonical "
            f"validate.py bounds only the UTC form, not the clock)",
            "viewer heuristic",
            _STATE_FILE,
        )
    elif (now - stamp).days > _STALE_DAYS:
        c.warn(
            "state.updated.stale",
            f"last checkpoint was {(now - stamp).days} days ago",
            "RFC § 1.5",
            _STATE_FILE,
        )


# --- BOARD.md -------------------------------------------------------------


@dataclass
class BoardTicket:
    ticket_id: str
    checkbox: str
    section: str
    line_no: int
    needs: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)


def parse_board_strict(text: str) -> tuple[dict[str, BoardTicket], list[str], list]:
    """Parse BOARD.md at RFC § 1.2's grammar, keeping line numbers and
    malformed lines. Returns (tickets by id, headings in order, problems)
    where a problem is (line_no, kind, detail)."""
    tickets: dict[str, BoardTicket] = {}
    headings: list[str] = []
    problems: list[tuple[int, str, str]] = []
    section = ""

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(1)
            headings.append(section)
            continue
        if not line.startswith("- ["):
            continue
        masked = line.replace("\\|", _PIPE_SENTINEL)
        m = _TICKET_RE.match(masked)
        if not m:
            loose = _LOOSE_TICKET_RE.match(masked)
            kind = "bad_id" if loose else "bad_shape"
            problems.append((line_no, kind, line))
            continue
        checkbox, tid, rest = m.groups()
        if tid in tickets:
            problems.append(
                (line_no, "duplicate", f"{tid} (first at line {tickets[tid].line_no})")
            )
            continue
        parts = [p.strip() for p in rest.split(" | ")]
        needs: list[str] = []
        fields: dict[str, str] = {}
        for part in parts[1:]:
            fm = _FIELD_RE.match(part)
            if not fm or fm.group(1) not in _KNOWN_TICKET_FIELDS:
                problems.append(
                    (
                        line_no,
                        "unknown_field",
                        f"{tid}: {part.replace(_PIPE_SENTINEL, '|')!r}",
                    )
                )
                continue
            if fm.group(1) in fields:
                # Closed single-valued grammar: duplicated authority MUST NOT
                # silently pick a winner (repair mission P1).
                problems.append(
                    (
                        line_no,
                        "duplicate_field",
                        f"{tid}: field {fm.group(1)} appears more than once",
                    )
                )
                continue
            fields[fm.group(1)] = fm.group(2)
            if fm.group(1) == "needs":
                needs = re.findall(r"T-\d+", fm.group(2))
        tickets[tid] = BoardTicket(tid, checkbox, section, line_no, needs, fields)

    return tickets, headings, problems


def check_board(root: Path, c: _Collector) -> dict[str, BoardTicket]:
    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        c.fail(
            "board.missing",
            "no .saipen/BOARD.md -- there is no work surface to pick from",
            "RFC § 1.2",
            _BOARD_FILE,
        )
        return {}

    enc = encoding_of(board_path)
    if enc != "utf-8":
        c.fail(
            "board.encoding",
            f"BOARD.md is {enc}, not plain UTF-8 -- unreadable to "
            f"tools/validate.py and the portable floor",
            "KNOWLEDGE/traps.md",
            _BOARD_FILE,
        )

    tickets, headings, problems = parse_board_strict(read_doc(board_path))

    for line_no, kind, detail in problems:
        if kind == "duplicate":
            c.fail(
                "board.duplicate",
                f"duplicate ticket ID {detail} -- a status change must MOVE "
                f"the line, never copy it",
                "RFC § 1.2",
                _BOARD_FILE,
                line_no,
            )
        elif kind == "duplicate_field":
            c.fail(
                "board.ticket.duplicate_field",
                f"duplicate closed ticket field: {detail} -- single-valued "
                f"grammar MUST NOT silently pick a winner",
                "RFC § 1.2",
                _BOARD_FILE,
                line_no,
            )
        elif kind == "bad_id":
            c.fail(
                "board.ticket.id",
                f"ticket line has no T-### id: {detail!r}",
                "RFC § 1.2",
                _BOARD_FILE,
                line_no,
            )
        elif kind == "bad_shape":
            c.fail(
                "board.ticket.shape",
                f"line does not match `- [ ] T-### description`: {detail!r}",
                "RFC § 1.2",
                _BOARD_FILE,
                line_no,
            )
        else:
            c.fail(
                "board.ticket.field",
                f"unrecognised ticket field {detail} -- the field list is "
                f"closed (needs/owner/claim_time/blocker/verify/review_passes/"
                f"verify_attempts/source_reports/recurrence/weak_model); "
                f"a literal | in a description must be escaped as \\|",
                "RFC § 1.2",
                _BOARD_FILE,
                line_no,
            )

    for required in protocol.BOARD_HEADINGS:
        count = headings.count(required)
        if count == 0:
            c.fail(
                "board.heading.missing",
                f"missing required section heading ## {required}",
                "RFC § 1.2",
                _BOARD_FILE,
            )
        elif count > 1:
            c.fail(
                "board.heading.duplicate",
                f"section heading ## {required} appears {count} times -- "
                f"duplicate status buckets split the work surface",
                "RFC § 1.2",
                _BOARD_FILE,
            )

    for tid, t in tickets.items():
        if t.section not in protocol.BOARD_HEADINGS:
            c.fail(
                "board.ticket.section",
                f"{tid} sits under `## {t.section or '(no heading)'}` -- not "
                f"one of the four sections",
                "RFC § 1.2",
                _BOARD_FILE,
                t.line_no,
            )
            continue
        expected = protocol.CHECKBOX_SECTIONS.get(t.checkbox, ())
        if expected and t.section not in expected:
            c.fail(
                "board.checkbox.section",
                f"{tid} is `[{t.checkbox}]` under ## {t.section} -- that "
                f"checkbox belongs under {' or '.join(expected)}",
                "RFC § 1.2",
                _BOARD_FILE,
                t.line_no,
            )

        # CORE § 1.2 blocker invariant: `## BLOCKED` requires a non-empty
        # `| blocker:` field, and a blocker field ANYWHERE ELSE is active
        # blocked-state data riding on an open ticket -- a malformed status
        # that must fail, never influence routing.
        if t.section == "BLOCKED" and not str(t.fields.get("blocker", "")).strip():
            c.fail(
                "board.blocked.requires_blocker",
                f"{tid} sits under ## BLOCKED without a non-empty "
                f"| blocker: field -- the section claims blocked, the line "
                f"names no reason",
                "RFC § 1.2",
                _BOARD_FILE,
                t.line_no,
            )
        if t.section != "BLOCKED" and "blocker" in t.fields:
            c.fail(
                "board.blocker.outside_blocked",
                f"{tid} carries | blocker: outside ## BLOCKED -- blocker is "
                f"active blocked-state data, not advisory history",
                "RFC § 1.2",
                _BOARD_FILE,
                t.line_no,
            )

        # A ticket in ## DONE is a completion claim, and the protocol requires
        # the evidence that says what met it: `| verify:` names it. Absence is
        # indistinguishable from never tested.
        if t.section == "DONE" and not t.fields.get("verify", "").strip():
            c.fail(
                "board.done.requires_verify",
                f"{tid} sits under ## DONE with no | verify: evidence -- a "
                f"completion claim with no evidence attached is "
                f"indistinguishable from one that was never tested",
                "RFC § 1.2",
                _BOARD_FILE,
                t.line_no,
            )

    doing = [t for t in tickets.values() if t.section == "DOING"]
    if len(doing) > 1:
        c.fail(
            "board.doing.multiple",
            f"{len(doing)} tickets claimed in ## DOING "
            f"({', '.join(sorted(t.ticket_id for t in doing))}) -- at most one",
            "RFC § 1.2",
            _BOARD_FILE,
        )

    dangling = [
        f"{tid} needs {ref}"
        for tid, t in tickets.items()
        for ref in t.needs
        if ref not in tickets
    ]
    if dangling:
        c.fail(
            "board.needs.dangling",
            "dependency on a ticket that does not exist: "
            + "; ".join(sorted(dangling))
            + " -- leaves the Pick Rule permanently unsatisfiable",
            "RFC § 1.2",
            _BOARD_FILE,
        )

    # Kahn's algorithm: whatever cannot be removed is in a cycle.
    remaining = dict(tickets)
    progress = True
    while remaining and progress:
        progress = False
        for tid in list(remaining):
            if not any(ref in remaining for ref in remaining[tid].needs):
                del remaining[tid]
                progress = True
    if remaining:
        c.fail(
            "board.needs.cycle",
            "cyclic needs: dependencies involving " + ", ".join(sorted(remaining)),
            "RFC § 1.2",
            _BOARD_FILE,
        )

    return tickets


# --- cross-file -----------------------------------------------------------


def check_cross(
    state: dict[str, str], tickets: dict[str, BoardTicket], root: Path, c: _Collector
) -> None:
    task = (state.get("task") or "none").strip()
    phase = state.get("phase")
    next_action = state.get("next_action", "")

    task_ids = re.findall(r"T-\d+", task)
    doing = [t for t in tickets.values() if t.section == "DOING"]
    for tid in task_ids:
        if tid not in tickets:
            c.fail(
                "cross.task.unknown",
                f"STATE names task {tid}, which is not on BOARD.md",
                "RFC § 1.5",
                _STATE_FILE,
            )
            continue
        t = tickets[tid]
        # A finished ticket cannot be the active task (the stale-state class
        # the wave started from: STATE.task naming a ticket that SHIP already
        # pushed). Recovery has no way to know the work was done otherwise.
        if t.section == "DONE":
            c.fail(
                "cross.task.done",
                f"STATE names task {tid}, which is DONE -- a finished ticket "
                f"cannot be the active task; the state is stale",
                "RFC § 1.5",
                _BOARD_FILE,
                t.line_no,
            )
        # In a ticket-working phase the named task MUST sit in ## DOING,
        # exactly once. A ticket anywhere else means the state and the board
        # are describing different work.
        elif phase in protocol.TICKET_PHASES and t.section != "DOING":
            c.fail(
                "cross.task.doing.once",
                f"phase {phase} is working {tid} but the ticket sits under "
                f"## {t.section}, not ## DOING -- STATE.task must exist "
                f"exactly once in DOING",
                "RFC § 1.5",
                _BOARD_FILE,
                t.line_no,
            )

    # An active task with an empty ## DOING is the same stale-state class
    # seen from the board side: nothing is claimed, yet the state claims work
    # is in flight.
    if phase in protocol.TICKET_PHASES and task_ids and not doing:
        c.fail(
            "cross.task.doing.empty",
            f"phase {phase} names task {task!r} but ## DOING is empty",
            "RFC § 1.5",
            _STATE_FILE,
        )

    # SHIP must reference work, never a ticket that is already finished.
    # `PHASE SHIP T-###` (or `RESUME: T-### SHIP`) naming a DONE ticket would
    # re-ship a release that already exists.
    m = re.match(r"^(?:PHASE SHIP (T-\d+)|RESUME: (T-\d+) SHIP)$", next_action.strip())
    if m:
        tid = m.group(1) or m.group(2)
        if tid in tickets and tickets[tid].section == "DONE":
            c.fail(
                "cross.ship.done",
                f"next_action {next_action!r} would re-ship {tid}, which is "
                f"already DONE -- SHIP must reference new scope",
                "RFC § 1.6",
                _STATE_FILE,
            )

    # RFC § 2.1 zero-prompt auto-transition + § 1.2's fixed WAIT wordings.
    # At DONE with nothing open the agent MUST go on to HUNT/ADD. A WAIT that
    # is not one of the three machine-separable wordings deadlocks the board.
    def _done_wait_whitelisted(value: str) -> bool:
        low = value.lower()
        return (
            "safety valve" in low
            or low.startswith("wait: user brake")
            or "untriaged markhunt findings" in low
        )

    if phase == "DONE" and next_action.startswith("WAIT:"):
        if not _done_wait_whitelisted(next_action):
            # DONE with a concrete WAIT that is not a valve/brake. The empty
            # board makes it a FAIL (auto-transition is mandatory there); a
            # board that still has work WARNs -- the agent should be working
            # the pick, not idling behind an invented wait.
            open_todo = [
                t for t in tickets.values() if t.section == "TODO" and t.checkbox == " "
            ]
            c.warn(
                "cross.done.wait",
                f"DONE with next_action {next_action!r} -- DONE + WAIT is "
                f"legal only for the § 2.4 safety valve, "
                f"'WAIT: user brake -- <reason>', or the untriaged-MARKHUNT "
                f"brake; otherwise DONE should transition to SCOUT/PLAN/HUNT "
                f"(RFC § 1.6/§ 2.1)",
                "RFC § 1.2",
                _STATE_FILE,
            )
            if not open_todo:
                c.fail(
                    "cross.done.wait.empty_board",
                    f"phase: DONE, empty ## TODO, but next_action={next_action!r} "
                    f"-- a bare command + empty board MUST auto-transition "
                    f"HUNT->ADD, never WAIT at DONE",
                    "RFC § 2.1",
                    _STATE_FILE,
                )

    # CORE § 1.11's Pick Rule, the "what would a cold agent actually do" half.
    # `next_action` is the pre-computed pick, so it must name the ticket the
    # rule would choose. And session-level BLOCKED is reserved for when no
    # ticket anywhere is workable.
    def _ticket_is_workable(t: BoardTicket) -> bool:
        return (
            t.section == "TODO"
            and t.checkbox in (" ", "")
            and "blocker" not in t.fields
            and all(
                need in tickets and tickets[need].section == "DONE" for need in t.needs
            )
        )

    na_pick = re.match(r"PHASE\s+\w+\s+(T-\d+)", next_action)
    if na_pick:
        named = na_pick.group(1)
        t = tickets.get(named)
        if t is None:
            c.fail(
                "cross.pick.unknown",
                f"next_action names {named}, which is on no board section -- "
                f"the pre-computed pick points at nothing",
                "RFC § 1.11",
                _STATE_FILE,
            )
        elif t.section in ("DONE", "BLOCKED"):
            c.fail(
                "cross.pick.closed",
                f"next_action names {named}, which sits under ## {t.section} "
                f"-- finished and blocked tickets are not executable; the "
                f"Pick Rule selects from ## TODO",
                "RFC § 1.11",
                _STATE_FILE,
            )
        elif "blocker" in t.fields:
            c.fail(
                "cross.pick.malformed_blocker",
                f"next_action names {named}, which carries | blocker: outside "
                f"## BLOCKED -- malformed status cannot become executable, "
                f"even before the board-status failure is repaired",
                "RFC § 1.11",
                _STATE_FILE,
            )
        else:
            unmet = [
                need for need in t.needs if tickets.get(need, {}).section != "DONE"
            ]
            if unmet:
                c.fail(
                    "cross.pick.unmet",
                    f"next_action names {named}, whose needs: "
                    + ", ".join(unmet)
                    + " are not DONE -- a ticket is workable only when every "
                    "dependency is finished",
                    "RFC § 1.11",
                    _STATE_FILE,
                )
            owner = t.fields.get("owner")
            if owner and state.get("agent") and owner != state.get("agent"):
                c.fail(
                    "cross.pick.other_claim",
                    f"next_action names {named}, claimed by {owner!r} while "
                    f"this state's agent is {state.get('agent')!r} -- "
                    f"executing another agent's claim is the concurrency "
                    f"collision § 1.4 exists to prevent",
                    "RFC § 1.4",
                    _STATE_FILE,
                )

    if phase == "BLOCKED":
        workable = [t.ticket_id for t in tickets.values() if _ticket_is_workable(t)]
        if workable:
            c.fail(
                "cross.blocked.workable",
                f"phase: BLOCKED while {len(workable)} workable ## TODO "
                f"ticket(s) exist (topmost {min(workable)}) -- session-level "
                f"BLOCKED is reserved for when no ticket anywhere is "
                f"workable; a block that belongs to one ticket goes on THAT "
                f"ticket's line under ## BLOCKED",
                "RFC § 1.11",
                _STATE_FILE,
            )


# --- LOG.md ---------------------------------------------------------------


def _log_sequence(root: Path) -> tuple[list[Path], Path | None]:
    """(segments in NNN order, active tail). Sealed segments live in
    .saipen/logs/LOG-NNN.md; the active tail is .saipen/LOG.md. The canonical
    validator walks segments first, active last, so E-### stays globally
    monotonic across segment boundaries -- STATE.last_event is judged against
    the whole sequence, not just the active file."""
    seg_dir = root / ".saipen" / "logs"
    segments = []
    if seg_dir.is_dir():
        segments = sorted(
            (
                p
                for p in seg_dir.glob("LOG-*.md")
                if re.fullmatch(r"LOG-\d+\.md", p.name)
            ),
            key=lambda p: int(p.stem[len("LOG-") :]),
        )
    active = root / ".saipen" / "LOG.md"
    return segments, active if active.is_file() else None


def check_log(root: Path, c: _Collector, state: dict[str, str] | None = None) -> None:
    log_path = root / ".saipen" / "LOG.md"
    if not log_path.is_file():
        c.warn(
            "log.missing",
            "no .saipen/LOG.md -- the audit trail Recovery reads is absent",
            "RFC § 1.2",
            _LOG_FILE,
        )
        return

    enc = encoding_of(log_path)
    if enc != "utf-8":
        c.fail(
            "log.encoding",
            f"LOG.md is {enc}, not plain UTF-8",
            "KNOWLEDGE/traps.md",
            _LOG_FILE,
        )

    segments, active = _log_sequence(root)
    log_files = segments + ([active] if active is not None else [])

    now = datetime.datetime.now(datetime.timezone.utc)
    prev_event = None
    seen: dict[int, int] = {}
    undated = 0
    in_comment = False
    for path in log_files:
        is_active = path == active
        for line_no, raw in enumerate(read_doc(path).splitlines(), 1):
            line = raw.rstrip()
            if not line.strip() or line.startswith("#"):
                continue

            # HTML comments are annotations ABOUT the log, not entries in it, and
            # demanding the Event Graph skeleton from one is a grader bug, not a
            # finding. Real case: FastPrompter's LOG carries a 16-line
            # `<!-- RECOVERY SPLICE ... -->` block explaining that a saitranslate
            # INIT bootstrap had overwritten BOARD/LOG/STATE -- exactly the kind of
            # note a human needs, reported as 16 failures for having the wrong
            # shape. Skipped whole: a `<!--` opener suppresses until its `-->`,
            # since the body lines carry no marker of their own.
            if in_comment:
                if "-->" in line:
                    in_comment = False
                continue
            if line.lstrip().startswith("<!--"):
                if "-->" not in line:
                    in_comment = True
                continue

            if "�" in line:
                c.fail(
                    "log.replacement_char",
                    "line carries a U+FFFD replacement character -- text was "
                    "corrupted somewhere upstream and the repair must be explicit",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )

            skeleton = _LOG_SKELETON_RE.match(line)
            if not skeleton:
                c.fail(
                    "log.skeleton",
                    f"line does not match the Event Graph skeleton "
                    f"`- DD.MM.YY HH:MM [E-###] [parent: E-###] [T-###] VERB: "
                    f"text`: {line[:80]!r}",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )
                continue

            _, _, ticket_ref, taxonomy, _ = skeleton.groups()
            if taxonomy not in _LOG_TAXONOMY:
                c.warn(
                    "log.taxonomy",
                    f"verb {taxonomy!r} is not one of "
                    f"{'/'.join(sorted(_LOG_TAXONOMY))} -- non-conformant for new entries",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )
            if ticket_ref and not _TICKET_REF_RE.match(ticket_ref):
                c.warn(
                    "log.ticket_ref",
                    f"ticket reference {ticket_ref!r} is neither a numeric T-### "
                    f"nor the literal T-none",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )

            dated = _LOG_ENTRY_RE.match(line)
            any_event = _LOG_ANY_EVENT_RE.match(line)
            event = int(any_event.group(1))
            if not dated:
                # CORE § 1.2 makes DATE mandatory. The active log is still the
                # writer's to get right (FAIL); sealed history is immutable by
                # append-only, so it can only be reported (WARN).
                undated += 1
                if is_active:
                    c.fail(
                        "log.timestamp.missing",
                        f"E-{event} in the active LOG has no DD.MM.YY HH:MM "
                        f"stamp -- Recovery cannot order what it cannot date",
                        "RFC § 1.2",
                        path.name,
                        line_no,
                    )
            else:
                try:
                    stamp = datetime.datetime.strptime(
                        f"{dated.group(1)} {dated.group(2)}", "%d.%m.%y %H:%M"
                    ).replace(tzinfo=datetime.timezone.utc)
                except ValueError:
                    stamp = None
                # CORE § 1.2's clock tolerance is 5 minutes (tools/validate.py
                # LOG_CLOCK_SLACK). The old 3-hour bound is exactly what let a
                # guessed clock -- off by 20-40 minutes -- sail through clean.
                if (
                    stamp
                    and (stamp - now).total_seconds() > protocol.LOG_CLOCK_SLACK_SECONDS
                ):
                    c.fail(
                        "log.timestamp.future",
                        f"E-{event} is stamped more than "
                        f"{protocol.LOG_CLOCK_SLACK_SECONDS // 60}m ahead of "
                        f"real UTC -- a local clock was written where UTC was "
                        f"required",
                        "RFC § 1.2",
                        path.name,
                        line_no,
                    )
            if event in seen:
                c.fail(
                    "log.event.duplicate",
                    f"E-{event} appears twice (first at line {seen[event]}) -- "
                    f"event ids are unique",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )
            elif prev_event is not None and event < prev_event:
                c.fail(
                    "log.event.order",
                    f"E-{event} follows E-{prev_event} -- event ids only increase",
                    "RFC § 1.2",
                    path.name,
                    line_no,
                )
            seen[event] = line_no
            prev_event = max(prev_event or 0, event)

    if undated and not any(f.rule == "log.timestamp.missing" for f in c.findings):
        c.warn(
            "log.timestamp.undated_sealed",
            f"{undated} sealed LOG entr(y/ies) carry no DD.MM.YY HH:MM stamp -- "
            f"immutable by append-only; new entries are FAILed instead",
            "RFC § 1.2",
            _LOG_FILE,
        )

    # CORE § 1.2/§ 1.5 freshness marker: at the current schema revision, a
    # state with an event-bearing LOG MUST carry last_event equal to the LOG
    # tail EXACTLY. Lower = stale state predating its own history; higher =
    # corrupt, a state carried from a branch whose events were never written.
    if state is not None:
        sv = state.get("schema_version")
        try:
            sv_int = int(sv)
        except (TypeError, ValueError):
            sv_int = None
        le = state.get("last_event")
        try:
            le_int = int(le)
        except (TypeError, ValueError):
            le_int = None
        if sv_int == protocol.STATE_SCHEMA_VERSION and prev_event and le_int is None:
            c.fail(
                "state.last_event.missing",
                f"STATE.md schema_version {protocol.STATE_SCHEMA_VERSION} "
                f"requires last_event because the LOG tail is E-{prev_event}",
                "RFC § 1.2",
                _STATE_FILE,
            )
        if le_int is not None:
            if le_int < 1:
                c.fail(
                    "state.last_event.minimum",
                    f"last_event is E-{le_int}, but event IDs start at E-1",
                    "RFC § 1.2",
                    _STATE_FILE,
                )
            elif le_int > prev_event:
                c.fail(
                    "state.last_event.ahead",
                    f"last_event is E-{le_int} but the LOG tail is "
                    f"E-{prev_event} -- higher than the log means corrupt, or "
                    f"a STATE carried over from an incompatible branch",
                    "RFC § 1.2",
                    _STATE_FILE,
                )
            elif le_int < prev_event:
                c.fail(
                    "state.last_event.stale",
                    f"last_event is E-{le_int} but the LOG tail is "
                    f"E-{prev_event} -- lower than the log means this STATE "
                    f"predates its own history: a checkpoint wrote LOG lines "
                    f"and did not finish updating STATE",
                    "RFC § 1.2",
                    _STATE_FILE,
                )


# --- subSaipens -----------------------------------------------------------


def check_subs(subs, c: _Collector) -> None:
    """`subs` is a list of parser.SubStatus. Checked here rather than in
    parser.py so the parser stays a reader and this stays the only opinion."""
    for sub in subs:
        where = f".saipen/extensions/subs/{sub.name}"
        na = sub.next_action
        if na and not na.startswith(protocol.NEXT_ACTION_PREFIXES):
            c.fail(
                "sub.next_action.prefix",
                f"{sub.name}: next_action {na!r} does not start with one of "
                f"{'/'.join(protocol.NEXT_ACTION_PREFIXES)}",
                "RFC § 1.2",
                f"{where}/STATE.md",
            )
        elif na.startswith("WAIT:"):
            body = na[len("WAIT:") :].strip().lower()
            if not any(body.startswith(cat) for cat in protocol.WAIT_CATEGORIES):
                c.fail(
                    "sub.next_action.wait.category",
                    f"{sub.name}: WAIT carries no category token",
                    "RFC § 1.2",
                    f"{where}/STATE.md",
                )
        if sub.phase not in protocol.PHASES and sub.phase != "?":
            c.fail(
                "sub.phase.enum",
                f"{sub.name}: phase {sub.phase!r} is not one of the 16 enum values",
                "RFC § 1.6",
                f"{where}/STATE.md",
            )
        for entry in sub.outbox:
            if entry.status not in protocol.OUTBOX_STATUSES:
                c.fail(
                    "sub.outbox.status",
                    f"{sub.name} {entry.entry_id}: status {entry.status!r} is "
                    f"not one of {'/'.join(protocol.OUTBOX_STATUSES)}",
                    "subs/PROTOCOL.md § 2",
                    f"{where}/kitchen/OUTBOX.md",
                )
        counts = sub.board_counts
        if not any(counts.values()) and not sub.outbox and sub.phase in ("?", "", None):
            c.warn(
                "sub.empty",
                f"{sub.name} has an empty board, an empty OUTBOX and no phase "
                f"-- spawned but never run, and indistinguishable from a "
                f"working one in MANIFEST.md",
                "subs/PROTOCOL.md § 5",
                f"{where}/STATE.md",
            )


# --- entry point ----------------------------------------------------------


def check_project(root: Path, state: dict[str, str], subs=None) -> Report:
    """Grade one project. `state` is the already-parsed STATE frontmatter --
    passed in rather than re-read so the verdict describes exactly the same
    bytes the rest of the row was built from."""
    c = _Collector()
    check_state(state, root, c)
    tickets = check_board(root, c)
    check_cross(state, tickets, root, c)
    check_log(root, c, state)
    if subs:
        check_subs(subs, c)
    # Fails first, then warns; stable within a severity by rule id so the list
    # doesn't reshuffle between refreshes.
    c.findings.sort(key=lambda f: (f.severity != FAIL, f.rule, f.line))
    return Report(c.findings)
