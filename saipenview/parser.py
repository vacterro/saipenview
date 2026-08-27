"""Parses STATE.md frontmatter and BOARD.md ticket sections.

Not a full YAML parser -- SAIPEN's own STATE.md frontmatter is flat
key: value pairs (RFC.md 1.2), so a line-based parser is enough and
sidesteps YAML's backslash-escape traps on Windows paths.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from saipenview import protocol, saio
from saipenview.ownership import AgentOwnershipError
from saipenview.protocol_write import (
    _canonical_read_deps,
    escape_pipe,
    get_coordinator,
)
from saipenview.tailio import tail_entry_lines
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


def _refuse_dict(code: str, message: str, **extra) -> dict:
    """One structured refusal in the normalized mutation-result contract."""
    out = {
        "ok": False,
        "code": code,
        "message": message,
        "changed_files": [],
        "retryable": code in ("WRITER_BUSY", "STALE_STATE", saio.STALE_FRESHNESS),
        "recovery_required": False,
        "op_id": None,
    }
    out.update(extra)
    return out


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key_raw, _, value = line.partition(":")
        key = key_raw.strip()
        if key in fields:
            # duplicate closed field => MALFORMED
            return {}
        fields[key] = _unquote(value)
    return fields


def update_state(root: Path, updates: dict[str, str]) -> dict:
    """Patch STATE.md frontmatter through the canonical writer pipeline.

    The decision (rendered STATE bytes) is bound to the exact snapshot read:
    the plan's precondition is that read's hash, revalidated by the canonical
    journal under the OS writer lock before commit. Returns the normalized
    mutation result contract.

    W2-021: only explicitly allowlisted keys are written; values must be
    single-line scalars (no embedded newlines or pipe chars). This prevents
    malicious RPC payloads from manufacturing extra frontmatter fields or
    breaking the YAML-like parser.
    """
    import datetime

    # W2-021: explicit writable-field allowlist. Anything not on this list is
    # silently dropped, never written, never errors the caller with a noisy
    # "unknown field" message that could leak implementation details.
    _STATE_FIELD_ALLOWLIST = frozenset({
        "phase", "task", "next_action", "blocker", "agent",
        "saipen_version", "schema_version", "last_event",
        "style_contract", "saipen_home", "mode", "updated",
        "transition_from", "execution_intent", "converge_target",
        "attempt", "human_note",
    })

    # W2-021: sanitize keys and values. Strip unsafe content.
    sanitized: dict[str, str] = {}
    for k, v in updates.items():
        safe_key = k.strip()
        if not safe_key or "\n" in safe_key or "|" in safe_key:
            continue  # drop malformed keys
        if safe_key not in _STATE_FIELD_ALLOWLIST:
            continue  # drop unknown fields silently
        safe_val = str(v).replace("\n", " ").replace("|", "\\|")[:200]
        sanitized[safe_key] = safe_val
    if not sanitized:
        return _refuse_dict("VALIDATION_FAILED", "no writable fields in updates")

    state_path = root / ".saipen" / "STATE.md"
    if not state_path.is_file():
        return _refuse_dict("VALIDATION_FAILED", "STATE.md not found")

    def op_fn(r: Path, attempt: int):
        docs = saio.snapshot(r, [".saipen/STATE.md"])
        doc = docs[".saipen/STATE.md"]
        text = doc.text_norm
        match = FRONTMATTER_RE.match(text)
        if not match:
            return _refuse_dict(
                "VALIDATION_FAILED", "STATE.md has no frontmatter block"
            )
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
            if k in sanitized:
                new_lines.append(f"{k}: {sanitized[k]}")
                updated_keys.add(k)
            else:
                new_lines.append(line)

        for k, v in sanitized.items():
            if k not in updated_keys:
                new_lines.append(f"{k}: {v}")

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        if "updated" not in sanitized:
            found = False
            for i, line in enumerate(new_lines):
                if line.startswith("updated:"):
                    new_lines[i] = f"updated: {now_str}"
                    found = True
                    break
            if not found:
                new_lines.append(f"updated: {now_str}")
        new_text = "---\n" + "\n".join(new_lines) + "\n---\n" + text[match.end() :]
        return saio.plan(
            r,
            "viewer-state",
            {"operation": "viewer-state", "updates": sorted(updates)},
            [(".saipen/STATE.md", "state", new_text, doc)],
            {".saipen/STATE.md": doc.raw_hash},
            read_deps=_canonical_read_deps(r, {".saipen/STATE.md"}),
        )

    try:
        return get_coordinator().mutate(root, op_fn)
    except AgentOwnershipError as exc:
        return _refuse_dict("WRITER_BUSY", str(exc))
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))


@dataclass
class Ticket:
    ticket_id: str
    status: str  # " " open, "x" done, "/" in-progress
    description: str
    blocker: str = ""
    errors: list[str] = field(default_factory=list)


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
# the checkbox. The AUTHORITY for every lifecycle edge is the canonical
# SAIOPS engine (saipenview/saio.py): claim (start), ticket_move (block/
# unblock), finish_ticket (done). The viewer NEVER re-implements a ticket
# transition; it delegates and surfaces the canonical refusal. `reopen` has no
# canonical operation, so it is a journaled board-only move (a finished
# ticket is never STATE.task, so board-only cannot split STATE/BOARD).
_VIEWER_TICKET_ACTIONS = ("start", "done", "block", "unblock", "reopen")

# The closed ticket-field vocabulary is owned by protocol.py (synced from
# tools/saipen_engine/board.py). ONE strict ticket-line grammar serves the
# display parser, the mutation legality and the conformance grader alike:
# escaped pipes preserved, fields order-independent, duplicate single-valued
# fields malformed (never last-write-wins), unknown fields surfaced.
_TICKET_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$")
_PIPE_SENTINEL = "\x00"


def _parse_ticket_line(line: str) -> tuple[str, str, str, dict[str, str], list[str]]:
    """Parse ONE ticket line strictly: (checkbox, tid, description, fields,
    errors). `errors` is empty only for a conformant line -- a malformed line
    is surfaced, never silently normalized."""
    masked = line.replace("\\|", _PIPE_SENTINEL)
    m = TICKET_RE.match(masked)
    if not m:
        return ("", "", "", {}, ["line does not match `- [ ] T-### description`"])
    checkbox, tid, rest = m.groups()
    parts = [p.strip() for p in rest.split(" | ")]
    description = parts[0].replace(_PIPE_SENTINEL, "|")
    fields: dict[str, str] = {}
    errors: list[str] = []
    for part in parts[1:]:
        fm = _TICKET_FIELD_RE.match(part)
        if not fm or fm.group(1) not in protocol.TICKET_FIELDS:
            errors.append(f"unrecognized ticket field {part!r}")
            continue
        key = fm.group(1)
        if key in fields:
            errors.append(f"duplicate single-valued field {key}")
            continue
        fields[key] = fm.group(2).replace(_PIPE_SENTINEL, "|")
    return checkbox, tid, description, fields, errors


def parse_ticket_line(line: str) -> tuple[str, str, str, dict[str, str], list[str]]:
    """PUBLIC strict ticket-line grammar: (checkbox, tid, description, fields,
    errors). The display parser, the mutation legality and the conformance
    grader all consume THIS -- one grammar, never three."""
    return _parse_ticket_line(line)


def ticket_fields(line: str) -> dict[str, str]:
    """The strict fields of one ticket line (empty when malformed)."""
    return _parse_ticket_line(line)[3]


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


def ticket_transition_error(
    root: Path, ticket_id: str, action: str, reason: str | None = None
) -> str | None:
    """The canonical refusal message for one ticket action, or None when the
    canonical engine would accept it. The UI derives disable/reason text from
    this SAME authority the backend enforces -- the canonical SAIOPS plan
    builders decide, never a local copy of the state machine."""
    if action not in _VIEWER_TICKET_ACTIONS:
        return f"unknown ticket action {action!r}"
    try:
        agent = saio.agent_for(root)
    except saio.SaioUnavailable as exc:
        return str(exc)
    ops = saio.engine(root)["operations"]
    with get_coordinator().locked(root):
        if action == "start":
            # Public dry-run: the same claim authority the mutation uses.
            result = ops.plan_claim(root, ticket_id, agent, explicit=True)
        elif action == "done":
            result = ops.finish_ticket(root, ticket_id, agent, dry_run=True)
        elif action in ("block", "unblock"):
            payload = (reason or "").strip()
            if action == "block" and not payload:
                return "block requires a non-empty reason: the facts/dead ends that justify the block"
            if action == "unblock" and not payload:
                return "unblock requires a non-empty decision: the evidence that lifts the block"
            result = ops.ticket_move(
                root, action, ticket_id, agent, payload, dry_run=True
            )
        elif action == "reopen":
            result = _reopen_legality(root, ticket_id)
    return saio.refusal_message(result) if result is not None else None


def _reopen_legality(root: Path, ticket_id: str) -> dict | None:
    """The viewer-only reopen legality: DONE [x] ticket -> TODO. Returns a
    refusal dict or None when legal."""
    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        return _refuse_dict("TICKET_NOT_FOUND", "BOARD.md not found")
    section = None
    for line in read_doc(board_path).splitlines():
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            section = heading.group(1)
            continue
        t = TICKET_RE.match(line.strip())
        if t and t.group(2) == ticket_id:
            if section != "DONE":
                return _refuse_dict(
                    "ILLEGAL_TICKET_LIFECYCLE",
                    f"reopen accepts only a ## DONE ticket; {ticket_id} is "
                    f"under ## {section}",
                )
            return None
    return _refuse_dict("TICKET_NOT_FOUND", f"{ticket_id} not on the board")


def move_ticket(
    root: Path, ticket_id: str, action: str, blocker_reason: str | None = None
) -> dict:
    """Move a ticket between BOARD sections -- DELEGATED to the canonical
    SAIOPS engine (one lifecycle authority; the viewer is a client).

    start/done/block/unblock are the canonical claim / finish_ticket /
    ticket_move operations (journaled LOG+BOARD+STATE, OS writer lock,
    recovery). `done` is ONLY the canonical SHIP->DONE closure: the canonical
    gate requires phase SHIP, STATE.task == the ticket, exactly one DOING --
    the viewer cannot manufacture DONE any other way. `reopen` has no
    canonical operation, so it is a journaled board-only move.

    Returns the normalized mutation result contract.
    """
    if action not in _VIEWER_TICKET_ACTIONS:
        return _refuse_dict("VALIDATION_FAILED", f"unknown ticket action {action!r}")
    try:
        agent = saio.agent_for(root)
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))
    try:
        coord = get_coordinator()
        with coord.locked(root):
            if action == "start":
                result = saio.claim(root, ticket_id, agent, explicit=True)
            elif action == "done":
                result = saio.finish(root, ticket_id, agent)
            elif action == "block":
                result = saio.ticket_block(
                    root, ticket_id, agent, (blocker_reason or "").strip()
                )
            elif action == "unblock":
                result = saio.ticket_unblock(
                    root, ticket_id, agent, (blocker_reason or "").strip()
                )
            else:
                return _reopen_ticket(root, ticket_id)
            # The delegated canonical ops apply internally; register their
            # post-write fingerprints so the watcher attributes every written
            # protocol file to the app (same finalize path as coordinator plans).
            if result.get("ok"):
                coord.finalize_self_writes(root, result.get("changed_files", []))
            return result
    except AgentOwnershipError as exc:
        return _refuse_dict("WRITER_BUSY", str(exc))
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))


def _reopen_ticket(root: Path, ticket_id: str) -> dict:
    """Journaled board-only DONE -> TODO reopen (no canonical op exists; a
    finished ticket is never STATE.task, so board-only cannot split
    STATE/BOARD). The DONE [x] line becomes a TODO [ ] line under ## TODO."""

    def op_fn(r: Path, attempt: int):
        docs = saio.snapshot(r, [".saipen/BOARD.md"])
        doc = docs[".saipen/BOARD.md"]
        legality = _reopen_legality(r, ticket_id)
        if legality is not None:
            return _refuse_dict(legality["code"], legality["message"])
        lines = doc.text_norm.splitlines(True)
        ticket_idx = -1
        for i, line in enumerate(lines):
            heading = SECTION_HEADING_RE.match(line.strip())
            if heading:
                continue
            t = TICKET_RE.match(line.strip())
            if t and t.group(2) == ticket_id:
                ticket_idx = i
                break
        ticket_line = lines.pop(ticket_idx)
        ticket_line = _rewrite_checkbox(ticket_line, " ")
        target_idx = -1
        insert_pos = len(lines)
        for i, line in enumerate(lines):
            heading = SECTION_HEADING_RE.match(line.strip())
            if heading:
                if heading.group(1) == "TODO":
                    target_idx = i
                elif target_idx >= 0:
                    insert_pos = i
                    break
        lines.insert(insert_pos if target_idx >= 0 else len(lines), ticket_line)
        new_text = "".join(lines)
        return saio.plan(
            r,
            "viewer-reopen",
            {"operation": "viewer-reopen", "ticket": ticket_id},
            [(".saipen/BOARD.md", "board", new_text, doc)],
            {".saipen/BOARD.md": doc.raw_hash},
            read_deps=_canonical_read_deps(r, {".saipen/BOARD.md"}),
        )

    return get_coordinator().mutate(root, op_fn)


