"""Parses STATE.md frontmatter and BOARD.md ticket sections.

Not a full YAML parser -- SAIPEN's own STATE.md frontmatter is flat
key: value pairs (RFC.md 1.2), so a line-based parser is enough and
sidesteps YAML's backslash-escape traps on Windows paths.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from saipenview import protocol
from saipenview.ownership import AgentOwnershipError
from saipenview.protocol_write import (
    ConflictError,
    MutationRejected,
    escape_pipe,
    get_coordinator,
    next_event_id,
    next_ticket_id,
)
from saipenview.textio import read_doc

# T-123: `updated` stamps. A valid protocol timestamp is explicit UTC (Z) or
# carries an offset; a timezone-naive value is AMBIGUOUS -- never silently
# treated as UTC, because a hand-edited naive stamp may actually be local and
# a wrong assumption is exactly the 1-2h "timing is wrong" report this ticket
# closed. The backend normalizes valid stamps to explicit UTC so the frontend
# receives one unambiguous value; naive/invalid stay raw and are marked.
_TS_UTC_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z$")
_TS_OFFSET_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2})$"
)
_TS_NAIVE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?$")


def classify_timestamp(raw: str) -> tuple[str, str]:
    """Normalize one `updated` stamp.

    Returns ``(normalized, kind)`` where kind is one of ``utc`` (explicit Z,
    kept as-is), ``offset`` (explicit offset, converted to UTC Z), ``naive``
    (no timezone -- kept raw, ambiguous), ``invalid`` (not a timestamp), or
    ``missing`` (empty).
    """
    s = (raw or "").strip()
    if not s:
        return "", "missing"
    if _TS_UTC_RE.match(s):
        return s, "utc"
    m = _TS_OFFSET_RE.match(s)
    if m:
        try:
            parsed = _dt.datetime.fromisoformat(s)
        except ValueError:
            return s, "invalid"
        utc = parsed.astimezone(_dt.timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z", "offset"
    if _TS_NAIVE_RE.match(s):
        return s, "naive"
    return s, "invalid"


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*", re.DOTALL)
TICKET_RE = re.compile(r"^-\s*\[( |x|/)\]\s*(\S+)\s+(.*)$")
SECTION_HEADING_RE = re.compile(r"^##\s+(DOING|TODO|DONE|BLOCKED)\s*$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = _unquote(value)
    return fields


def update_state(root: Path, updates: dict[str, str]) -> bool:
    import datetime

    state_path = root / ".saipen" / "STATE.md"
    if not state_path.is_file():
        return False

    def transform(text: str) -> str | None:
        match = FRONTMATTER_RE.match(text)
        if not match:
            return None
        lines = match.group(1).splitlines()
        new_lines = []
        updated_keys = set()
        for line in lines:
            sline = line.strip()
            if not sline or ":" not in sline:
                new_lines.append(line)
                continue
            key, _, _ = line.partition(":")
            k = key.strip()
            if k in updates:
                new_lines.append(f"{k}: {updates[k]}")
                updated_keys.add(k)
            else:
                new_lines.append(line)

        for k, v in updates.items():
            if k not in updated_keys:
                new_lines.append(f"{k}: {v}")

        if "updated" not in updates:
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            found = False
            for i, line in enumerate(new_lines):
                if line.startswith("updated:"):
                    new_lines[i] = f"updated: {now_str}"
                    found = True
                    break
            if not found:
                new_lines.append(f"updated: {now_str}")

        new_frontmatter = "---\n" + "\n".join(new_lines) + "\n---\n"
        return new_frontmatter + text[match.end() :]

    try:
        return get_coordinator().mutate_doc(state_path, transform) is not None
    except (ConflictError, MutationRejected, OSError):
        return False
    except AgentOwnershipError:
        return False


@dataclass
class Ticket:
    ticket_id: str
    status: str  # " " open, "x" done, "/" in-progress
    description: str
    blocker: str = ""


@dataclass
class Board:
    doing: list[Ticket] = field(default_factory=list)
    todo: list[Ticket] = field(default_factory=list)
    done: list[Ticket] = field(default_factory=list)
    blocked: list[Ticket] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "doing": len(self.doing),
            "todo": len(self.todo),
            "done": len(self.done),
            "blocked": len(self.blocked),
        }


_SECTION_LISTS = {
    "DOING": "doing",
    "TODO": "todo",
    "DONE": "done",
    "BLOCKED": "blocked",
}

# CORE § 1.2's strict ticket state machine. The SECTION is the status -- never
# the checkbox -- and each action names the source sections it accepts and the
# (section, checkbox) it produces. Everything else is an illegal transition
# that must be rejected with zero writes.
_ACTION_TRANSITIONS: dict[str, dict[str, tuple[str, str]]] = {
    "start": {"TODO": ("DOING", "/")},
    "done": {"DOING": ("DONE", "x")},
    "reopen": {"DONE": ("TODO", " ")},
    "block": {"TODO": ("BLOCKED", " "), "DOING": ("BLOCKED", " ")},
    "unblock": {"BLOCKED": ("TODO", " ")},
}

# The closed ticket-field vocabulary is owned by protocol.py (synced from
# tools/saipen_engine/board.py); the blocker/verify reads here just use it.
_TICKET_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
_PIPE_SENTINEL = "\x00"


def _ticket_parts(rest: str) -> tuple[str, dict[str, str]]:
    """Split a ticket line's pipe-delimited tail into (description, fields).
    An escaped pipe is hidden before splitting so it never invents a field."""
    masked = rest.replace("\\|", _PIPE_SENTINEL)
    parts = [p.strip() for p in masked.split(" | ")]
    fields: dict[str, str] = {}
    for part in parts[1:]:
        m = _TICKET_FIELD_RE.match(part)
        if m:
            fields[m.group(1)] = m.group(2).replace(_PIPE_SENTINEL, "|")
    return parts[0].replace(_PIPE_SENTINEL, "|"), fields


def _set_field(line: str, field: str, value: str) -> str:
    """Replace `| field: ...` on a ticket line or append it; exactly one copy."""
    parts = line.rstrip("\n").replace("\\|", _PIPE_SENTINEL).split(" | ")
    pattern = re.compile(rf"^{re.escape(field)}:\s*")
    out = []
    replaced = False
    for part in parts:
        if pattern.match(part):
            if not replaced:
                out.append(f"{field}: {value}")
                replaced = True
            continue
        out.append(part)
    if not replaced:
        out.append(f"{field}: {value}")
    return " | ".join(out).replace(_PIPE_SENTINEL, "\\|")


def _remove_field(line: str, field: str) -> str:
    parts = line.rstrip("\n").replace("\\|", _PIPE_SENTINEL).split(" | ")
    pattern = re.compile(rf"^{re.escape(field)}:\s*")
    return " | ".join(p for p in parts if not pattern.match(p)).replace(
        _PIPE_SENTINEL, "\\|"
    )


def _rewrite_checkbox(line: str, new_ch: str) -> str:
    m = TICKET_RE.match(line.strip())
    if m:
        old = m.group(1)
        return line.replace(f"[{old}]", f"[{new_ch}]", 1)
    return line


def _transition_error_text(
    board_text: str,
    state: dict[str, str],
    ticket_id: str,
    action: str,
    reason: str | None,
) -> str | None:
    """The legality of one ticket move, decided from the board text (section
    IS status) plus STATE for the active-task cases. None == legal."""
    if action not in _ACTION_TRANSITIONS:
        return f"unknown ticket action {action!r}"
    allowed = _ACTION_TRANSITIONS[action]
    section: str | None = None
    fields: dict[str, str] = {}
    current: str | None = None
    for line in board_text.splitlines():
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            current = heading.group(1)
            continue
        t = TICKET_RE.match(line.strip())
        if t and t.group(2) == ticket_id:
            section = current
            _, fields = _ticket_parts(t.group(3))
            break
    if section is None:
        return f"{ticket_id} not on the board"
    if section not in allowed:
        sources = (
            "TODO/DOING" if set(allowed) == {"TODO", "DOING"} else "/".join(allowed)
        )
        return f"{action} accepts {sources}; {ticket_id} is under ## {section}"
    if action in ("block", "unblock"):
        need = (
            "the facts/dead ends that justify the block"
            if action == "block"
            else "the decision/evidence that lifts the block"
        )
        if not (reason or "").strip():
            return f"{action} requires a non-empty reason: {need}"
    if action == "block" and section == "DOING":
        return (
            f"blocking a DOING ticket must park the execution state under "
            f"SAIOPS park semantics (STATE -> DONE/task none); mutating BOARD "
            f"alone would leave a state the validator rejects -- use "
            f"`saipen ticket block {ticket_id} <reason>`"
        )
    if action == "start" and "blocker" in fields:
        return (
            f"{ticket_id} carries | blocker: outside ## BLOCKED -- malformed "
            f"status cannot become workable; remove the blocker field first"
        )
    if action == "done":
        if not fields.get("verify", "").strip():
            return (
                f"DOING -> DONE requires canonical completion evidence: the "
                f"ticket must carry a non-empty | verify: clause. Closing "
                f"without it fabricates a completion; use `saipen ticket done "
                f"{ticket_id}` to close it atomically"
            )
        active_task = (
            state.get("task") == ticket_id
            and state.get("phase") in protocol.TICKET_PHASES
        )
        if active_task:
            return (
                f"{ticket_id} is the active STATE task in a ticket-bearing "
                f"phase -- closing it board-only would split STATE/BOARD; "
                f"use `saipen ticket done {ticket_id}`"
            )
    return None


def ticket_transition_error(
    root: Path, ticket_id: str, action: str, reason: str | None = None
) -> str | None:
    """None when the move is legal under CORE § 1.2's strict state machine,
    else the refusal reason. The UI derives disable/reason text from this SAME
    function the backend enforces."""
    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        return "BOARD.md not found"
    state_path = root / ".saipen" / "STATE.md"
    state = parse_frontmatter(read_doc(state_path)) if state_path.is_file() else {}
    return _transition_error_text(
        read_doc(board_path), state, ticket_id, action, reason
    )


def move_ticket(
    root: Path, ticket_id: str, action: str, blocker_reason: str | None = None
) -> bool:
    """Move a ticket between BOARD sections under the strict state machine.

    Legal source -> action -> target (CORE § 1.2; section IS status):

      TODO  -> start  -> DOING
      DOING -> done   -> DONE  (only with a non-empty | verify: clause and
                                only when the ticket is not the active STATE
                                task -- both are canonical completion gates)
      DONE  -> reopen -> TODO
      TODO  -> block  -> BLOCKED   (reason REQUIRED, escaped)
      BLOCKED -> unblock -> TODO   (lifting decision REQUIRED, blocker field
                                    removed atomically)

    Everything else is rejected with zero writes. `done`/`block` on the active
    ticket is refused in favour of the canonical SAIOPS operations, which can
    close BOARD+LOG+STATE atomically where this board-only mover cannot.
    """
    if action not in _ACTION_TRANSITIONS:
        return False
    board_path = root / ".saipen" / "BOARD.md"
    state_path = root / ".saipen" / "STATE.md"
    if not board_path.is_file():
        return False

    coord = get_coordinator()
    deps = [state_path] if state_path.is_file() else None
    try:
        with coord.locked(root):
            state = (
                parse_frontmatter(read_doc(state_path)) if state_path.is_file() else {}
            )
            err = _transition_error_text(
                read_doc(board_path), state, ticket_id, action, blocker_reason
            )
            if err is not None:
                return False
            coord.transaction(
                root,
                {
                    board_path: lambda text, a=action, r=blocker_reason, s=state: (
                        _apply_move(text, ticket_id, a, r, s)
                    )
                },
                deps=deps,
            )
        return True
    except (ConflictError, MutationRejected, OSError):
        return False
    except AgentOwnershipError:
        return False


def _apply_move(
    text: str,
    ticket_id: str,
    action: str,
    reason: str | None,
    state: dict[str, str],
) -> str | None:
    """Apply one legal move to the BOARD text. Returns None (decline, no
    write) on anything the strict machine forbids -- re-checked here, on the
    exact text being committed, so a stale legality decision can never commit."""
    err = _transition_error_text(text, state, ticket_id, action, reason)
    if err is not None:
        return None
    allowed = _ACTION_TRANSITIONS[action]
    lines = text.splitlines(True)
    ticket_idx = -1
    current: str | None = None
    for i, line in enumerate(lines):
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            current = heading.group(1)
            continue
        t = TICKET_RE.match(line.strip())
        if t and t.group(2) == ticket_id:
            ticket_idx = i
            break
    if ticket_idx < 0:
        return None
    section = current or ""
    target_section, new_ch = allowed[section]

    ticket_line = lines.pop(ticket_idx)
    had_newline = ticket_line.endswith("\n")
    ticket_line = ticket_line.rstrip("\n")
    if action == "block":
        reason_flat = " ".join((reason or "").split())
        ticket_line = _set_field(ticket_line, "blocker", escape_pipe(reason_flat))
        ticket_line = _rewrite_checkbox(ticket_line, new_ch)
    elif action == "unblock":
        ticket_line = _remove_field(ticket_line, "blocker")
        ticket_line = _remove_field(ticket_line, "verify_attempts")
        ticket_line = _rewrite_checkbox(ticket_line, new_ch)
    else:
        ticket_line = _rewrite_checkbox(ticket_line, new_ch)
    if had_newline:
        ticket_line += "\n"

    # Insert into the target section: after its heading, before the next
    # heading (or end of file). All four headings are required on a valid
    # board; a missing one degrades to appending at the end.
    target_idx = -1
    insert_pos = len(lines)
    for i, line in enumerate(lines):
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            if heading.group(1) == target_section:
                target_idx = i
            elif target_idx >= 0:
                insert_pos = i
                break
    if target_idx >= 0:
        lines.insert(insert_pos, ticket_line)
    else:
        lines.append(ticket_line)
    return "".join(lines)


def reorder_ticket(
    root: Path, ticket_id: str, section: str, before_ticket_id: str | None = None
) -> bool:
    """Move a ticket line to a new position WITHIN its section (T-175).

    ``before_ticket_id`` is the ticket the dragged row should land before;
    None appends to the end of the section. Order inside a section is the
    order of its lines -- and board order is priority (RFC 1.6), so a
    drag-reordered board is a re-prioritised one. Only ever touches the one
    ticket's line, never other lines, so the single-writer path holds.
    """
    if section not in _SECTION_LISTS:
        return False
    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        return False

    def transform(text: str) -> str | None:
        lines = text.splitlines(True)

        section_start = -1
        section_end = len(lines)
        ticket_idx = -1
        before_idx = -1
        current: str | None = None
        for i, line in enumerate(lines):
            heading = SECTION_HEADING_RE.match(line.strip())
            if heading:
                current = heading.group(1)
                if current == section:
                    section_start = i
                elif section_start >= 0:
                    section_end = i
                    break
                continue
            if current == section and section_start >= 0:
                t = TICKET_RE.match(line.strip())
                if t:
                    if t.group(2) == ticket_id:
                        ticket_idx = i
                    elif t.group(2) == before_ticket_id:
                        before_idx = i

        if section_start < 0 or ticket_idx < 0 or ticket_idx < section_start:
            return None
        if before_idx >= 0 and before_idx >= section_end:
            return None

        ticket_line = lines.pop(ticket_idx)
        if before_idx > ticket_idx:
            before_idx -= 1
        section_end_adj = section_end - 1 if section_end > ticket_idx else section_end
        insert_pos = before_idx if before_idx >= 0 else section_end_adj
        # No-op: already in place.
        if insert_pos == ticket_idx:
            lines.insert(ticket_idx, ticket_line)
            return None
        lines.insert(insert_pos, ticket_line)
        return "".join(lines)

    try:
        return get_coordinator().mutate_doc(board_path, transform) is not None
    except (ConflictError, MutationRejected, OSError):
        return False


def _insert_into_todo(board_text: str, ticket_line: str) -> str:
    """Insert *ticket_line* under `## TODO`, before the next heading."""
    if "\n## TODO" in "\n" + board_text:
        lines = board_text.splitlines(True)
        insert_at = len(lines)
        in_todo = False
        for i, line in enumerate(lines):
            heading = SECTION_HEADING_RE.match(line.strip())
            if heading:
                if heading.group(1) == "TODO":
                    in_todo = True
                    insert_at = i + 1
                elif in_todo:
                    insert_at = i
                    break
        lines.insert(insert_at, ticket_line + "\n")
        return "".join(lines)
    return board_text.rstrip("\n") + "\n\n## TODO\n" + ticket_line + "\n"


_MANUAL_WORK_RE = re.compile(
    r"\[E-(\d+)\] \[(T-\d+)\](?: \[op: ([^\]]+)\])? RUN: manual work recorded -- (.*)$"
)


def _new_operation_id() -> str:
    import uuid

    return "mw-" + uuid.uuid4().hex[:12]


def _transaction_deps(root: Path) -> list[Path]:
    """The canonical checkpoint set an operation's truth depends on: STATE,
    LOG (and BOARD is added by callers that touch it). An external edit to
    STATE while a BOARD+LOG transaction is in flight must abort, never
    silently compose two realities."""
    deps = [root / ".saipen" / "LOG.md"]
    state_path = root / ".saipen" / "STATE.md"
    if state_path.is_file():
        deps.append(state_path)
    return deps


def record_manual_work(
    root: Path, description: str, operation_id: str | None = None
) -> dict:
    """Record a user's manual edit as a board entry (T-127).

    The user did something by hand -- edited a project's STATE/BOARD/LOG in an
    editor, made a commit, ran a script. SAIPENVIEW cannot attribute the
    change to a person (the watcher never knows who wrote the file), so it
    does not try: the UI asks, the user confirms, and THIS function writes the
    explicit record. One board ticket + one LOG evidence line, both through
    the per-project write coordinator (T-183). Returns ``{"ok": True}`` or an
    error dict.

    Idempotency is by OPERATION ID, never by human prose (repair mission P1):
    two legitimate separate actions named "updated docs" must remain two
    records. ``operation_id`` is generated at UI invocation and carried
    through retry/resume; a retry with the same id resumes the original
    ticket, while the same description with a different id is a fresh record.
    The id is persisted in the LOG line as ``[op: <id>]``.

    Crash safety (T-191): the LOG evidence line is written FIRST, then the
    BOARD ticket. A failure between the two leaves the LOG record behind --
    never an unlogged orphan ticket -- and a retry detects the prior LOG line
    by its ``[op: ...]`` marker and resumes.
    """
    description = " ".join(str(description or "").split())
    if not description:
        return {"ok": False, "error": "description is empty"}
    escaped = escape_pipe(description)
    op_id = operation_id or _new_operation_id()

    board_path = root / ".saipen" / "BOARD.md"
    log_path = root / ".saipen" / "LOG.md"
    if not board_path.is_file():
        return {"ok": False, "error": "BOARD.md not found"}
    if not log_path.is_file():
        return {"ok": False, "error": "LOG.md not found"}

    coord = get_coordinator()
    try:
        with coord.locked(root):
            # Both files are read once, under the root lock, and the fingerprints
            # of THAT read become the CAS baseline for both writes. An external
            # writer between read and commit raises ConflictError; nothing is
            # written, ids are never burned on a stale read.
            log_text = read_doc(log_path)
            board_text = read_doc(board_path)

            # Idempotent resume: did a prior attempt with THIS operation_id
            # already write the LOG line?
            for m in re.finditer(_MANUAL_WORK_RE, log_text):
                if m.group(3) == op_id:
                    event_id = f"E-{m.group(1)}"
                    ticket_id = m.group(2)
                    if re.search(rf"\b{re.escape(ticket_id)}\b", board_text):
                        return {
                            "ok": True,
                            "already": True,
                            "ticket_id": ticket_id,
                            "event": event_id,
                        }
                    ticket_line = f"- [ ] {ticket_id} Manual: {escaped} | owner: user"
                    coord.transaction(
                        root,
                        {
                            board_path: lambda t, tl=ticket_line: _insert_into_todo(
                                t, tl
                            )
                        },
                        deps=_transaction_deps(root),
                    )
                    return {
                        "ok": True,
                        "resumed": True,
                        "ticket_id": ticket_id,
                        "event": event_id,
                    }

            # Fresh allocation -- one place, under the root lock (T-183).
            next_event = next_event_id(log_text)
            next_ticket = next_ticket_id(board_text)
            ticket_id = f"T-{next_ticket:03d}"
            stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%d.%m.%y %H:%M")
            git_note = _manual_work_git_note(root)
            log_line = (
                f"- {stamp} [E-{next_event}] [{ticket_id}] [op: {op_id}] RUN: "
                f"manual work recorded -- {escaped}{git_note}"
            )
            ticket_line = f"- [ ] {ticket_id} Manual: {escaped} | owner: user"

            coord.transaction(
                root,
                {
                    log_path: lambda t, ll=log_line: (
                        (t.rstrip("\n") + "\n" if t.strip() else "") + ll + "\n"
                    ),
                    board_path: lambda t, tl=ticket_line: _insert_into_todo(t, tl),
                },
                deps=_transaction_deps(root),
            )

        return {"ok": True, "ticket_id": ticket_id, "event": f"E-{next_event}"}
    except ConflictError:
        return {"ok": False, "error": "project changed concurrently; retry"}
    except (AgentOwnershipError, MutationRejected, OSError):
        return {
            "ok": False,
            "error": "record refused (project changed or agent owns it); retry",
        }


def _manual_work_git_note(root: Path) -> str:
    """Best-effort git context for a manual-work record: HEAD + dirty count."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    # A dead reader thread can leave stdout as None; never crash a worker on it.
    if head.returncode != 0:
        return ""
    head_out = (head.stdout or "").strip()
    dirty = (
        len([ln for ln in (status.stdout or "").splitlines() if ln.strip()])
        if status.returncode == 0
        else 0
    )
    return f" -- at {head_out} ({dirty} dirty files)"


