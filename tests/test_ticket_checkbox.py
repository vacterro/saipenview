"""T-174 + P0: ticket lifecycle is delegated to the canonical SAIOPS engine.

The viewer is a CLIENT of one lifecycle authority, never a second state
machine:

  start  -> canonical claim (writes owner/claim_time + transitions STATE)
  done   -> canonical finish_ticket (ONLY from phase SHIP; the viewer cannot
            manufacture DONE any other way)
  block  -> canonical ticket_move block (reason REQUIRED)
  unblock-> canonical ticket_move unblock (decision REQUIRED)
  reopen -> journaled board-only move (no canonical op exists; a finished
            ticket is never STATE.task, so board-only cannot split STATE/BOARD)

Everything else is refused by the canonical engine with zero writes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import make_conformant_project

from saipenview.parser import move_ticket, parse_board, ticket_transition_error
from saipenview.textio import read_doc


def _board(root: Path) -> str:
    return read_doc(root / ".saipen" / "BOARD.md")


def _state(root: Path) -> str:
    return read_doc(root / ".saipen" / "STATE.md")


BOARD_TODO = (
    "# BOARD\n## DOING\n\n## TODO\n"
    "- [ ] T-001 open ticket\n- [ ] T-003 another\n"
    "## DONE\n- [x] T-004 finished | verify: it shipped\n"
    "## BLOCKED\n- [ ] T-005 stuck | blocker: external dep\n"
)


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(tmp_path, board_text=BOARD_TODO)


class TestStartDelegatesToCanonicalClaim:
    def test_start_claims_ticket(self, project):
        res = move_ticket(project, "T-001", "start")
        assert res["ok"] is True, res
        assert res["code"] == "CLAIMED", res
        text = _board(project)
        doing = text.split("## DOING")[1].split("## TODO")[0]
        assert "T-001" in doing
        assert "[/] T-001 open ticket | owner: testseat" in doing
        # The canonical claim transitions STATE to SCOUT with task T-001.
        state = _state(project)
        assert re.search(r"phase:\s*SCOUT", state), state
        assert re.search(r"task:\s*T-001", state), state

    def test_start_refuses_when_another_doing_exists(self, tmp_path):
        root = make_conformant_project(
            tmp_path,
            board_text="# BOARD\n## DOING\n- [/] T-099 busy\n"
            "## TODO\n- [ ] T-001 open\n## DONE\n## BLOCKED\n",
        )
        res = move_ticket(root, "T-001", "start")
        assert res["ok"] is False
        assert res["code"] == "ALREADY_CLAIMED", res


class TestDoneIsCanonicalFinish:
    def test_done_refuses_outside_ship(self, tmp_path):
        # The canonical gate: finish requires phase SHIP + task match + one
        # DOING. A DONE click on a non-SHIP ticket refuses ILLEGAL_PHASE with
        # zero writes -- the viewer cannot manufacture DONE.
        root = make_conformant_project(
            tmp_path,
            phase="BUILD",
            task="T-001",
            next_action="PHASE BUILD T-001",
            board_text="# BOARD\n## DOING\n- [/] T-001 in flight | owner: testseat | claim_time: 2026-08-23T00:00:00Z\n"
            "## TODO\n## DONE\n## BLOCKED\n",
        )
        res = move_ticket(root, "T-001", "done")
        assert res["ok"] is False
        assert res["code"] == "ILLEGAL_PHASE", res
        assert "T-001" not in _board(root).split("## DONE")[1]

    def test_done_from_ship_closes_atomically(self, tmp_path):
        # The one legal path: ticket at SHIP, task matches, exactly one DOING.
        root = make_conformant_project(
            tmp_path,
            phase="SHIP",
            task="T-001",
            next_action="PHASE SHIP T-001",
            board_text="# BOARD\n## DOING\n- [/] T-001 done work | owner: testseat | claim_time: 2026-08-23T00:00:00Z | verify: PASS -- ship-gate evidence\n"
            "## TODO\n## DONE\n## BLOCKED\n",
        )
        # Canonical finish needs a current-cycle VERIFY boundary + PASS conf: high.
        log = root / ".saipen" / "LOG.md"
        log.write_text(
            "- 11.08.26 00:00 [E-1] RUN: boot\n"
            "- 11.08.26 00:01 [E-2] [parent: E-1] RUN: validate.py -> PASS\n"
            "- 11.08.26 00:02 [E-3] [parent: E-2] [T-001] RUN: transition to VERIFY\n"
            "- 11.08.26 00:03 [E-4] [parent: E-3] [T-001] RUN: PASS conf: high -- suite green\n",
            encoding="utf-8",
        )
        state = root / ".saipen" / "STATE.md"
        state.write_text(
            state.read_text(encoding="utf-8").replace("last_event: 2", "last_event: 4"),
            encoding="utf-8",
        )
        res = move_ticket(root, "T-001", "done")
        assert res["ok"] is True, res
        assert res["code"] == "FINISHED", res
        assert "- [x] T-001" in _board(root).split("## DONE")[1]
        state = _state(root)
        assert re.search(r"phase:\s*DONE", state), state
        assert re.search(r"task:\s*none", state), state


class TestBlockUnblockDelegates:
    def test_block_moves_todo_to_blocked_with_reason(self, project):
        res = move_ticket(project, "T-001", "block", "waiting on upstream")
        assert res["ok"] is True, res
        assert res["code"] == "BLOCK", res
        blocked = _board(project).split("## BLOCKED")[1].split("## ")[0]
        assert "T-001" in blocked
        assert "blocker: waiting on upstream" in blocked
        assert "- [ ] T-001 open ticket | blocker: waiting on upstream" in blocked

    def test_block_without_reason_is_rejected(self, project):
        res = move_ticket(project, "T-001", "block", None)
        assert res["ok"] is False
        assert res["code"] == "VALIDATION_FAILED", res
        assert "T-001" in _board(project).split("## TODO")[1]

    def test_block_escapes_literal_pipe_in_reason(self, project):
        assert move_ticket(project, "T-001", "block", "needs | review")["ok"] is True
        blocked = _board(project).split("## BLOCKED")[1].split("## ")[0]
        assert "needs \\| review" in blocked

    def test_unblock_moves_blocked_to_todo(self, project):
        res = move_ticket(project, "T-005", "unblock", "dep released")
        assert res["ok"] is True, res
        assert res["code"] == "UNBLOCK", res
        todo = _board(project).split("## TODO")[1]
        assert "T-005" in todo
        assert "T-005" not in _board(project).split("## BLOCKED")[1].split("## ")[0]

    def test_unblock_requires_a_lifting_decision(self, project):
        res = move_ticket(project, "T-005", "unblock", None)
        assert res["ok"] is False
        assert res["code"] == "VALIDATION_FAILED", res

    def test_unblock_removes_the_blocker_field(self, project):
        assert move_ticket(project, "T-005", "unblock", "dep released")["ok"] is True
        todo = _board(project).split("## TODO")[1]
        assert "blocker:" not in todo
        # Blocking again creates exactly one fresh blocker field, not two.
        assert move_ticket(project, "T-005", "block", "re-stuck")["ok"] is True
        blocked = _board(project).split("## BLOCKED")[1].split("## ")[0]
        assert blocked.count("blocker:") == 1
        assert "blocker: re-stuck" in blocked


class TestReopenJournaledBoardOnly:
    def test_reopen_moves_done_to_todo(self, project):
        res = move_ticket(project, "T-004", "reopen")
        assert res["ok"] is True, res
        todo = _board(project).split("## TODO")[1]
        assert "T-004" in todo
        assert "T-004" not in _board(project).split("## DONE")[1]

    def test_reopen_from_non_done_is_rejected(self, project):
        res = move_ticket(project, "T-001", "reopen")
        assert res["ok"] is False
        assert res["code"] == "ILLEGAL_TICKET_LIFECYCLE", res
        assert "T-001" in _board(project).split("## TODO")[1]


class TestIllegalTransitions:
    def test_wrong_origin_actions_write_nothing(self, project):
        before = _board(project)
        # T-005 (BLOCKED): no start/done/block/reopen. T-004 (DONE): no
        # start/block/unblock. Every attempt must be refused with zero writes.
        move_ticket(project, "T-005", "start")
        move_ticket(project, "T-005", "done")
        move_ticket(project, "T-005", "block", "x")
        move_ticket(project, "T-005", "reopen")
        move_ticket(project, "T-004", "start")
        move_ticket(project, "T-004", "block", "x")
        move_ticket(project, "T-004", "unblock", "x")
        move_ticket(project, "T-001", "done")
        assert _board(project) == before

    def test_unknown_action_rejected(self, project):
        res = move_ticket(project, "T-001", "explode")
        assert res["ok"] is False


class TestBlockerParsing:
    def test_parse_board_extracts_blocker(self, project):
        board = parse_board(_board(project))
        blocked = {t.ticket_id: t for t in board.blocked}
        assert blocked["T-005"].blocker == "external dep"
        assert blocked["T-005"].description == "stuck"
        assert all(t.blocker == "" for t in board.todo)


class TestTransitionErrorIsCanonical:
    def test_error_text_comes_from_canonical_plans(self, project):
        err = ticket_transition_error(project, "T-001", "done")
        assert err and "DOING" in err
        err_block = ticket_transition_error(project, "T-001", "block", None)
        assert err_block and "reason" in err_block
        assert ticket_transition_error(project, "T-001", "start") is None