def reorder_ticket(
    root: Path, ticket_id: str, section: str, before_ticket_id: str | None = None
) -> dict:
    """Move a ticket line to a new position WITHIN its section (T-175),
    committed through the canonical writer pipeline.

    ``before_ticket_id`` is the ticket the dragged row should land before;
    None appends to the end of the section. Order inside a section is the
    order of its lines -- and board order is priority (RFC 1.6), so a
    drag-reordered board is a re-prioritised one. Returns the normalized
    mutation result contract.
    """
    if section not in _SECTION_LISTS:
        return _refuse_dict("VALIDATION_FAILED", f"unknown section {section!r}")
    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        return _refuse_dict("TICKET_NOT_FOUND", "BOARD.md not found")

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
        return get_coordinator().mutate_doc(board_path, transform)
    except AgentOwnershipError as exc:
        return _refuse_dict("WRITER_BUSY", str(exc))
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))


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
# W2-024: capture the description payload from the LOG line so we can
# bind the operation_id to its canonical payload and reject mismatches.
_MANUAL_WORK_PAYLOAD_RE = re.compile(
    r"\[E-(\d+)\] \[(T-\d+)\] ?\[op: ([^\]]+)\] RUN: manual work recorded -- (.*)$"
)


def _new_operation_id() -> str:
    import uuid

    return "mw-" + uuid.uuid4().hex[:12]