def parse_board(text: str) -> Board:
    board = Board()
    current: str | None = None
    for line in text.splitlines():
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            current = heading.group(1)
            continue
        ticket = TICKET_RE.match(line.strip())
        if ticket and current:
            status, ticket_id, description = ticket.groups()
            # A `| blocker:` field rides on the end of the line; show it
            # separately so a BLOCKED row can display WHY it is blocked.
            blocker = ""
            field = re.search(r"\s*\|\s*blocker:\s*(.+)$", description)
            if field:
                blocker = field.group(1).strip()
                description = description[: field.start()]
            getattr(board, _SECTION_LISTS[current]).append(
                Ticket(ticket_id, status, description, blocker)
            )
    return board


OUTBOX_HEADING_RE = re.compile(r"^##\s+(\S+):\s*(.*)$")
OUTBOX_FIELD_RE = re.compile(r"^-\s*\*\*([A-Za-z_]+):\*\*\s*(.*)$")


@dataclass
class OutboxEntry:
    """One `## ID: title` block from a subSaipen's kitchen/OUTBOX.md
    (extensions/subs/PROTOCOL.md 2). Fields are kept as a free-form dict
    since a fixer-type sub (saipython) adds its own extra fields
    (base_head, verified, patch) on top of the base shape -- no fixed
    schema to enumerate here, same descriptive-only footing as
    outbox.schema.json."""

    entry_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def summary(self) -> str:
        return self.fields.get("summary", "")

    @property
    def critical(self) -> bool:
        return self.fields.get("critical", "").strip().lower() == "true"

    @property
    def severity(self) -> str:
        return self.fields.get("severity", "")

    @property
    def details(self) -> str:
        return self.fields.get("details", "").strip()


