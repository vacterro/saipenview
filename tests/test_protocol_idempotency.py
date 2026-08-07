"""T-191: idempotency + grammar safety of the protocol mutations.

record_manual_work must be recoverable (LOG-first, resume on retry) and must
escape the closed BOARD/LOG field grammar. collect_outbox_entry must be
idempotent per stable identity `(sub_name, entry_id)`: re-running after any
partial step resumes, never duplicates, and external sub content cannot break
BOARD grammar or bypass the freshness gate.
"""

from __future__ import annotations

import re

import pytest

from saipenview.parser import (
    collect_outbox_entry,
    parse_board,
    record_manual_work,
)
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## DOING\n- [/] T-001 in flight\n## TODO\n- [ ] T-002 open\n## DONE\n- [x] T-003 done\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


def _sub_outbox(root, entries: str, sub="saiwiki"):
    outbox = root / ".saipen" / "extensions" / "subs" / sub / "kitchen"
    outbox.mkdir(parents=True)
    (outbox / "OUTBOX.md").write_text(entries, encoding="utf-8")
    return outbox


READY_CRITICAL = """## WIKI-1: doc fix

- **status:** ready
- **critical:** true
- **summary:** fix the docs
"""

READY_MINOR = """## WIKI-2: minor

- **status:** ready
- **critical:** false
- **summary:** tidy a paragraph
"""


# --- record_manual_work: grammar -----------------------------------------


def test_record_escapes_pipes_in_description(project):
    res = record_manual_work(project, "add | owner: evil")
    assert res["ok"] is True
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "- [ ] T-004 Manual: add \\| owner: evil | owner: user" in board
    parsed = parse_board(board)
    desc = next(t.description for t in parsed.todo if t.ticket_id == "T-004")
    assert "add \\| owner: evil" in desc
    # No second `| field:` pair was forged from the description.
    assert "| critical:" not in board


def test_record_escapes_field_looking_text(project):
    record_manual_work(project, "note | critical: true | blocker: x")
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "\\| critical: true" in board
    assert "\\| blocker: x" in board
    assert board.count("| owner: user") == 1


# --- record_manual_work: idempotent resume -------------------------------


def test_record_resumes_a_log_only_partial_state(project):
    # A prior attempt wrote the LOG line but crashed before the BOARD insert.
    log = project / ".saipen" / "LOG.md"
    log.write_text(
        read_doc(log)
        + "- 07.08.26 12:00 [E-2] [T-004] RUN: manual work recorded -- half done\n",
        encoding="utf-8",
    )
    res = record_manual_work(project, "half done")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-004"
    assert res["event"] == "E-2"
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "- [ ] T-004 Manual: half done | owner: user" in board
    # Exactly one E-2, exactly one T-004 -- no duplicate record.
    assert read_doc(log).count("[E-2]") == 1
    assert board.count("T-004") == 1


def test_record_returns_already_when_fully_recorded(project):
    first = record_manual_work(project, "twice")
    second = record_manual_work(project, "twice")
    assert second["already"] is True
    assert second["ticket_id"] == first["ticket_id"]
    assert second["event"] == first["event"]
    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert board.count(first["ticket_id"]) == 1
    assert log.count(f"[{first['event']}]") == 1


# --- collect_outbox_entry: idempotency -----------------------------------


def test_collect_critical_is_idempotent(project):
    _sub_outbox(project, READY_CRITICAL)
    first = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert first["ok"] is True
    assert first["ticket_id"] == "T-004"

    second = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert second["ok"] is True
    assert second.get("already") is True  # reviewed -> deterministic no-op

    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert board.count("T-004") == 1, "collect duplicated the ticket"
    assert board.count("[from saiwiki WIKI-1]") == 1
    assert len(re.findall(r"\[E-(\d+)\]", log)) == len(
        set(re.findall(r"\[E-(\d+)\]", log))
    )
    outbox = read_doc(
        project
        / ".saipen"
        / "extensions"
        / "subs"
        / "saiwiki"
        / "kitchen"
        / "OUTBOX.md"
    )
    assert "- **status:** reviewed" in outbox


def test_collect_noncritical_is_idempotent(project):
    _sub_outbox(project, READY_MINOR)
    first = collect_outbox_entry(project, "saiwiki", "WIKI-2")
    assert first["ok"] is True
    second = collect_outbox_entry(project, "saiwiki", "WIKI-2")
    assert second["ok"] is True
    assert second.get("already") is True

    inbox = read_doc(
        project / ".saipen" / "extensions" / "subs" / "_shared" / "inbox.md"
    )
    assert inbox.count("WIKI-2") == 1, "non-critical collect duplicated the inbox line"


def test_collect_already_reviewed_is_a_noop(project):
    _sub_outbox(project, READY_CRITICAL.replace("ready", "reviewed"))
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    assert res.get("already") is True
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "T-004" not in board


def test_collect_resumes_when_board_written_but_outbox_still_ready(project):
    # Crash between the BOARD write and the OUTBOX reviewed-mark: the entry is
    # still `ready`, but the ticket already exists. Retry must NOT duplicate.
    _sub_outbox(project, READY_CRITICAL)
    board = project / ".saipen" / "BOARD.md"
    board.write_text(
        read_doc(board).replace(
            "## TODO\n",
            "## TODO\n- [ ] T-004 [from saiwiki WIKI-1] fix the docs\n",
            1,
        ),
        encoding="utf-8",
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-004"
    board_text = read_doc(board)
    assert board_text.count("T-004") == 1, "retry duplicated the ticket"
    outbox = read_doc(
        project
        / ".saipen"
        / "extensions"
        / "subs"
        / "saiwiki"
        / "kitchen"
        / "OUTBOX.md"
    )
    assert "- **status:** reviewed" in outbox


def test_collect_stale_source_head_is_refused(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    for c in (
        ["init", "-q"],
        ["config", "user.email", "t@t.t"],
        ["config", "user.name", "t"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", "-C", str(root), *c], capture_output=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "a.txt"], capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "init"], capture_output=True
    )
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    _sub_outbox(root, READY_CRITICAL + "- **source_head:** deadbeef\n")

    res = collect_outbox_entry(root, "saiwiki", "WIKI-1")
    assert res["ok"] is False
    assert "stale" in res["message"]
    board = read_doc(root / ".saipen" / "BOARD.md")
    assert "T-004" not in board
    outbox = read_doc(
        root / ".saipen" / "extensions" / "subs" / "saiwiki" / "kitchen" / "OUTBOX.md"
    )
    assert "- **status:** ready" in outbox  # not reviewed


def test_collect_escapes_external_sub_content(project):
    _sub_outbox(
        project,
        READY_CRITICAL.replace("fix the docs", "fix | critical: true docs"),
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "\\| critical: true" in board
    assert "| critical: true" not in board.replace("\\|", "escaped")