def record_manual_work(
    root: Path, description: str, operation_id: str | None = None
) -> dict:
    """Record a user's manual edit as a board entry (T-127), committed through
    the CANONICAL writer pipeline (journaled LOG+BOARD+STATE, OS lock,
    recovery).

    Idempotency is by OPERATION ID, never by human prose (repair mission P1):
    two legitimate separate actions named "updated docs" must remain two
    records. ``operation_id`` is generated at UI invocation and carried
    through retry/resume; a retry with the same id resumes the original
    ticket, while the same description with a different id is a fresh record.
    The id is persisted in the LOG line as ``[op: <id>]``.

    Crash safety: the plan writes LOG + BOARD + STATE in ONE journaled
    operation. A crash after any write leaves a PREPARED/APPLYING journal;
    recovery rolls it forward (idempotent) -- never a duplicate, never a
    half-success reported as done.
    """
    description = " ".join(str(description or "").split())
    if not description:
        return _refuse_dict("VALIDATION_FAILED", "description is empty")
    escaped = escape_pipe(description)
    op_id = operation_id or _new_operation_id()

    def op_fn(r: Path, attempt: int):
        docs = saio.snapshot(
            r, [".saipen/STATE.md", ".saipen/BOARD.md", ".saipen/LOG.md"]
        )
        log_doc = docs[".saipen/LOG.md"]
        board_doc = docs[".saipen/BOARD.md"]
        state_doc = docs[".saipen/STATE.md"]
        log_text = log_doc.text_norm
        board_text = board_doc.text_norm

        # Idempotent resume: did a prior attempt with THIS operation_id already
        # write the LOG line?
        for m in re.finditer(_MANUAL_WORK_PAYLOAD_RE, log_text):
            if m.group(3) == op_id:
                event_id = f"E-{m.group(1)}"
                ticket_id = m.group(2)
                # W2-024: bind operation_id to canonical normalized payload.
                # Same id+same payload -> resume/no-op. Same id+different
                # payload -> IDEMPOTENCY_CONFLICT with zero writes.
                persisted_desc = m.group(4).strip()
                if persisted_desc != description:
                    return _refuse_dict(
                        "IDEMPOTENCY_CONFLICT",
                        f"operation_id {op_id} bound to payload "
                        f"{persisted_desc!r}; got {description!r}",
                    )
                if re.search(rf"\b{re.escape(ticket_id)}\b", board_text):
                    return {
                        "ok": True,
                        "code": "ALREADY_RECORDED",
                        "message": "already recorded",
                        "changed_files": [],
                        "retryable": False,
                        "recovery_required": False,
                        "ticket_id": ticket_id,
                        "event": event_id,
                    }
                ticket_line = f"- [ ] {ticket_id} Manual: {escaped} | owner: user"
                new_board = _insert_into_todo(board_text, ticket_line)
                utc = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                new_state = _patch_state_last_event(
                    state_doc.text_norm, int(m.group(1)), utc
                )
                return saio.plan(
                    r,
                    "viewer-manual-work-resume",
                    {"operation": "viewer-manual-work-resume", "op_id": op_id},
                    [
                        (".saipen/BOARD.md", "board", new_board, board_doc),
                        (".saipen/STATE.md", "state", new_state, state_doc),
                    ],
                    {
                        ".saipen/BOARD.md": board_doc.raw_hash,
                        ".saipen/LOG.md": log_doc.raw_hash,
                        ".saipen/STATE.md": state_doc.raw_hash,
                    },
                    expected={"ticket_id": ticket_id, "event": event_id},
                )

        next_event = saio.next_event_id(r, log_text)
        next_ticket = saio.next_ticket_id(r, board_text, log_text)
        ticket_id = f"T-{next_ticket:03d}"
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%d.%m.%y %H:%M")
        utc = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        git_note = _manual_work_git_note(root)
        log_line = (
            f"- {stamp} [E-{next_event}] [{ticket_id}] [op: {op_id}] RUN: "
            f"manual work recorded -- {escaped}{git_note}"
        )
        ticket_line = f"- [ ] {ticket_id} Manual: {escaped} | owner: user"
        new_log = log_text.rstrip("\n") + "\n" + log_line + "\n"
        new_board = _insert_into_todo(board_text, ticket_line)
        new_state = _patch_state_last_event(state_doc.text_norm, next_event, utc)
        return saio.plan(
            r,
            "viewer-manual-work",
            {
                "operation": "viewer-manual-work",
                "op_id": op_id,
                "ticket": ticket_id,
                "event": next_event,
            },
            [
                (".saipen/LOG.md", "log", new_log, log_doc),
                (".saipen/BOARD.md", "board", new_board, board_doc),
                (".saipen/STATE.md", "state", new_state, state_doc),
            ],
            {
                ".saipen/LOG.md": log_doc.raw_hash,
                ".saipen/BOARD.md": board_doc.raw_hash,
                ".saipen/STATE.md": state_doc.raw_hash,
            },
            expected={"ticket_id": ticket_id, "event": f"E-{next_event}"},
        )

    try:
        return get_coordinator().mutate(root, op_fn)
    except AgentOwnershipError as exc:
        return _refuse_dict("WRITER_BUSY", str(exc))
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))