def parse_outbox(text: str) -> list[OutboxEntry]:
    """Parses the `## ID: title` + `- **field:** value` shape PROTOCOL.md 2
    defines. A field's value continues on following lines (needed for
    multi-line `details:` and fenced-diff `patch:` blocks) until the next
    bold field or the next entry heading."""
    entries: list[OutboxEntry] = []
    entry_id: str | None = None
    title = ""
    fields: dict[str, str] = {}
    field_key: str | None = None

    def flush() -> None:
        if entry_id is not None:
            entries.append(OutboxEntry(entry_id, title, fields))

    for raw_line in text.splitlines():
        heading = OUTBOX_HEADING_RE.match(raw_line.strip())
        if heading:
            flush()
            entry_id, title = heading.group(1), heading.group(2).strip()
            fields = {}
            field_key = None
            continue
        if entry_id is None:
            continue  # before the first '## ID:' heading -- '# OUTBOX' title, comments
        bold_field = OUTBOX_FIELD_RE.match(raw_line.strip())
        if bold_field:
            field_key = bold_field.group(1).lower()
            fields[field_key] = bold_field.group(2).strip()
            continue
        if field_key is not None:
            fields[field_key] = (fields[field_key] + "\n" + raw_line).rstrip()
    flush()
    return entries


def load_sub_log_tail(sub_path: Path, max_lines: int = 3) -> list[str]:
    """Return last N LOG.md entries for a subSaipen."""
    log_path = sub_path / "LOG.md"
    if not log_path.is_file():
        return []
    try:
        lines = [
            line.strip()
            for line in read_doc(log_path).splitlines()
            if line.strip().startswith("-")
        ]
        return lines[-max_lines:]
    except OSError:
        return []


