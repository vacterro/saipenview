"""Parses STATE.md frontmatter and BOARD.md ticket sections.

Not a full YAML parser -- SAIPEN's own STATE.md frontmatter is flat
key: value pairs (RFC.md 1.2), so a line-based parser is enough and
sidesteps YAML's backslash-escape traps on Windows paths.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from saipenview.textio import read_doc, read_doc_meta, write_doc

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

    text, enc, newline = read_doc_meta(state_path)
    match = FRONTMATTER_RE.match(text)
    if not match:
        return False

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
    new_text = new_frontmatter + text[match.end() :]
    # Atomic write: .tmp -> replace -> no .bak accumulation.
    # Previous versions created STATE.md.bak on every call without
    # cleanup, letting N .bak files accumulate per project.
    # Encoding and newline come back from read_doc_meta so stamping one field
    # doesn't silently re-encode a file we didn't author.
    write_doc(state_path, new_text, enc, newline)
    return True


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

_TICKET_ACTIONS = {
    "start": (" ", "/", "DOING"),
    "done": ("/", "x", "DONE"),
    "reopen": ("x", " ", "TODO"),
    # T-174: BLOCKED tickets carry `[ ]` like TODO ones, so the target section
    # cannot be derived from the checkbox alone -- it is explicit per action.
    "block": (None, " ", "BLOCKED"),
    "unblock": (" ", " ", "TODO"),
}

_TICKET_SECTION_FOR_STATUS = {
    " ": "TODO",
    "/": "DOING",
    "x": "DONE",
}


def move_ticket(
    root: Path, ticket_id: str, action: str, blocker_reason: str | None = None
) -> bool:
    """Changes a ticket's status on BOARD.md and moves it to the correct section.
    Action is one of: start (TODO->DOING), done (DOING->DONE), reopen (DONE->TODO),
    block (TODO/DOING->BLOCKED, appends `| blocker:`), unblock (BLOCKED->TODO).
    Returns True on success."""
    if action not in _TICKET_ACTIONS:
        return False
    old_ch, new_ch, target_section = _TICKET_ACTIONS[action]
    if not target_section:
        return False

    board_path = root / ".saipen" / "BOARD.md"
    if not board_path.is_file():
        return False
    text, enc, newline = read_doc_meta(board_path)

    lines = text.splitlines(True)  # keep line endings
    section_starts: dict[str, int] = {}
    ticket_line_idx = -1
    actual_status = old_ch
    current_heading: str | None = None

    for i, line in enumerate(lines):
        heading = SECTION_HEADING_RE.match(line.strip())
        if heading:
            current_heading = heading.group(1)
            if current_heading not in section_starts:
                section_starts[current_heading] = i
            continue
        if ticket_line_idx < 0:
            ticket = TICKET_RE.match(line.strip())
            if ticket and ticket.group(2) == ticket_id:
                # The ticket's REAL checkbox, which need not be the one the
                # action expects -- "start" on an already-`[x]` ticket is
                # allowed, it just moves where the new status dictates. The
                # replacement below has to target what is actually there:
                # rewriting `[ ]` on a line that reads `[x]` matched nothing,
                # so the line moved to ## DOING still carrying `[x]` and the
                # board came out in exactly the checkbox-vs-section state
                # RFC 1.2 forbids.
                actual_status = ticket.group(1)
                ticket_line_idx = i

    if ticket_line_idx < 0:
        return False

    # Remove the ticket line from its current position
    ticket_line = lines.pop(ticket_line_idx)

    # Update the status marker
    ticket_line = ticket_line.replace(f"[{actual_status}]", f"[{new_ch}]", 1)

    # T-174: blocking appends the reason as a `| blocker:` ticket field. The
    # field list is closed, so a literal pipe in the reason is escaped as \|.
    if action == "block" and blocker_reason and blocker_reason.strip():
        reason = blocker_reason.strip().replace("|", "\\|")
        newline = "\n" if ticket_line.endswith("\n") else ""
        ticket_line = ticket_line.rstrip("\n") + f" | blocker: {reason}" + newline

    # Insert into the target section (after its heading, before next heading or end)
    insert_pos = len(lines)  # default: end of file
    if target_section in section_starts:
        target_idx = section_starts[target_section]
        # Find the next heading after target section, or end of file
        for j in range(target_idx + 1, len(lines)):
            if SECTION_HEADING_RE.match(lines[j].strip()):
                insert_pos = j
                break
        else:
            insert_pos = len(lines)

    lines.insert(insert_pos, ticket_line)
    new_text = "".join(lines)

    write_doc(board_path, new_text, enc, newline)
    return True


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
    text, enc, newline = read_doc_meta(board_path)
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
        return False
    if before_idx >= 0 and before_idx >= section_end:
        return False

    ticket_line = lines.pop(ticket_idx)
    if before_idx > ticket_idx:
        before_idx -= 1
    section_end_adj = section_end - 1 if section_end > ticket_idx else section_end
    insert_pos = before_idx if before_idx >= 0 else section_end_adj
    # No-op: already in place.
    if insert_pos == ticket_idx:
        lines.insert(ticket_idx, ticket_line)
        return True
    lines.insert(insert_pos, ticket_line)

    write_doc(board_path, "".join(lines), enc, newline)
    return True


def record_manual_work(root: Path, description: str) -> dict:
    """Record a user's manual edit as a board entry (T-127).

    The user did something by hand -- edited a project's STATE/BOARD/LOG in an
    editor, made a commit, ran a script. SAIPENVIEW cannot attribute the
    change to a person (the watcher never knows who wrote the file), so it
    does not try: the UI asks, the user confirms, and THIS function writes the
    explicit record. One board ticket + one LOG evidence line, both through
    the single-writer atomic path. Returns ``{"ok": True}`` or an error dict.
    """
    description = " ".join(str(description or "").split())
    if not description:
        return {"ok": False, "error": "description is empty"}

    board_path = root / ".saipen" / "BOARD.md"
    log_path = root / ".saipen" / "LOG.md"
    if not board_path.is_file():
        return {"ok": False, "error": "BOARD.md not found"}

    # Next T-### across the whole board (T-### must never be reused). Zero-
    # padded to three digits, the board's own convention.
    board_text, enc, newline = read_doc_meta(board_path)
    existing_ids = [int(m) for m in re.findall(r"\bT-(\d+)\b", board_text)]
    next_ticket = max(existing_ids) + 1 if existing_ids else 1
    ticket_id = f"T-{next_ticket:03d}"

    ticket = f"- [ ] {ticket_id} Manual: {description} | owner: user"
    if "\n## TODO" in "\n" + board_text:
        # Insert under ## TODO (after its heading, before the next heading).
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
        lines.insert(insert_at, ticket + "\n")
        board_text = "".join(lines)
    else:
        board_text = board_text.rstrip("\n") + "\n\n## TODO\n" + ticket + "\n"
    write_doc(board_path, board_text, enc, newline)

    # LOG evidence line (valid skeleton: dated, monotonic E-N, RUN taxonomy).
    log_text, log_enc, log_nl = read_doc_meta(log_path)
    existing_events = [int(m) for m in re.findall(r"\[E-(\d+)\]", log_text)]
    next_event = max(existing_events) + 1 if existing_events else 1
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%d.%m.%y %H:%M")
    git_note = _manual_work_git_note(root)
    log_line = (
        f"- {stamp} [E-{next_event}] [{ticket_id}] RUN: manual work recorded "
        f"-- {description}{git_note}"
    )
    log_text = (
        (log_text.rstrip("\n") + "\n" if log_text.strip() else "") + log_line + "\n"
    )
    write_doc(log_path, log_text, log_enc, log_nl)

    return {"ok": True, "ticket_id": ticket_id, "event": f"E-{next_event}"}


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
    if head.returncode != 0:
        return ""
    dirty = (
        len([ln for ln in status.stdout.splitlines() if ln.strip()])
        if status.returncode == 0
        else 0
    )
    return f" -- at {head.stdout.strip()} ({dirty} dirty files)"


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
_TICKET_ID_RE = re.compile(r"T-(\d+)")
_EVENT_ID_RE = re.compile(r"\[E-(\d+)\]")
_COLLECT_SUB_FM_RE = re.compile(r"^##\s+(\S+):\s*(.*)$", re.MULTILINE)
_COLLECT_STATUS_RE = re.compile(r"^- \*\*status:\*\*\s*ready", re.MULTILINE)


def _highest_ticket_number(text: str) -> int:
    """Find the highest T-### number in a BOARD.md text."""
    max_n = 0
    for match in _TICKET_ID_RE.finditer(text):
        n = int(match.group(1))
        max_n = max(max_n, n)
    return max_n