def _patch_state_last_event(state_text: str, last_event: int, updated: str) -> str:
    """Set STATE.last_event + updated without touching any other field."""
    match = FRONTMATTER_RE.match(state_text)
    if not match:
        return state_text
    lines = match.group(1).splitlines()
    out = []
    set_last = set_updated = False
    for line in lines:
        if line.startswith("last_event:"):
            out.append(f"last_event: {last_event}")
            set_last = True
            continue
        if line.startswith("updated:"):
            out.append(f"updated: {updated}")
            set_updated = True
            continue
        out.append(line)
    if not set_last:
        out.append(f"last_event: {last_event}")
    if not set_updated:
        out.append(f"updated: {updated}")
    return "---\n" + "\n".join(out) + "\n---\n" + state_text[match.end() :]


def _manual_work_git_note(root: Path) -> str:
    """Best-effort git context for a manual-work record: HEAD + dirty count."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=10,
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
    """Display parse via the ONE strict ticket-line grammar: fields parse
    identically regardless of order or position, escaped pipes preserved,
    duplicate single-valued fields surfaced as errors (never last-write-wins),
    and `| blocker: X | verify: Y` renders blocker as exactly `X`."""
    board = Board()
    current: str | None = None
    for line in text.splitlines():
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            current = heading.group(1)
            continue
        if not current:
            continue
        checkbox, ticket_id, description, fields, errors = _parse_ticket_line(
            line.strip()
        )
        if not ticket_id:
            continue
        getattr(board, _SECTION_LISTS[current]).append(
            Ticket(
                ticket_id,
                checkbox,
                description,
                fields.get("blocker", ""),
                errors,
            )
        )
    return board


# The strict OUTBOX parser is the ONE parser (repair mission P1): duplicates
# are structural errors, `critical` is typed true/false only. The display type
# is re-exported so api.py keeps one import surface.
from saipenview.outbox import OutboxEntry  # noqa: E402


def parse_outbox(text: str) -> list[OutboxEntry]:
    """Parse OUTBOX entries via the STRICT single-valued grammar (repair
    mission P1): duplicate fields/entry-ids are structural errors, never
    last-write-wins. Callers that can act on an entry MUST refuse one with
    errors; read-only display may show the error marker."""
    from saipenview.outbox import parse_outbox_strict

    entries, _errors = parse_outbox_strict(text)
    return entries


def load_sub_log_tail(sub_path: Path, max_lines: int = 3) -> list[str]:
    """Return last N LOG.md entries for a subSaipen."""
    log_path = sub_path / "LOG.md"
    if not log_path.is_file():
        return []
    try:
        # PERF-007: bounded backward tail -- never reads the whole LOG just
        # to show the last three entries. Legacy whole-file decode remains
        # the fallback for BOM'd/UTF-16/pathological files (tailio returns
        # None) and for files whose entries are sparse beyond the budget.
        tail = tail_entry_lines(log_path, max_lines)
        if tail is not None:
            return tail
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
            name = match.group(1)
            # CORE-005: reject manifest entries that are not valid sub IDs
            if _validate_manifest_sub_name(name):
                names.append(name)
    return names


def _validate_manifest_sub_name(name: str) -> bool:
    """CORE-005: reject path traversal, separators, absolute/drive/UNC forms.
    Returns True when the name is safe to use as a sub directory."""
    from saipenview.collect import validate_sub_id
    return validate_sub_id(name) is None


def load_subs(root: Path) -> list[SubStatus]:
    subs_dir = _find_subs_dir(root)
    if subs_dir is None:
        return []
    manifest_names = _manifest_sub_names(subs_dir)
    if manifest_names is not None:
        # CORE-005: filter invalid sub names from manifest
        safe_names = [n for n in manifest_names if _validate_manifest_sub_name(n)]
        candidates = [subs_dir / name for name in safe_names]
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


def _file_staleness_key(path: Path) -> tuple[str, str] | None:
    """Content identity of a file: (sha256, b'' marker) -- never (mtime, size).

    mtime/size is not content: the same bytes copied at another time reads
    stale, and same-size + preserved-mtime with different bytes reads fresh.
    The canonical comparison normalizes line endings (the canonical copies are
    checked against the home's own copies, which share the home's newline
    convention); raw bytes would cry wolf on a CRLF home.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(), ""