def load_sub_board(sub_path: Path) -> dict[str, int]:
    """Return board section counts for a subSaipen."""
    board_path = sub_path / "BOARD.md"
    if not board_path.is_file():
        return {"doing": 0, "todo": 0, "done": 0, "blocked": 0}
    try:
        return parse_board(read_doc(board_path)).counts()
    except OSError:
        return {"doing": 0, "todo": 0, "done": 0, "blocked": 0}


def load_outbox(kitchen_dir: Path) -> list[OutboxEntry]:
    outbox_path = kitchen_dir / "OUTBOX.md"
    if not outbox_path.is_file():
        return []
    try:
        return parse_outbox(read_doc(outbox_path))
    except OSError:
        return []


_OUTBOX_STATUS_COUNTS = ("ready", "draft", "blocked", "reviewed", "stale")


@dataclass
class SubStatus:
    """A nested SAIPEN instance's own state -- distinguished by full path (RFC.md 1.1)."""

    name: str
    path: Path
    state: dict[str, str]
    outbox: list[OutboxEntry] = field(default_factory=list)
    log_tail: list[str] = field(default_factory=list)
    board_counts: dict[str, int] = field(
        default_factory=lambda: {"doing": 0, "todo": 0, "done": 0, "blocked": 0}
    )

    @property
    def phase(self) -> str:
        return self.state.get("phase", "?")

    @property
    def task(self) -> str:
        return self.state.get("task", "none")

    @property
    def next_action(self) -> str:
        return self.state.get("next_action", "")

    @property
    def blocker(self) -> str:
        return self.state.get("blocker", "none")

    @property
    def updated(self) -> str:
        return self.state.get("updated", "")

    @property
    def updated_kind(self) -> str:
        return classify_timestamp(self.updated)[1]

    @property
    def outbox_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in _OUTBOX_STATUS_COUNTS}
        for e in self.outbox:
            counts[e.status] = counts.get(e.status, 0) + 1
        return counts

    @property
    def outbox_critical_ready(self) -> int:
        return sum(1 for e in self.outbox if e.status == "ready" and e.critical)