def _highest_event_number(text: str) -> int:
    """Highest E-### in a LOG.md text; 0 when the log carries none."""
    return max((int(m.group(1)) for m in _EVENT_ID_RE.finditer(text)), default=0)


def collect_outbox_entry(root: Path, sub_name: str, entry_id: str) -> dict:
    """Collect one ready OUTBOX entry from a subSaipen into the main project.

    Per PROTOCOL.md §4:
    - critical: true -> create a new T-### TODO ticket on main BOARD.md
    - critical: false -> append to _shared/inbox.md
    - Mark the entry reviewed in the sub's OUTBOX.md
    - Append a LOG RUN line to the main LOG.md

    Write order (crash safety): main files first, OUTBOX.md last.

    Returns a dict with:
      ok: bool
      message: str (human-readable summary)
      ticket_id: str | None (if a ticket was created)
    """
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    # RFC § 1.2 LOG stamp: DD.MM.YY HH:MM, UTC. This wrote an ISO-ish
    # "%Y-%m-%d %H:%M:%S", which no SAIPEN validator recognises as a dated
    # entry -- so every line this function ever appended counted as undated.
    date_str = now.strftime("%d.%m.%y %H:%M")

    # --- Locate the sub's OUTBOX.md ---
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

    # --- Read and find the entry ---
    outbox_text, outbox_enc, outbox_nl = read_doc_meta(outbox_path)
    lines = outbox_text.splitlines(True)  # keep line endings

    # Find the target entry's heading line index and its status line
    entry_heading_idx = -1
    status_line_idx = -1
    entry_critical = False
    entry_summary = ""
    entry_refs = ""
    entry_title = ""

    i = 0
    while i < len(lines):
        m = _COLLECT_SUB_FM_RE.match(lines[i].strip())
        if m and m.group(1) == entry_id:
            entry_heading_idx = i
            entry_title = m.group(2).strip()
            # Read fields in this entry block (until next heading or EOF)
            # and locate the status line index for later replacement
            j = i + 1
            while j < len(lines):
                next_heading = _COLLECT_SUB_FM_RE.match(lines[j].strip())
                if next_heading:
                    break
                line_stripped = lines[j].strip()
                if line_stripped.startswith("- **status:"):
                    if status_line_idx < 0:
                        status_line_idx = j
                    if "ready" not in line_stripped:
                        # Entry exists but not in 'ready' status
                        return {
                            "ok": False,
                            "message": f"entry '{entry_id}' is not ready (already reviewed or blocked)",
                            "ticket_id": None,
                        }
                elif line_stripped.startswith("- **critical:"):
                    val = line_stripped.split("**critical:**", 1)[-1].strip().lower()
                    entry_critical = val == "true"
                elif line_stripped.startswith("- **summary:"):
                    entry_summary = line_stripped.split("**summary:**", 1)[-1].strip()
                elif line_stripped.startswith("- **main_project_refs:"):
                    entry_refs = line_stripped.split("**main_project_refs:**", 1)[
                        -1
                    ].strip()
                j += 1
            break
        i += 1

    if entry_heading_idx < 0:
        return {
            "ok": False,
            "message": f"entry '{entry_id}' not found in {sub_name}'s OUTBOX",
            "ticket_id": None,
        }

    if status_line_idx < 0:
        return {
            "ok": False,
            "message": f"entry '{entry_id}' has no status field",
            "ticket_id": None,
        }

    # --- Route the entry ---
    created_ticket_id = None

    if entry_critical:
        # Create a new T-### ticket on main BOARD.md
        board_path = root / ".saipen" / "BOARD.md"
        if board_path.is_file():
            board_text, board_enc, board_nl = read_doc_meta(board_path)
            next_num = _highest_ticket_number(board_text) + 1
            created_ticket_id = f"T-{next_num:03d}"

            # Build ticket description with sub reference
            ticket_desc = f"[from {sub_name} {entry_id}] {entry_title}"
            if entry_summary:
                ticket_desc += f" -- {entry_summary}"
            ticket_line = f"- [ ] {created_ticket_id} | {ticket_desc}\n"

            # Find TODO section and insert after heading
            board_lines = board_text.splitlines(True)
            insert_pos = len(board_lines)
            for idx, line in enumerate(board_lines):
                if SECTION_HEADING_RE.match(line.strip()) and line.strip().endswith(
                    "TODO"
                ):
                    insert_pos = idx + 1
                    break
            board_lines.insert(insert_pos, ticket_line)
            new_board = "".join(board_lines)

            # Write main BOARD.md FIRST (crash safety)
            write_doc(board_path, new_board, board_enc, board_nl)
            message = f"created {created_ticket_id} for critical entry '{entry_id}' from {sub_name}"
        else:
            return {
                "ok": False,
                "message": "main BOARD.md not found",
                "ticket_id": None,
            }
    else:
        # Non-critical: append to _shared/inbox.md
        inbox_path = subs_dir / "_shared" / "inbox.md"
        refs_text = f" | ref: {entry_refs}" if entry_refs else ""
        inbox_line = f"- {date_str} | source: {sub_name} {entry_id} | {entry_summary or entry_title}{refs_text}\n"

        if inbox_path.is_file():
            inbox_text, inbox_enc, inbox_nl = read_doc_meta(inbox_path)
        else:
            inbox_text, inbox_enc, inbox_nl = "# Inbox\n\n", "utf-8", "\n"
        inbox_text += inbox_line
        write_doc(inbox_path, inbox_text, inbox_enc, inbox_nl)
        message = f"appended '{entry_id}' from {sub_name} to inbox (non-critical)"

    # --- Append LOG RUN line to main LOG.md ---
    log_path = root / ".saipen" / "LOG.md"
    if log_path.is_file():
        log_text, log_enc, log_nl = read_doc_meta(log_path)
    else:
        log_text, log_enc, log_nl = "# Log\n\n", "utf-8", "\n"

    # E-### continues the project's own sequence. It used to be built from the
    # wall clock ("E-%H%M%S"), which drops a five- or six-digit id into a
    # sequence sitting in the hundreds: unique by luck, monotonic by nothing,
    # and every genuine entry appended afterwards then reads as out-of-order.
    last_event = _highest_event_number(log_text)
    parent = f" [parent: E-{last_event}]" if last_event else ""
    target = f" -> {created_ticket_id}" if created_ticket_id else ""
    log_line = (
        f"- {date_str} [E-{last_event + 1}]{parent} [T-none] RUN: collect "
        f"{sub_name} {entry_id}{target}\n"
    )
    log_text += log_line
    write_doc(log_path, log_text, log_enc, log_nl)

    # --- Mark the OUTBOX entry reviewed LAST (crash safety) ---
    # Replace only the specific entry's status line, not the first match in the whole file
    lines[status_line_idx] = lines[status_line_idx].replace(
        "- **status:** ready", "- **status:** reviewed", 1
    )
    new_outbox = "".join(lines)
    write_doc(outbox_path, new_outbox, outbox_enc, outbox_nl)

    return {"ok": True, "message": message, "ticket_id": created_ticket_id}


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
        branch = bp.stdout.strip()
        sp = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        dirty = bool(sp.stdout.strip())
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
