"""T-174 + the strict state machine: real-time ticket checkboxes -- backend.

move_ticket() is CORE § 1.2's strict state machine. The SECTION is the status,
never the checkbox, and each action accepts exactly its source sections:

  TODO -> start -> DOING
  DOING -> done -> DONE     (only with a non-empty | verify: clause, and only
                             when the ticket is not the active STATE task)
  DONE -> reopen -> TODO
  TODO/DOING -> block -> BLOCKED   (reason REQUIRED; DOING block is refused
                                    board-only -- it needs SAIOPS park semantics)
  BLOCKED -> unblock -> TODO       (lifting decision REQUIRED, blocker removed)

Everything else is rejected with zero writes. parse_board() surfaces the
blocker reason so a BLOCKED row can say WHY it is blocked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from saipenview.parser import (
    move_ticket,
    parse_board,
    reorder_ticket,
    ticket_transition_error,
)
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
        "- [/] T-002 doing ticket | verify: it runs\n"
        "## TODO\n"
        "- [ ] T-001 open ticket\n"
        "- [ ] T-003 another\n"
        "## DONE\n"
        "- [x] T-004 finished | verify: it shipped\n"
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
        assert "- [x] T-002 doing ticket | verify: it runs" in text
        assert "T-002" in text.split("## DONE")[1]

    def test_reopen_moves_done_to_todo(self, project):
        assert move_ticket(project, "T-004", "reopen")
        text = _board(project)
        assert "- [ ] T-004 finished | verify: it shipped" in text
        assert "T-004" in text.split("## TODO")[1]


class TestIllegalTransitions:
    """Every wrong-origin action is rejected with zero writes (the strict
    machine the old code deliberately skipped)."""

    def test_start_on_doing(self, project):
        assert move_ticket(project, "T-002", "start") is False
        assert "- [/] T-002" in _board(project)

    def test_start_on_done(self, project):
        assert move_ticket(project, "T-004", "start") is False
        assert "T-004" in _board(project).split("## DONE")[1]

    def test_start_on_blocked(self, project):
        assert move_ticket(project, "T-005", "start") is False

    def test_done_on_todo(self, project):
        assert move_ticket(project, "T-001", "done") is False
        assert "T-001" in _board(project).split("## TODO")[1]

    def test_done_on_done(self, project):
        assert move_ticket(project, "T-004", "done") is False

    def test_done_on_blocked(self, project):
        assert move_ticket(project, "T-005", "done") is False

    def test_reopen_on_todo(self, project):
        assert move_ticket(project, "T-001", "reopen") is False

    def test_reopen_on_doing(self, project):
        assert move_ticket(project, "T-002", "reopen") is False

    def test_reopen_on_blocked(self, project):
        assert move_ticket(project, "T-005", "reopen") is False

    def test_block_on_done(self, project):
        assert move_ticket(project, "T-004", "block", "why") is False
        assert "T-004" in _board(project).split("## DONE")[1]

    def test_block_on_blocked(self, project):
        assert move_ticket(project, "T-005", "block", "again") is False
        assert _board(project).count("T-005") == 1

    def test_unblock_on_todo(self, project):
        assert move_ticket(project, "T-001", "unblock", "decision") is False

    def test_unblock_on_doing(self, project):
        assert move_ticket(project, "T-002", "unblock", "decision") is False

    def test_unblock_on_done(self, project):
        assert move_ticket(project, "T-004", "unblock", "decision") is False

    def test_illegal_transition_writes_nothing(self, project):
        before = _board(project)
        # Only wrong-origin actions: T-004 (DONE) has no done/start/block/
        # unblock; T-005 (BLOCKED) has no done/start/reopen/block and unblock
        # without a decision is refused too. Zero writes on every attempt.
        for action in ("done", "start", "block"):
            move_ticket(project, "T-004", action, "reason")
        move_ticket(project, "T-004", "unblock", "reason")
        for action in ("done", "start", "reopen", "block"):
            move_ticket(project, "T-005", action, "reason")
        move_ticket(project, "T-005", "unblock", None)
        assert _board(project) == before

    def test_unknown_action_rejected(self, project):
        assert move_ticket(project, "T-001", "explode") is False


class TestBlockUnblock:
    def test_block_moves_todo_to_blocked_with_reason(self, project):
        assert move_ticket(project, "T-001", "block", "waiting on upstream")
        text = _board(project)
        blocked_section = text.split("## BLOCKED")[1].split("## ")[0]
        assert "T-001" in blocked_section
        assert "blocker: waiting on upstream" in blocked_section
        assert "- [ ] T-001 open ticket | blocker: waiting on upstream" in text

    def test_block_without_reason_is_rejected(self, project):
        # CORE § 1.2: a block with no stated facts/dead-ends is not a block.
        assert move_ticket(project, "T-001", "block", None) is False
        assert "T-001" in _board(project).split("## TODO")[1]
        assert move_ticket(project, "T-001", "block", "  ") is False

    def test_block_escapes_literal_pipe_in_reason(self, project):
        assert move_ticket(project, "T-001", "block", "needs | review")
        text = _board(project)
        assert "needs \\| review" in text
        assert "T-001" in text.split("## BLOCKED")[1].split("## ")[0]

    def test_block_collapses_newlines_in_reason(self, project):
        # A reason is ONE ticket field on ONE line; embedded newlines would
        # split the line and forge a bogus second line.
        assert move_ticket(project, "T-001", "block", "line one\nline two")
        text = _board(project)
        blocked_section = text.split("## BLOCKED")[1].split("## ")[0]
        assert "line one line two" in blocked_section
        assert "\n" not in blocked_section.strip().splitlines()[-1]

    def test_block_replaces_an_existing_blocker_field(self, project):
        # "Create exactly one blocker field": a stale blocker on the line is
        # replaced, never doubled.
        saipen = project / ".saipen"
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## TODO\n- [ ] T-001 open | blocker: stale\n"
            "## DOING\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        assert move_ticket(project, "T-001", "block", "fresh reason")
        blocked = _board(project).split("## BLOCKED")[1].split("## ")[0]
        assert blocked.count("blocker:") == 1
        assert "blocker: fresh reason" in blocked

    def test_unblock_moves_blocked_to_todo(self, project):
        assert move_ticket(project, "T-005", "unblock", "dep released")
        text = _board(project)
        todo_section = text.split("## TODO")[1]
        assert "T-005" in todo_section
        assert "T-005" not in text.split("## BLOCKED")[1].split("## ")[0]

    def test_unblock_requires_a_lifting_decision(self, project):
        # CORE § 1.2: an unblock without the decision that lifts the block is
        # the same shape as a block without a reason -- no transition.
        assert move_ticket(project, "T-005", "unblock", None) is False
        assert "T-005" in _board(project).split("## BLOCKED")[1].split("## ")[0]

    def test_unblock_removes_the_blocker_field(self, project):
        assert move_ticket(project, "T-005", "unblock", "dep released")
        todo = _board(project).split("## TODO")[1]
        assert "blocker:" not in todo
        # Blocking again must create exactly one fresh blocker field, not two.
        assert move_ticket(project, "T-005", "block", "re-stuck")
        blocked = _board(project).split("## BLOCKED")[1].split("## ")[0]
        assert blocked.count("blocker:") == 1
        assert "blocker: re-stuck" in blocked

    def test_done_without_verify_is_refused(self, project):
        # DOING -> DONE cannot fabricate a completion: no | verify: clause on
        # the ticket means no completion evidence.
        saipen = project / ".saipen"
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## DOING\n- [/] T-002 no proof yet\n"
            "## TODO\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        assert move_ticket(project, "T-002", "done") is False
        assert "T-002" in _board(project).split("## DOING")[1]
        assert ticket_transition_error(project, "T-002", "done")
        assert "verify" in ticket_transition_error(project, "T-002", "done")


class TestActiveTaskGates:
    def _active_project(self, tmp_path, phase="BUILD", task="T-002"):
        root = tmp_path / "proj"
        saipen = root / ".saipen"
        saipen.mkdir(parents=True)
        (saipen / "STATE.md").write_text(
            f"---\nphase: {phase}\ntask: {task}\n---\n", encoding="utf-8"
        )
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## DOING\n- [/] T-002 active | verify: runs\n"
            "## TODO\n- [ ] T-001 open\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        return root

    def test_done_on_active_task_is_refused(self, tmp_path):
        # Board-only done would split STATE (still naming T-002 in BUILD) from
        # BOARD (T-002 DONE) -- the exact T-573 corruption the validator now
        # rejects. Refuse and point at the atomic operation.
        root = self._active_project(tmp_path)
        assert move_ticket(root, "T-002", "done") is False
        err = ticket_transition_error(root, "T-002", "done")
        assert err and "saipen ticket done" in err
        assert "T-002" in _board(root).split("## DOING")[1]

    def test_done_on_inactive_doing_is_allowed(self, tmp_path):
        # STATE names a different task, so the ticket is a plain DOING claim
        # with verify evidence -- board-only done stays legal.
        root = self._active_project(tmp_path, phase="BUILD", task="T-001")
        assert move_ticket(root, "T-002", "done") is True
        assert "T-002" in _board(root).split("## DONE")[1]

    def test_block_on_active_doing_is_refused(self, tmp_path):
        # Blocking the active DOING ticket must park STATE (DONE/task none,
        # transition_from) -- SAIOPS park semantics a BOARD-only mover cannot
        # reproduce. Refuse board-only, point at the canonical operation.
        root = self._active_project(tmp_path)
        assert move_ticket(root, "T-002", "block", "parked") is False
        err = ticket_transition_error(root, "T-002", "block", "parked")
        assert err and "ticket block" in err
        assert "T-002" in _board(root).split("## DOING")[1]

    def test_block_on_inactive_doing_is_refused(self, tmp_path):
        # Canonical SAIOPS refuses block of a DOING ticket that is not the
        # active task; the viewer mirrors that instead of inventing a weaker
        # transition.
        root = self._active_project(tmp_path, phase="BUILD", task="T-001")
        assert move_ticket(root, "T-002", "block", "parked") is False


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


class TestReorder:
    def _todo_ids(self, project) -> list[str]:
        return [t.ticket_id for t in parse_board(_board(project)).todo]

    def test_move_to_front(self, project):
        assert reorder_ticket(project, "T-003", "TODO", before_ticket_id="T-001")
        assert self._todo_ids(project) == ["T-003", "T-001"]

    def test_move_to_end(self, project):
        assert reorder_ticket(project, "T-001", "TODO", before_ticket_id=None)
        assert self._todo_ids(project) == ["T-003", "T-001"]

    def test_move_down(self, project):
        assert reorder_ticket(project, "T-001", "TODO", before_ticket_id=None)
        assert self._todo_ids(project) == ["T-003", "T-001"]

    def test_cross_section_target_stays_in_own_section(self, project):
        reorder_ticket(project, "T-001", "TODO", before_ticket_id="T-004")
        assert "T-001" in _board(project).split("## TODO")[1].split("## DOING")[0]
        assert "T-001" not in _board(project).split("## DONE")[1].split("## BLOCKED")[0]
        assert "T-001" in self._todo_ids(project)

    def test_unknown_section_rejected(self, project):
        assert reorder_ticket(project, "T-001", "NOPE") is False

    def test_other_sections_untouched(self, project):
        reorder_ticket(project, "T-001", "TODO", before_ticket_id=None)
        text = _board(project)
        assert "- [/] T-002 doing ticket | verify: it runs" in text
        assert "- [x] T-004 finished | verify: it shipped" in text
        assert "- [ ] T-005 stuck | blocker: external dep" in text