def _find_subs_dir(root: Path) -> Path | None:
    for candidate in (
        root / ".saipen" / "extensions" / "subs",
        root / "extensions" / "subs",
    ):
        if candidate.is_dir():
            return candidate
    return None


_RESERVED_SUB_DIRS = {"_shared", "TEMPLATE"}
_MANIFEST_ENTRY_RE = re.compile(r"^-\s*(\S+)\s*--")


def _manifest_sub_names(subs_dir: Path) -> list[str] | None:
    """MANIFEST.md is the authoritative name list (PROTOCOL.md 5) when present.
    None means no manifest at all (legacy/pre-bootstrap) -- distinct from an
    existing manifest that happens to list zero names."""
    manifest_path = subs_dir / "MANIFEST.md"
    if not manifest_path.is_file():
        return None
    try:
        text = read_doc(manifest_path)
        if not text.strip():
            # read_doc never raises, so the old `except UnicodeDecodeError`
            # below stopped firing and an unreadable MANIFEST.md started
            # returning [] -- an AUTHORITATIVE empty list, which suppressed
            # every sub in the directory instead of falling back to scanning
            # it. No text at all is "cannot read this", not "lists nothing";
            # a manifest with prose and zero entries still returns [].
            return None
    except (OSError, UnicodeDecodeError):
        # Unreadable/corrupt MANIFEST.md degrades to "no manifest" (dir-scan
        # fallback) rather than raising -- a background scan thread has no
        # console to report to under pythonw.exe, so one bad file must not
        # be able to kill the whole scan silently (same reasoning as
        # load_outbox's try/except just above).
        return None
    names = []
    for line in text.splitlines():
        match = _MANIFEST_ENTRY_RE.match(line.strip())
        if match:
            names.append(match.group(1))
    return names