def check_subs_staleness(root: Path, state: dict) -> tuple[bool, str]:
    """Compare local subs/ files against canonical copies in saipen_home by
    CONTENT identity (repair mission P1: mtime/size is a false-stale/false-
    fresh lie). Returns (stale, details)."""
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
                diff += " (content differs)"
            return True, diff
    return False, ""


# --- OUTBOX collect ---


def collect_outbox_entry(
    root: Path, sub_name: str, entry_id: str, *, explicit: bool = False
) -> dict:
    """Collect one OUTBOX entry from a subSaipen into the main project,
    committed through the CANONICAL writer pipeline.

    Authorization order (repair mission P0):

    1. STRICT parse -- duplicate fields/entry-ids and a non-boolean `critical`
       are MALFORMED, zero writes.
    2. GATE -- exact `ready`, every handoff field, producer identity,
       source_head + source_tree_fingerprint + role_revision current. Returns
       an immutable freshness PROOF.
    3. BOUNDARY -- unresolved external changes for this project (backend
       registry) and any canonical recovery debt block the collect.
    4. POLICY -- the producer's charter `collect_policy` decides routing:
       `explicit` needs the explicit named authorization (the GUI click);
       `core-review` creates a normal Core ticket and never applies a payload
       directly; `automatic` allows direct intake.
    5. APPLY -- one journaled operation (BOARD/inbox + LOG + OUTBOX reviewed +
       STATE last_event) whose plan carries the proof. The freshness proof is
       REVALIDATED under the canonical OS writer lock immediately before
       commit (STALE_FRESHNESS => zero writes if the source tree, OUTBOX or
       any main checkpoint moved after the gate).

    Returns the normalized mutation result contract.
    """
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%d.%m.%y %H:%M")

    from saipenview import collect as collect_gate
    from saipenview.outbox import parse_outbox_strict, reviewed_transform

    subs_dir = _find_subs_dir(root)
    if subs_dir is None:
        return _refuse_dict("VALIDATION_FAILED", "no subs/ directory found")
    # CORE-017: resolve the effective OUTBOX identity ONCE at the start and
    # carry it through the entire collect. The initial read can come from
    # whichever layout _find_subs_dir found, but the canonical snapshot in
    # op_fn must use the same resolved project-relative path.
    # Prefer the canonical .saipen/ layout when it exists.
    canonical_outbox = root / ".saipen" / "extensions" / "subs" / sub_name / "kitchen" / "OUTBOX.md"
    legacy_outbox = root / "extensions" / "subs" / sub_name / "kitchen" / "OUTBOX.md"
    if canonical_outbox.is_file():
        outbox_path = canonical_outbox
        outbox_rel = f".saipen/extensions/subs/{sub_name}/kitchen/OUTBOX.md"
    elif legacy_outbox.is_file():
        outbox_path = legacy_outbox
        outbox_rel = f"extensions/subs/{sub_name}/kitchen/OUTBOX.md"
    else:
        return _refuse_dict("TICKET_NOT_FOUND", f"{sub_name} has no OUTBOX.md")

    coord = get_coordinator()
    try:
        with coord.locked(root):
            outbox_text = read_doc(outbox_path)
            entries, parse_errors = parse_outbox_strict(outbox_text)
            if parse_errors:
                return _refuse_dict(
                    saio.MALFORMED_OUTBOX,
                    "malformed OUTBOX: " + "; ".join(parse_errors[:3]),
                )
            entry = next((e for e in entries if e.entry_id == entry_id), None)
            if entry is None:
                return _refuse_dict(
                    "TICKET_NOT_FOUND",
                    f"entry '{entry_id}' not found in {sub_name}'s OUTBOX",
                )

            ok, message, kind, proof = collect_gate.check_package(root, sub_name, entry)
            if kind == "reviewed":
                return {
                    "ok": True,
                    "code": "ALREADY_REVIEWED",
                    "message": message,
                    "changed_files": [],
                    "retryable": False,
                    "recovery_required": False,
                    "ticket_id": None,
                }
            if not ok:
                if kind == "malformed":
                    return _refuse_dict(saio.MALFORMED_OUTBOX, message)
                return _refuse_dict(
                    saio.STALE_FRESHNESS if kind == "stale" else kind, message
                )

            # Boundary: unresolved external changes + canonical recovery debt.
            from saipenview.external_changes import get_registry, normalize_rel

            # Registry key is normalized; outbox_rel is the snapshot-identity (canonical or legacy)
            try:
                registry_rel = normalize_rel(outbox_rel)
            except ValueError:
                registry_rel = outbox_rel
            unresolved = [
                c
                for c in get_registry().unresolved(str(root))
                if c.rel_path != registry_rel  # the package itself is the subject
            ]
            if unresolved:
                return _refuse_dict(
                    saio.BOUNDARY_VIOLATION,
                    "unexplained external change(s) block collect: "
                    + "; ".join(c.rel_path for c in unresolved[:5]),
                )
            recovery = saio.recovery_status(root)
            if recovery.get("blocked"):
                return _refuse_dict(
                    "RECOVERY_REQUIRED",
                    "unresolved canonical operation(s) block collect: "
                    + ", ".join(
                        str(p.get("op_id")) for p in recovery.get("pending", [])
                    ),
                    recovery_required=True,
                )

            # Policy: the producer's charter collect_policy decides routing.
            policy = collect_gate.resolve_collect_policy(root, sub_name)
            if policy is None:
                return _refuse_dict(
                    "VALIDATION_FAILED",
                    f"{sub_name} charter carries no collect_policy "
                    f"(one of automatic/core-review/explicit)",
                )
            if policy == "explicit" and not explicit:
                return _refuse_dict(
                    "DESTRUCTIVE_CONFIRMATION_REQUIRED",
                    f"{sub_name} collect_policy is `explicit` -- a named "
                    "explicit collect authorization is required (the GUI "
                    "one-click collect on the exact entry is one)",
                )
            direct_apply = policy != "core-review"

            def op_fn(r: Path, attempt: int):
                # CORE-017: use the resolved outbox_rel for the snapshot
                docs = saio.snapshot(
                    r,
                    [
                        ".saipen/STATE.md",
                        ".saipen/BOARD.md",
                        ".saipen/LOG.md",
                        outbox_rel,
                    ],
                )
                state_doc = docs[".saipen/STATE.md"]
                board_doc = docs[".saipen/BOARD.md"]
                log_doc = docs[".saipen/LOG.md"]
                outbox_doc = docs[outbox_rel]
                outbox_text = outbox_doc.text_norm
                board_text = board_doc.text_norm
                log_text = log_doc.text_norm

                targets: list[tuple[str, str, str, object]] = []
                created_ticket_id = None

                if direct_apply and collect_gate.critical_flag(entry):
                    already_ticket = re.search(
                        rf"\[from {re.escape(sub_name)} {re.escape(entry_id)}\]",
                        board_text,
                    )
                    if not already_ticket:
                        created_ticket_id = (
                            f"T-{saio.next_ticket_id(r, board_text, log_text):03d}"
                        )
                        desc = escape_pipe(
                            " ".join(
                                (
                                    entry.title
                                    + (f" -- {entry.summary}" if entry.summary else "")
                                ).split()
                            )
                        )
                        ticket_line = (
                            f"- [ ] {created_ticket_id} [from {sub_name} "
                            f"{entry_id}] {desc}"
                        )
                        targets.append(
                            (
                                ".saipen/BOARD.md",
                                "board",
                                _insert_into_todo(board_text, ticket_line),
                                board_doc,
                            )
                        )
                    else:
                        line = board_text[
                            board_text.rfind("\n", 0, already_ticket.start()) + 1 :
                        ]
                        line = line.split("\n", 1)[0]
                        tid_match = re.search(r"\b(T-\d+)\b", line)
                        created_ticket_id = tid_match.group(1) if tid_match else None
                elif direct_apply:
                    inbox_rel = ".saipen/extensions/subs/_shared/inbox.md"
                    inbox_doc = saio.snapshot(r, [inbox_rel])[inbox_rel]
                    inbox_text = inbox_doc.text_norm
                    if not re.search(
                        rf"\| source: {re.escape(sub_name)} "
                        rf"{re.escape(entry_id)} \|",
                        inbox_text,
                    ):
                        summary = escape_pipe(entry.summary or entry.title)
                        refs = (entry.fields.get("main_project_refs") or "").strip()
                        refs_text = f" | ref: {escape_pipe(refs)}" if refs else ""
                        inbox_line = (
                            f"- {date_str} | source: {sub_name} {entry_id} | "
                            f"{summary}{refs_text}"
                        )
                        targets.append(
                            (
                                inbox_rel,
                                "generic",
                                inbox_text.rstrip("\n")
                                + ("\n" if inbox_text.strip() else "")
                                + inbox_line
                                + "\n",
                                inbox_doc,
                            )
                        )
                else:
                    # core-review: a normal Core ticket, never a direct apply.
                    if not re.search(
                        rf"\[from {re.escape(sub_name)} {re.escape(entry_id)}\]",
                        board_text,
                    ):
                        created_ticket_id = (
                            f"T-{saio.next_ticket_id(r, board_text, log_text):03d}"
                        )
                        desc = escape_pipe(
                            " ".join(
                                (
                                    entry.title
                                    + (f" -- {entry.summary}" if entry.summary else "")
                                    + " (core-review: apply via the ticket's "
                                    "VERIFY/REVIEW chain)"
                                ).split()
                            )
                        )
                        ticket_line = (
                            f"- [ ] {created_ticket_id} [from {sub_name} "
                            f"{entry_id}] {desc}"
                        )
                        targets.append(
                            (
                                ".saipen/BOARD.md",
                                "board",
                                _insert_into_todo(board_text, ticket_line),
                                board_doc,
                            )
                        )

                appended_log = not re.search(
                    rf"RUN: collect {re.escape(sub_name)} "
                    rf"{re.escape(entry_id)}(?:\s|$)",
                    log_text,
                )
                if appended_log:
                    next_event = saio.next_event_id(r, log_text)
                    parent = f" [parent: E-{next_event - 1}]" if next_event > 1 else ""
                    target = f" -> {created_ticket_id}" if created_ticket_id else ""
                    log_line = (
                        f"- {date_str} [E-{next_event}]{parent} [T-none] "
                        f"RUN: collect {sub_name} {entry_id}{target}"
                    )
                    targets.append(
                        (
                            ".saipen/LOG.md",
                            "log",
                            log_text.rstrip("\n") + "\n" + log_line + "\n",
                            log_doc,
                        )
                    )

                new_outbox = reviewed_transform(outbox_text, entry_id)
                if new_outbox is None:
                    return _refuse_dict(
                        saio.MALFORMED_OUTBOX,
                        "OUTBOX status flip failed to produce exactly one "
                        "`reviewed`; collect aborted",
                    )
                targets.append(
                    (
                        outbox_rel,
                        "generic",
                        new_outbox,
                        outbox_doc,
                    )
                )

                # STATE.last_event MUST equal the real LOG tail. When the
                # collect LOG line already existed (idempotent resume), no new
                # event was appended -- bumping last_event to the NEXT unused id
                # would claim a nonexistent event (T-204 review finding).
                last_event = (
                    next_event if appended_log else saio.event_tail(r, log_text)
                )
                new_state = _patch_state_last_event(
                    state_doc.text_norm,
                    last_event,
                    now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
                targets.append((".saipen/STATE.md", "state", new_state, state_doc))

                preconditions = {
                    ".saipen/STATE.md": state_doc.raw_hash,
                    ".saipen/BOARD.md": board_doc.raw_hash,
                    ".saipen/LOG.md": log_doc.raw_hash,
                    outbox_rel: outbox_doc.raw_hash,
                }
                operation_plan = saio.plan(
                    r,
                    "viewer-collect",
                    {
                        "operation": "viewer-collect",
                        "sub": sub_name,
                        "entry": entry_id,
                        "policy": policy,
                    },
                    targets,
                    preconditions,
                    expected={"ticket_id": created_ticket_id, "message": message},
                )
                return operation_plan

            def precheck(r: Path):
                return _collect_freshness_precheck(r, proof)

            # The coordinator APPLYs the plan (one _finalize_success path for
            # self-write attribution) and runs the freshness precheck under
            # the canonical writer lock immediately before the journal is
            # PREPARED. STALE_STATE re-decides once on a fresh snapshot.
            return get_coordinator().mutate(root, op_fn, precheck=precheck)

    except AgentOwnershipError as exc:
        return _refuse_dict("WRITER_BUSY", str(exc))
    except saio.SaioUnavailable as exc:
        return _refuse_dict(saio.SAIO_UNAVAILABLE, str(exc))


def _hash_rel(root: Path, rel: str) -> str:
    import hashlib

    try:
        raw = (root / rel).read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(raw).hexdigest()[:16]


def _collect_freshness_precheck(root: Path, proof: dict) -> dict | None:
    """Commit-time freshness proof revalidation (runs under the canonical
    writer lock, immediately before the journal is PREPARED). Any moved input
    of the proof => STALE_FRESHNESS, zero writes.

    W2-013: also re-check the external-change registry here — the initial
    BOUNDARY gate in collect_outbox_entry runs OUTSIDE the writer lock, so a
    new unresolved external event recorded between gate and apply would slip
    through if we only validated file hashes and source identity.
    """
    from saipenview import collect as collect_gate
    from saipenview.external_changes import get_registry

    # W2-013: re-validate boundary under writer lock. New external evidence
    # arriving between the initial gate and this point must block the commit.
    unresolved = get_registry().unresolved(str(root))
    if unresolved:
        return _refuse_dict(
            saio.BOUNDARY_VIOLATION,
            "unexplained external change(s) appeared after the gate; collect refused: "
            + "; ".join(c.rel_path for c in unresolved[:5]),
        )

    try:
        identity = collect_gate.compute_source_identity(root)
    except collect_gate.FreshnessError as exc:
        return _refuse_dict(
            saio.STALE_FRESHNESS,
            f"source freshness computation BLOCKED at apply: {exc}",
        )
    if proof.get("source_head") and identity.source_head != proof["source_head"]:
        return _refuse_dict(
            saio.STALE_FRESHNESS, "source_head moved after the gate; zero writes"
        )
    if (
        proof.get("source_tree_fingerprint")
        and identity.source_tree_fingerprint != proof["source_tree_fingerprint"]
    ):
        return _refuse_dict(
            saio.STALE_FRESHNESS,
            "source tree changed (same HEAD or not) after the gate; zero writes",
        )
    if proof.get("role_revision"):
        try:
            current_rr = collect_gate.current_role_revision(
                root, proof.get("sub_name", "")
            )
        except collect_gate.FreshnessError as exc:
            return _refuse_dict(saio.STALE_FRESHNESS, str(exc))
        if current_rr != proof["role_revision"]:
            return _refuse_dict(
                saio.STALE_FRESHNESS, "role charter changed after the gate; zero writes"
            )
    # Use proof's immutable outbox_rel when present; fallback to canonical for old proofs
    outbox_rel_proof = proof.get("outbox_rel") or f".saipen/extensions/subs/{proof.get('sub_name', '')}/kitchen/OUTBOX.md"
    for key, rel in (
        ("outbox_hash", outbox_rel_proof),
        ("state_hash", ".saipen/STATE.md"),
        ("board_hash", ".saipen/BOARD.md"),
        ("log_hash", ".saipen/LOG.md"),
    ):
        if not proof.get(key):
            continue
        live = _hash_rel(root, rel)
        if live != proof[key]:
            return _refuse_dict(
                saio.STALE_FRESHNESS, f"{rel} changed after the gate; zero writes"
            )
    return None


def load_log_tail(root: Path, max_lines: int = 5) -> list[str]:
    log_path = root / ".saipen" / "LOG.md"
    if not log_path.is_file():
        return []
    try:
        # PERF-007: bounded backward tail (see load_sub_log_tail).
        tail = tail_entry_lines(log_path, max_lines)
        if tail is not None:
            return tail
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
    """PERF-004: single git subprocess for branch + dirty status."""
    if not (root / ".git").exists():
        return "", False
    try:
        CREATE_NO_WINDOW = 0x08000000
        sp = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v2", "--branch"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
        )
        if sp.returncode != 0:
            return "", False
        # Parse branch from header line: # branch.head <name>
        branch = ""
        dirty = False
        for line in (sp.stdout or "").splitlines():
            if line.startswith("# branch.head "):
                branch = line[14:].strip()
            elif not line.startswith("# "):
                # Any non-header line means there are changes.
                dirty = True
                if branch:  # Already found branch, no need to keep scanning.
                    break
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
