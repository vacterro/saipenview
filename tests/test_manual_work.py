"""T-127: recording a user's manual edit as a board entry.

The watcher cannot attribute a file change to a person, so SAIPENVIEW never
tries: the UI asks, the user confirms, and record_manual_work() writes the
explicit record -- one board ticket (attributable to the user), one LOG
evidence line, and best-effort git context.
"""

from __future__ import annotations

import re

import pytest

from saipenview.parser import parse_board, record_manual_work
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


def test_record_creates_a_todo_ticket_attributed_to_the_user(project):
    res = record_manual_work(project, "edited STATE.md by hand")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-004"
    text = read_doc(project / ".saipen" / "BOARD.md")
    todo = text.split("## TODO")[1].split("## DONE")[0]
    assert "- [ ] T-004 Manual: edited STATE.md by hand | owner: user" in todo
    assert "T-004" not in text.split("## DOING")[1].split("## TODO")[0]


def test_record_appends_a_valid_log_evidence_line(project):
    res = record_manual_work(project, "committed a fix")
    assert res["event"] == "E-2"
    log = read_doc(project / ".saipen" / "LOG.md")
    assert re.search(
        r"^- \d{2}\.\d{2}\.\d{2} \d{2}:\d{2} \[E-2\] \[T-004\] RUN: manual work recorded -- committed a fix",
        log,
        flags=re.MULTILINE,
    ), log
    assert "[E-1]" in log


def test_record_takes_the_next_ticket_and_event_numbers(project):
    record_manual_work(project, "first")
    record_manual_work(project, "second")
    text = read_doc(project / ".saipen" / "BOARD.md")
    ids = sorted(int(m) for m in re.findall(r"\bT-(\d+)\b", text))
    assert ids[-1] == 5
    log = read_doc(project / ".saipen" / "LOG.md")
    events = sorted(int(m) for m in re.findall(r"\[E-(\d+)\]", log))
    assert events[-1] == 3


def test_record_rejects_empty_description(project):
    res = record_manual_work(project, "   ")
    assert res["ok"] is False
    assert "empty" in res["error"]


def test_record_with_git_context_links_head_and_dirty_count(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for c in (
        ["init", "-q"],
        ["config", "user.email", "t@t.t"],
        ["config", "user.name", "t"],
        ["config", "commit.gpgsign", "false"],
    ):
        import subprocess

        subprocess.run(["git", "-C", str(root), *c], capture_output=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "a.txt"], capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", "init"], capture_output=True
    )
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    (root / ".saipen").mkdir()
    (root / ".saipen" / "BOARD.md").write_text(
        "# BOARD\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (root / ".saipen" / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")

    res = record_manual_work(root, "manual test edit")
    assert res["ok"] is True
    log = read_doc(root / ".saipen" / "LOG.md")
    assert "at " in log and "dirty files" in log


def test_record_then_board_is_valid(project):
    record_manual_work(project, "manual pass")
    board = parse_board(read_doc(project / ".saipen" / "BOARD.md"))
    assert any(
        t.ticket_id == "T-004" and t.description.startswith("Manual:")
        for t in board.todo
    )