def load_subs(root: Path) -> list[SubStatus]:
    subs_dir = _find_subs_dir(root)
    if subs_dir is None:
        return []
    manifest_names = _manifest_sub_names(subs_dir)
    if manifest_names is not None:
        candidates = [subs_dir / name for name in manifest_names]
    else:
        # No MANIFEST.md -- fall back to a directory scan, excluding the
        # non-instance entries every subs/ folder carries (TEMPLATE/ is a
        # copy-me starting point, _shared/ is the cross-sub inbox; neither
        # is a running subSaipen even though TEMPLATE/ ships its own STATE.md).
        candidates = [
            p
            for p in sorted(subs_dir.iterdir())
            if p.is_dir() and p.name not in _RESERVED_SUB_DIRS
        ]
    subs = []
    for entry in candidates:
        state_path = entry / "STATE.md"
        if entry.is_dir() and state_path.is_file():
            state = parse_frontmatter(read_doc(state_path))
            outbox = load_outbox(entry / "kitchen")
            log_tail = load_sub_log_tail(entry)
            board_counts = load_sub_board(entry)
            subs.append(
                SubStatus(
                    name=entry.name,
                    path=entry,
                    state=state,
                    outbox=outbox,
                    log_tail=log_tail,
                    board_counts=board_counts,
                )
            )
    return subs


def load_translate(root: Path) -> SubStatus | None:
    for candidate in (root / ".saipen" / "saitranslate", root / ".saitranslate"):
        state_path = candidate / "STATE.md"
        if state_path.is_file():
            state = parse_frontmatter(read_doc(state_path))
            log_tail = load_sub_log_tail(candidate)
            board_counts = load_sub_board(candidate)
            return SubStatus(
                name="saitranslate",
                path=candidate,
                state=state,
                log_tail=log_tail,
                board_counts=board_counts,
            )
    return None


@dataclass
class ProjectStatus:
    root: Path
    state: dict[str, str]
    board: Board
    mtime: float = 0
    subs: list[SubStatus] = field(default_factory=list)
    translate: SubStatus | None = None
    quick_actions: list[dict] = field(default_factory=list)
    subs_stale: bool = False
    subs_stale_details: str = ""
    git_branch: str = ""
    git_dirty: bool = False

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def phase(self) -> str:
        return self.state.get("phase", "?")

    @property
    def task(self) -> str:
        return self.state.get("task", "none")

    @property
    def next_action(self) -> str:
        return self.state.get("next_action", "")

    @property
    def blocker(self) -> str:
        return self.state.get("blocker", "none")

    @property
    def updated(self) -> str:
        return self.state.get("updated", "")

    @property
    def updated_kind(self) -> str:
        return classify_timestamp(self.updated)[1]


# --- Protocol staleness check ---
# Files to compare when checking if a project's local subs/ copy
# has drifted from the canonical version in saipen_home.
_STALENESS_FILES = [
    "PROTOCOL.md",
    "README.md",
    "MANIFEST.md",
    "TEMPLATE/STATE.md",
    "TEMPLATE/BOARD.md",
    "TEMPLATE/LOG.md",
]


def _file_staleness_key(path: Path) -> tuple[float, int] | None:
    """Return (mtime, size) for a file, or None if it doesn't exist."""
    try:
        s = path.stat()
        return (s.st_mtime, s.st_size)
    except OSError:
        return None


def check_subs_staleness(root: Path, state: dict) -> tuple[bool, str]:
    """Compare local subs/ files against canonical copies in saipen_home.
    Returns (stale: bool, details: str) where details names the first
    differing file, or empty if everything matches."""
    saipen_home = state.get("saipen_home", "")
    if not saipen_home:
        return False, ""
    canon_root = Path(saipen_home) / "extensions" / "subs"
    if not canon_root.is_dir():
        return False, ""

    subs_dir = _find_subs_dir(root)
    if subs_dir is None:
        return False, ""

    for rel_path in _STALENESS_FILES:
        local_path = subs_dir / rel_path
        canon_path = canon_root / rel_path
        local_key = _file_staleness_key(local_path)
        canon_key = _file_staleness_key(canon_path)
        if local_key != canon_key:
            diff = rel_path
            if local_key is None:
                diff += " (missing locally)"
            elif canon_key is None:
                diff += " (missing from canonical)"
            else:
                diff += " (mtime/size differ)"
            return True, diff
    return False, ""


# --- OUTBOX collect ---
_COLLECT_LOG_RE = re.compile(r"RUN: collect \S+ (\S+)(?:\s|$)")
_COLLECT_INBOX_RE = re.compile(r"\| source: \S+ (\S+) \|")
_COLLECT_TICKET_RE = re.compile(r"\[from \S+ (\S+)\]")


