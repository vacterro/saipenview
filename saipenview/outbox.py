"""Strict OUTBOX parsing: single-valued authority, typed `critical`, one status.

A subSaipen's `kitchen/OUTBOX.md` is the ONLY channel into the main project, so
malformed authority must FAIL CLOSED, never be silently resolved by a
last-write-wins dict:

* duplicate field within one entry (status/producer/critical/freshness/...) ->
  structural error, not "the last one wins";
* duplicate entry_id across the file -> structural error, not "the first one";
* `critical` is exactly `true` | `false` -- `yes`, `TRUE`, `1`, junk are
  errors, never truthiness fallbacks;
* `status` recognition and the reviewed-flip share ONE regex, so a value
  recognized as `ready` can never fail to be replaced.

Collect refuses any package with a structural error -- zero writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ENTRY_HEADING_RE = re.compile(r"^##\s+([A-Z0-9]+-\d+):\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*\*\*([A-Za-z_]+):\*\*\s*(.*)$")

# The ONE status regex: recognition (parse) and replacement (reviewed-flip)
# use the exact same matcher, so a value parsed as `ready` is always
# replaceable. Allowed trailing whitespace, no leading/trailing junk.
STATUS_FIELD_RE = re.compile(r"^-\s*\*\*status:\*\*\s*([A-Za-z_-]+)\s*$")

CRITICAL_VALUES = frozenset({"true", "false"})


@dataclass
class OutboxEntry:
    """One `## ID: title` block. `critical` is a typed bool or None (absent);
    `errors` names every structural problem in the block."""

    entry_id: str
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    critical: bool | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def summary(self) -> str:
        return self.fields.get("summary", "")

    @property
    def severity(self) -> str:
        return self.fields.get("severity", "")

    @property
    def details(self) -> str:
        return self.fields.get("details", "").strip()

    @property
    def valid(self) -> bool:
        return not self.errors


def _parse_block(lines: list[str]) -> OutboxEntry | None:
    head = ENTRY_HEADING_RE.match(lines[0].strip())
    if not head:
        return None
    entry = OutboxEntry(head.group(1), head.group(2).strip())
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw in lines[1:]:
        line = raw.rstrip("\n").rstrip("\r")
        stripped = line.strip()
        field = FIELD_RE.match(stripped)
        if field:
            key = field.group(1).lower()
            if key in fields:
                entry.errors.append(f"duplicate field **{key}:**")
            fields[key] = field.group(2).strip()
            current_key = key
            continue
        if current_key is not None and stripped and not stripped.startswith("## "):
            # Multiline field continuation.
            fields[current_key] = (fields[current_key] + "\n" + line).rstrip()
            continue
        if stripped.startswith("## "):
            break
    entry.fields = fields

    if "status" in fields:
        status_line = next(
            (ln for ln in lines[1:] if STATUS_FIELD_RE.match(ln.strip())), None
        )
        if status_line is None:
            entry.errors.append(
                "status value must match `- **status:** <token>` exactly"
            )
    if "critical" in fields:
        value = fields["critical"].strip()
        if value not in CRITICAL_VALUES:
            entry.errors.append(
                f"critical must be exactly `true` or `false`, got {value!r}"
            )
        else:
            entry.critical = value == "true"
    return entry


def parse_outbox_strict(text: str) -> tuple[list[OutboxEntry], list[str]]:
    """Parse an OUTBOX document into entries + file-level structural errors.

    Every `## ID: title` block becomes one OutboxEntry; a duplicate entry_id is
    a file-level error and the duplicate block is dropped (never silently
    merged or first-wins). Callers MUST refuse a package with any error.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines(keepends=True):
        if ENTRY_HEADING_RE.match(line.strip()):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)

    entries: list[OutboxEntry] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for block in blocks:
        entry = _parse_block(block)
        if entry is None:
            errors.append(
                f"block starting {block[0].strip()[:40]!r} is not a legal "
                "`## ID: title` entry"
            )
            continue
        if entry.entry_id in seen_ids:
            errors.append(f"duplicate entry id {entry.entry_id}")
            continue
        seen_ids.add(entry.entry_id)
        entries.append(entry)
    return entries, errors


def status_ready(entry: OutboxEntry) -> bool:
    """Exact `ready` (the one token collect may consume)."""
    m = STATUS_FIELD_RE.match(f"- **status:** {entry.fields.get('status', '')}")
    return bool(m) and m.group(1) == "ready"


def reviewed_transform(outbox_text: str, entry_id: str) -> str | None:
    """Flip the ONE named entry's `status: ready` to `reviewed`.

    Uses the SAME status regex as parsing, replaces EXACTLY the matched span
    (so extra spaces/tabs around the token cannot defeat the flip), counts
    exactly one replacement, and returns None unless the result re-parses
    with that entry `reviewed`. Callers abort the whole collect when None.
    """
    lines = outbox_text.splitlines(keepends=True)
    in_block = False
    replaced = 0
    for i, line in enumerate(lines):
        head = ENTRY_HEADING_RE.match(line.strip())
        if head:
            in_block = head.group(1) == entry_id
            continue
        if not in_block:
            continue
        m = STATUS_FIELD_RE.match(line.strip())
        if m and m.group(1) == "ready":
            # Replace the exact matched span of the ORIGINAL line (whitespace
            # tolerance: the regex already matched it).
            raw = lines[i]
            head_off = raw.index(raw.lstrip())
            span = m.span(1)
            start = head_off + span[0]
            end = head_off + span[1]
            lines[i] = raw[:start] + "reviewed" + raw[end:]
            replaced += 1
    if replaced != 1:
        return None
    new_text = "".join(lines)
    entries, errors = parse_outbox_strict(new_text)
    target = next((e for e in entries if e.entry_id == entry_id), None)
    if errors or target is None or target.status != "reviewed":
        return None
    return new_text


def field_by_name(entry: OutboxEntry, name: str) -> str:
    return entry.fields.get(name, "")
