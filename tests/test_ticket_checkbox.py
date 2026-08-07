"""T-174: real-time ticket checkboxes -- the backend half.

move_ticket() gains `block` (TODO/DOING -> BLOCKED, appending `| blocker:`)
and `unblock` (BLOCKED -> TODO); parse_board() surfaces the blocker reason so
a BLOCKED row can say WHY it is blocked. Every move keeps the
checkbox-vs-section agreement (RFC 1.2): BLOCKED stays `[ ]`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from saipenview.parser import move_ticket, parse_board
from saipenview.textio import read_doc


def _board(root: Path) -> str:
    return read_doc(root / ".saipen" / "BOARD.md")


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "BOARD.md").write_text(
        "# BOARD\n"
        "## DOING\n"
        "- [/] T-002 doing ticket\n"
        "## TODO\n"
        "- [ ] T-001 open ticket\n"
        "- [ ] T-003 another\n"
        "## DONE\n"
        "- [x] T-004 finished\n"
        "## BLOCKED\n"
        "- [ ] T-005 stuck | blocker: external dep\n",
        encoding="utf-8",
    )
    return root


class TestCycle:
    def test_start_moves_todo_to_doing(self, project):
        assert move_ticket(project, "T-001", "start")
        text = _board(project)
        assert (
            "## DOING" in text
            and "T-001" in text.split("## DOING")[1].split("## TODO")[0]
        )
        assert "- [/] T-001 open ticket" in text

    def test_done_moves_doing_to_done(self, project):
        assert move_ticket(project, "T-002", "done")
        text = _board(project)
        assert "- [x] T-002 doing ticket" in text
        assert "T-002" in text.split("## DONE")[1]

    def test_reopen_moves_done_to_todo(self, project):
        assert move_ticket(project, "T-004", "reopen")
        text = _board(project)
        assert "- [ ] T-004 finished" in text
        assert "T-004" in text.split("## TODO")[1]


class TestBlockUnblock:
    def test_block_moves_todo_to_blocked_with_reason(self, project):
        assert move_ticket(project, "T-001", "block", "waiting on upstream")
        text = _board(project)
        blocked_section = text.split("## BLOCKED")[1].split("## ")[0]
        assert "T-001" in blocked_section
        assert "blocker: waiting on upstream" in blocked_section
        assert "- [ ] T-001 open ticket | blocker: waiting on upstream" in text

    def test_block_moves_doing_to_blocked_keeping_open_checkbox(self, project):
        assert move_ticket(project, "T-002", "block", "stuck on T-003")
        text = _board(project)
        assert "- [ ] T-002 doing ticket | blocker: stuck on T-003" in text
        # checkbox stays [ ] under BLOCKED -- RFC 1.2 checkbox/section agreement
        assert "[/] T-002" not in text

    def test_block_without_reason_still_moves(self, project):
        assert move_ticket(project, "T-001", "block", None)
        assert "T-001" in _board(project).split("## BLOCKED")[1].split("## ")[0]

    def test_unblock_moves_blocked_to_todo(self, project):
        assert move_ticket(project, "T-005", "unblock")
        text = _board(project)
        todo_section = text.split("## TODO")[1]
        assert "T-005" in todo_section
        assert "T-005" not in text.split("## BLOCKED")[1].split("## ")[0]

    def test_block_escapes_literal_pipe_in_reason(self, project):
        assert move_ticket(project, "T-001", "block", "needs | review")
        text = _board(project)
        assert "needs \\| review" in text
        assert "T-001" in text.split("## BLOCKED")[1].split("## ")[0]

    def test_unknown_action_rejected(self, project):
        assert move_ticket(project, "T-001", "explode") is False


class TestBlockerParsing:
    def test_parse_board_extracts_blocker(self, project):
        board = parse_board(_board(project))
        blocked = {t.ticket_id: t for t in board.blocked}
        assert blocked["T-005"].blocker == "external dep"
        assert blocked["T-005"].description == "stuck"
        assert all(t.blocker == "" for t in board.todo)

    def test_board_is_valid_after_all_moves(self, project):
        for tid, action, reason in [
            ("T-001", "start", None),
            ("T-002", "done", None),
            ("T-004", "reopen", None),
            ("T-003", "block", "hold"),
        ]:
            assert move_ticket(project, tid, action, reason)
        text = _board(project)
        # every `[` matches a legal section
        for section, ch in (
            ("DOING", "/"),
            ("DONE", "x"),
            ("TODO", " "),
            ("BLOCKED", " "),
        ):
            body = text.split(f"## {section}")[1].split("## ")[0]
            for line in body.splitlines():
                if re.match(r"^- \[", line.strip()):
                    assert line.strip().startswith(f"- [{ch}]"), (section, line.strip())