def _outbox_status_transform(outbox_text: str, entry_id: str) -> str | None:
    """Flip `- **status:** ready` to `reviewed` inside the ONE named entry's
    block. Returns None when the entry block has no ready status line."""
    lines = outbox_text.splitlines(True)
    in_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        heading = OUTBOX_HEADING_RE.match(stripped)
        if heading:
            in_block = heading.group(1) == entry_id
            continue
        if in_block and stripped.startswith("- **status:"):
            if re.search(r"^- \*\*status:\*\*\s*ready\s*$", stripped, re.MULTILINE):
                lines[i] = line.replace(
                    "- **status:** ready", "- **status:** reviewed", 1
                )
                return "".join(lines)
            return None
    return None


def collect_outbox_entry(root: Path, sub_name: str, entry_id: str) -> dict:
    """Collect one OUTBOX entry from a subSaipen into the main project.

    The CURRENT package contract gates every write (tools/validate.py's
    `--gate collect:<producer>` shape, see saipenview/collect.py):

    - ``status`` must equal EXACTLY ``ready``; ``reviewed`` is an idempotent
      no-op, draft/blocked/stale is a controlled refusal, malformed/unknown is
      a refusal.
    - every handoff field (source_head, source_tree_fingerprint, role_revision,
      producer, coverage, payload, verified, instructions) plus summary and
      critical must be present; producer must name this sub.
    - source_head and source_tree_fingerprint must match the CURRENT source
      identity; role_revision must match the current project-local charter.
    - freshness computation FAILS CLOSED: if the current identity cannot be
      computed, nothing is collected.

    Only after the gate PASSES does the write go ahead: route (critical ->
    new T-### TODO ticket; non-critical -> _shared/inbox.md), then LOG, then
    OUTBOX `reviewed` LAST. Every step is idempotent per stable identity
    ``(sub_name, entry_id)`` -- an already-reviewed entry is a no-op, an
    existing marker skips that step, and a crash after any step resumes
    without duplication. All writes are one coordinator transaction, so an
    external change to any input aborts the whole collect.

    Returns a dict with ok / message / ticket_id.
    """
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%d.%m.%y %H:%M")

    from saipenview import collect as collect_gate

    subs_dir = _find_subs_dir(root)
    if subs_dir is None:
        return {"ok": False, "message": "no subs/ directory found", "ticket_id": None}
    outbox_path = subs_dir / sub_name / "kitchen" / "OUTBOX.md"
    if not outbox_path.is_file():
        return {
            "ok": False,
            "message": f"{sub_name} has no OUTBOX.md",
            "ticket_id": None,
        }

    coord = get_coordinator()
    try:
        with coord.locked(root):
            outbox_text = read_doc(outbox_path)
            entries = parse_outbox(outbox_text)
            entry = next((e for e in entries if e.entry_id == entry_id), None)
            if entry is None:
                return {
                    "ok": False,
                    "message": f"entry '{entry_id}' not found in {sub_name}'s OUTBOX",
                    "ticket_id": None,
                }

            ok, message, kind = collect_gate.check_package(root, sub_name, entry)
            if kind == "reviewed":
                return {
                    "ok": True,
                    "already": True,
                    "message": message,
                    "ticket_id": None,
                }
            if not ok:
                return {
                    "ok": False,
                    "message": message,
                    "ticket_id": None,
                    "kind": kind,
                }

            # --- Gate passed. Build the writes. ---
            targets: dict[Path, Callable[[str], str | None]] = {}
            created_ticket_id = None

            if collect_gate.critical_flag(entry):
                board_path = root / ".saipen" / "BOARD.md"
                if not board_path.is_file():
                    return {
                        "ok": False,
                        "message": "main BOARD.md not found",
                        "ticket_id": None,
                        "kind": "incomplete",
                    }
                board_text = read_doc(board_path)
                already_ticket = re.search(
                    rf"\[from {re.escape(sub_name)} {re.escape(entry_id)}\]",
                    board_text,
                )
                if not already_ticket:
                    next_num = next_ticket_id(board_text)
                    created_ticket_id = f"T-{next_num:03d}"
                    desc = escape_pipe(
                        " ".join(
                            (
                                entry.title
                                + (f" -- {entry.summary}" if entry.summary else "")
                            ).split()
                        )
                    )
                    ticket_line = (
                        f"- [ ] {created_ticket_id} [from {sub_name} {entry_id}] {desc}"
                    )
                    targets[board_path] = lambda t, tl=ticket_line: _insert_into_todo(
                        t, tl
                    )
                    message = (
                        f"created {created_ticket_id} for critical entry "
                        f"'{entry_id}' from {sub_name}"
                    )
                else:
                    line = board_text[
                        board_text.rfind("\n", 0, already_ticket.start()) + 1 :
                    ]
                    line = line.split("\n", 1)[0]
                    tid_match = re.search(r"\b(T-\d+)\b", line)
                    created_ticket_id = tid_match.group(1) if tid_match else None
                    message = (
                        f"entry '{entry_id}' from {sub_name} already collected "
                        f"({created_ticket_id})"
                    )
            else:
                inbox_path = subs_dir / "_shared" / "inbox.md"
                inbox_text = read_doc(inbox_path)
                if not re.search(
                    rf"\| source: {re.escape(sub_name)} {re.escape(entry_id)} \|",
                    inbox_text,
                ):
                    summary = escape_pipe(entry.summary or entry.title)
                    refs = (entry.fields.get("main_project_refs") or "").strip()
                    refs_text = f" | ref: {escape_pipe(refs)}" if refs else ""
                    inbox_line = (
                        f"- {date_str} | source: {sub_name} {entry_id} | "
                        f"{summary}{refs_text}"
                    )
                    targets[inbox_path] = lambda t, il=inbox_line: (
                        (t.rstrip("\n") + "\n" if t.strip() else "") + il + "\n"
                    )
                    message = (
                        f"appended '{entry_id}' from {sub_name} to inbox (non-critical)"
                    )

            log_path = root / ".saipen" / "LOG.md"
            if not log_path.is_file():
                return {
                    "ok": False,
                    "message": "main LOG.md not found",
                    "ticket_id": None,
                    "kind": "incomplete",
                }
            log_text = read_doc(log_path)
            if not re.search(
                rf"RUN: collect {re.escape(sub_name)} {re.escape(entry_id)}(?:\s|$)",
                log_text,
            ):
                next_event = next_event_id(log_text)
                parent = f" [parent: E-{next_event - 1}]" if next_event > 1 else ""
                target = f" -> {created_ticket_id}" if created_ticket_id else ""
                log_line = (
                    f"- {date_str} [E-{next_event}]{parent} [T-none] RUN: collect "
                    f"{sub_name} {entry_id}{target}"
                )
                targets[log_path] = lambda t, ll=log_line: (
                    (t.rstrip("\n") + "\n" if t.strip() else "") + ll + "\n"
                )

            new_outbox = _outbox_status_transform(outbox_text, entry_id)
            if new_outbox is not None:
                targets[outbox_path] = lambda t, no=new_outbox: no

            deps = [outbox_path, log_path]
            state_path = root / ".saipen" / "STATE.md"
            if state_path.is_file():
                deps.append(state_path)
            board_path_dep = root / ".saipen" / "BOARD.md"
            if board_path_dep.is_file() and board_path_dep not in targets:
                deps.append(board_path_dep)

            coord.transaction(
                root,
                targets,
                deps=deps,
            )

        return {"ok": True, "message": message, "ticket_id": created_ticket_id}
    except ConflictError:
        return {
            "ok": False,
            "message": "project changed concurrently; retry",
            "ticket_id": None,
        }
    except (AgentOwnershipError, MutationRejected, OSError):
        return {
            "ok": False,
            "message": "collect refused (project changed or agent owns it); retry",
            "ticket_id": None,
        }


