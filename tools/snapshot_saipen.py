"""Mechanically (re)generate the tracked own-`.saipen` CI snapshot.

SAIPENVIEW's real `.saipen/` is gitignored and exists only on machines where
the app runs, so CI cannot validate it -- and the workflow must not pretend it
does. This tool produces a tracked, sanitized snapshot of the memory's SHAPE:

* STATE.md -- the live state's canonical field set and values, with the
  volatile surfaces scrubbed (agent identity, saipen_home path, updated stamp,
  last_event) so the output is stable across sessions;
* BOARD.md -- the live board verbatim (structural, not volatile);
* LOG.md -- a fixed conformant reference log (the live log is append-only
  volatile by design).

Run `python tools/snapshot_saipen.py --write` after the memory SHAPE changes
(a new required STATE field, a new phase). The default dry run compares the
tracked snapshot against the live memory and reports drift -- the local
pre-ship gate. CI validates the TRACKED snapshot via tests/
test_conformance_legacy.py::test_own_saipen_snapshot_is_conformant; the live
memory is validated locally by test_own_saipen_memory_is_conformant.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKED = ROOT / "tests" / "fixtures" / "own_saipen_snapshot" / ".saipen"
LIVE = ROOT / ".saipen"

_FIXED_UPDATED = "2026-08-01T00:00:00Z"
_REFERENCE_LOG = (
    "- 07.08.26 00:00 [E-1] RUN: boot\n"
    "- 07.08.26 00:01 [E-2] [parent: E-1] RUN: validate.py -> PASS\n"
)

# STATE fields carried into the snapshot. Anything else (saipen_home, agent
# identity, updated, last_event, goal counters, human_note, converges) is
# volatile per-session or per-machine and is scrubbed to a stable form.
_KEPT_STATE_FIELDS = (
    "schema_version",
    "phase",
    "transition_from",
    "task",
    "next_action",
    "blocker",
    "mode",
    "saipen_version",
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("---") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip("\"'")
    return out


def generate(live: Path, tracked: Path) -> dict[str, str]:
    """Produce the sanitized STATE/BOARD/LOG for *live* into *tracked*.
    Returns {relative: text}."""
    state = _parse_frontmatter((live / "STATE.md").read_text(encoding="utf-8-sig"))
    lines = ["---"]
    for key in _KEPT_STATE_FIELDS:
        if key in state:
            value = state[key]
            if key == "next_action" and re.search(r"\bT-\d+\b", value):
                # A ticket-naming next_action is session routing (the live
                # Pick Rule's choice for THIS agent); the snapshot's fixed
                # `agent: snapshot` cannot own a live ticket claim, so the
                # shape keeps the generic continuation instead of a stale
                # ticket ref that would fail the cross-agent claim check.
                value = "saipen continue"
            if " " in value or value == "":
                value = f'"{value}"'
            lines.append(f"{key}: {value}")
    lines.append("agent: snapshot")
    lines.append("saipen_home: snapshot")
    # execution_intent is per-session volatile (normal/goal/converge), like
    # agent/updated/last_event -- the snapshot carries the stable shape, not a
    # transient intent that would flip the fixture every convergence run.
    lines.append("execution_intent: normal")
    lines.append(f"updated: {_FIXED_UPDATED}")
    lines.append("last_event: 2")
    lines.append("style_contract: ded-4ae736e4")
    lines.append("---")
    state_text = "\n".join(lines) + "\n"

    board = (live / "BOARD.md").read_text(encoding="utf-8-sig")

    # A claimed ## DOING ticket carries live session data (owner identity,
    # claim_time) -- the same volatile class as STATE's agent/updated. Scrub
    # it to the snapshot's stable owner so the claimed ticket stays
    # conformant: STATE's next_action names a ticket its own agent owns.
    # Historical owner/claim_time on ## DONE / ## TODO tickets stay verbatim.
    def _scrub_claim(heading: str, body: str) -> str:
        if heading != "## DOING":
            return body
        body = re.sub(r"(\| owner: )\S+", r"\1snapshot", body)
        body = re.sub(r"(\| claim_time: )\S+", r"\g<1>" + _FIXED_UPDATED, body)
        return body

    # Split into sections; scrub only the claimed ## DOING body. Historical
    # owner/claim_time on ## DONE / ## TODO tickets stay verbatim.
    _section_re = re.compile(r"(?m)^(## (?:DOING|TODO|DONE|BLOCKED))$")
    parts = _section_re.split(board)
    for i in range(1, len(parts), 2):
        parts[i + 1] = _scrub_claim(parts[i].strip(), parts[i + 1])
    board = "".join(parts)
    # The live board may carry trailing blank lines (scratch space). Strip
    # them -- `git diff --check` treats a blank line at EOF as an error, and
    # the snapshot is a tracked commit artifact, not a scratch pad.
    board = board.rstrip() + "\n"
    log = _REFERENCE_LOG
    return {
        "STATE.md": state_text,
        "BOARD.md": board,
        "LOG.md": log,
    }


def _emit(tracked: Path, texts: dict[str, str]) -> None:
    tracked.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (tracked / name).write_text(text, encoding="utf-8")


def _diff(live: Path, tracked: Path) -> list[str]:
    if not (live / "STATE.md").is_file():
        return ["live .saipen/STATE.md absent -- nothing to compare"]
    if not (tracked / "STATE.md").is_file():
        return ["tracked snapshot absent -- run --write"]
    generated = generate(live, tracked)
    diffs = []
    for name, text in generated.items():
        current = (tracked / name).read_text(encoding="utf-8-sig")
        if current != text:
            diffs.append(f"{name}: tracked snapshot differs from live memory shape")
    return diffs


def main() -> int:
    argv = sys.argv[1:]
    write = "--write" in argv
    if any(a not in ("--write",) for a in argv):
        print(f"usage: {sys.argv[0]} [--write]")
        return 2
    if not (LIVE / "STATE.md").is_file():
        print("live .saipen/STATE.md absent -- nothing to snapshot")
        return 2
    if write:
        _emit(TRACKED, generate(LIVE, TRACKED))
        print(f"snapshot written to {TRACKED}")
        return 0
    diffs = _diff(LIVE, TRACKED)
    if diffs:
        print("snapshot drift:")
        for d in diffs:
            print(f"  - {d}")
        print("regenerate with --write after the memory shape change")
        return 1
    print("tracked snapshot matches the live memory shape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
