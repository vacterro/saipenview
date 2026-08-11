"""T-127 + P1: recording a user's manual edit as a board entry.

The watcher cannot attribute a file change to a person, so SAIPENVIEW never
tries: the UI asks, the user confirms, and record_manual_work() writes the
explicit record -- one board ticket (attributable to the user), one LOG
evidence line, and best-effort git context, committed through the canonical
writer pipeline (journaled LOG+BOARD+STATE). Idempotency is by operation id,
never by human prose.
"""

from __future__ import annotations

import re

import pytest
from conftest import make_conformant_project

from saipenview.parser import parse_board, record_manual_work
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(tmp_path)


def test_record_creates_a_todo_ticket_attributed_to_the_user(project):
    res = record_manual_work(project, "edited STATE.md by hand")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-001"
    text = read_doc(project / ".saipen" / "BOARD.md")
    todo = text.split("## TODO")[1].split("## DOING")[0]
    assert "- [ ] T-001 Manual: edited STATE.md by hand | owner: user" in todo


def test_record_appends_a_valid_log_evidence_line(project):
    res = record_manual_work(project, "committed a fix")
    assert res["event"] == "E-3"
    log = read_doc(project / ".saipen" / "LOG.md")
    assert re.search(
        r"^- \d{2}\.\d{2}\.\d{2} \d{2}:\d{2} \[E-3\] \[T-001\] \[op: \S+\] "
        r"RUN: manual work recorded -- committed a fix",
        log,
        flags=re.MULTILINE,
    ), log
    assert "[E-1]" in log
    # STATE.last_event follows the LOG tail (canonical fast-check invariant).
    state = read_doc(project / ".saipen" / "STATE.md")
    assert re.search(r"last_event:\s*3", state), state


def test_record_takes_the_next_ticket_and_event_numbers(project):
    record_manual_work(project, "first")
    record_manual_work(project, "second")
    text = read_doc(project / ".saipen" / "BOARD.md")
    ids = sorted(int(m) for m in re.findall(r"\bT-(\d+)\b", text))
    assert ids[-1] == 2
    log = read_doc(project / ".saipen" / "LOG.md")
    events = sorted(int(m) for m in re.findall(r"\[E-(\d+)\]", log))
    assert events[-1] == 4


def test_record_rejects_empty_description(project):
    res = record_manual_work(project, "   ")
    assert res["ok"] is False
    assert "empty" in res["message"]


def test_record_with_git_context_links_head_and_dirty_count(tmp_path):
    import subprocess

    root = make_conformant_project(tmp_path)
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
    (root / "b.txt").write_text("b\n", encoding="utf-8")

    res = record_manual_work(root, "manual test edit")
    assert res["ok"] is True
    log = read_doc(root / ".saipen" / "LOG.md")
    assert "at " in log and "dirty files" in log


def test_record_then_board_is_valid(project):
    record_manual_work(project, "manual pass")
    board = parse_board(read_doc(project / ".saipen" / "BOARD.md"))
    assert any(
        t.ticket_id == "T-001" and t.description.startswith("Manual:")
        for t in board.todo
    )


# --- idempotency by OPERATION ID, never by human prose (repair mission P1) --


def test_same_description_with_same_op_id_is_one_record(project):
    op = "mw-test-op-1"
    first = record_manual_work(project, "updated docs", operation_id=op)
    second = record_manual_work(project, "updated docs", operation_id=op)
    assert second.get("code") == "ALREADY_RECORDED", second
    assert second["ticket_id"] == first["ticket_id"]
    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert board.count("T-001") == 1
    assert log.count("[E-3]") == 1


def test_same_description_with_different_op_id_is_two_records(project):
    record_manual_work(project, "updated docs", operation_id="mw-op-a")
    record_manual_work(project, "updated docs", operation_id="mw-op-b")
    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert board.count("Manual: updated docs") == 2
    assert log.count("manual work recorded -- updated docs") == 2
    assert log.count("[E-3]") == 1 and log.count("[E-4]") == 1


def test_retry_after_log_only_partial_resumes_original_ticket(project):
    # A crash after the LOG write leaves the line with the op marker; a retry
    # with the SAME op id resumes the original ticket instead of a new one.
    op = "mw-crash-1"
    log_path = project / ".saipen" / "LOG.md"
    log_path.write_text(
        read_doc(log_path)
        + f"- 11.08.26 12:00 [E-3] [T-001] [op: {op}] RUN: manual work "
        "recorded -- half done\n",
        encoding="utf-8",
    )
    state_path = project / ".saipen" / "STATE.md"
    state_path.write_text(
        re.sub(r"last_event:\s*\d+", "last_event: 3", read_doc(state_path)),
        encoding="utf-8",
    )
    res = record_manual_work(project, "half done", operation_id=op)
    assert res["ok"] is True
    assert res["ticket_id"] == "T-001"
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert board.count("T-001") == 1
    assert read_doc(log_path).count("[E-3]") == 1


def test_same_description_no_op_id_generates_two_records(project):
    # Backend-generated ids are distinct per call: without a stable operation
    # id there is nothing to resume, so the same prose twice is two actions.
    first = record_manual_work(project, "tuned knobs")
    second = record_manual_work(project, "tuned knobs")
    assert first["ticket_id"] == "T-001"
    assert second["ticket_id"] == "T-002"