def load_log_tail(root: Path, max_lines: int = 5) -> list[str]:
    log_path = root / ".saipen" / "LOG.md"
    if not log_path.is_file():
        return []
    try:
        lines = [
            line.strip()
            for line in read_doc(log_path).splitlines()
            if line.strip().startswith("-")
        ]
        return lines[-max_lines:]
    except OSError:
        return []


# --- Quick action detection ---
# Map file presence to contextual run-commands the action bar can offer.
_QUICK_ACTION_RULES = [
    (
        "package.json",
        [
            ("npm run dev", "npm run dev"),
            ("npm start", "npm start"),
            ("npm test", "npm test"),
            ("npm run build", "npm run build"),
        ],
    ),
    (
        "Cargo.toml",
        [
            ("cargo build", "cargo build"),
            ("cargo test", "cargo test"),
        ],
    ),
    (
        "go.mod",
        [
            ("go build", "go build"),
            ("go test", "go test"),
        ],
    ),
    ("Makefile", [("make", "make")]),
    ("makefile", [("make", "make")]),
    ("Gemfile", [("bundle exec", "bundle exec")]),
    ("CMakeLists.txt", [("cmake --build .", "cmake --build .")]),
]


def detect_quick_actions(root: Path) -> list[dict]:
    """Scan project root for well-known files and return a list of
    {label, command} dicts the UI can render as action buttons.
    Checks in priority order, stops at the first match."""
    for filename, actions in _QUICK_ACTION_RULES:
        if (root / filename).is_file():
            return [{"label": label, "command": cmd} for label, cmd in actions]
    return []


def get_git_status(root: Path) -> tuple[str, bool]:
    if not (root / ".git").exists():
        return "", False
    try:
        CREATE_NO_WINDOW = 0x08000000
        bp = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        if bp.returncode != 0:
            return "", False
        # A dead reader thread (Bad file descriptor under load) leaves stdout
        # None -- guard it so the scan thread never raises (T-179).
        branch = (bp.stdout or "").strip()
        sp = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        dirty = bool((sp.stdout or "").strip())
        return branch, dirty
    except (OSError, subprocess.SubprocessError):
        return "", False


def load_project(root: Path, with_git: bool = True) -> ProjectStatus | None:
    """Parse one project's .saipen/ state.

    `with_git=False` skips the git branch/dirty lookup, which is measured at
    ~97% of this function's total cost (48ms of 50ms -- it spawns two `git`
    subprocesses). The fast UI refresh (Api.refresh_known) uses that to poll
    every few seconds cheaply; git state can't change from a STATE.md edit
    anyway, so the caller carries the previous values forward and the slow
    full scan refreshes them.
    """
    saipen_dir = root / ".saipen"
    state_path = saipen_dir / "STATE.md"
    board_path = saipen_dir / "BOARD.md"
    if not state_path.is_file():
        return None
    state = parse_frontmatter(read_doc(state_path))
    board = parse_board(read_doc(board_path)) if board_path.is_file() else Board()
    subs_stale, subs_stale_details = check_subs_staleness(root, state)
    quick_actions = detect_quick_actions(root)
    branch, dirty = get_git_status(root) if with_git else ("", False)
    try:
        mtime = state_path.stat().st_mtime
    except OSError:
        mtime = 0
    return ProjectStatus(
        root=root,
        state=state,
        board=board,
        mtime=mtime,
        subs=load_subs(root),
        translate=load_translate(root),
        quick_actions=quick_actions,
        subs_stale=subs_stale,
        subs_stale_details=subs_stale_details,
        git_branch=branch,
        git_dirty=dirty,
    )
