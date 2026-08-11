"""Single-writer ownership: app mutation vs agent launch, atomically decided.

The launch reservation and the app-protocol-transaction marker live in ONE
shared per-root lock (saipenview/ownership.py). These tests pin the mutual
exclusion from both directions and the cross-document conflict detection for
multi-file transactions.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.ownership import AgentOwnershipError
from saipenview.parser import collect_outbox_entry, record_manual_work
from saipenview.protocol_write import get_coordinator
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    (saipen / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\n---\n", encoding="utf-8"
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## DOING\n- [/] T-001 in flight\n## TODO\n- [ ] T-002 open\n"
        "## DONE\n- [x] T-003 done\n## BLOCKED\n",
        encoding="utf-8",
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def api(tmp_path) -> Api:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    with (
        patch("saipenview.api.config_path"),
        patch("saipenview.api.load_config", return_value=cfg),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        api = Api()
        try:
            yield api
        finally:
            api.stop()


class TestLaunchVsMutation:
    def test_launch_refused_while_app_transaction_active(self, project):
        coord = get_coordinator()
        with coord.locked(project):
            assert coord.ownership.begin_app_tx(project)
            # A launch reservation under the same per-root lock must refuse:
            # check and mark are one atomic decision, so no TOCTOU window.
            assert coord.ownership.reserve_agent(project) is False
            coord.ownership.end_app_tx(project)
        # After the transaction, the launch reservation succeeds.
        assert coord.ownership.reserve_agent(project) is True
        coord.ownership.release_agent(project)

    def test_mutation_refused_once_launch_reserved(self, project):
        coord = get_coordinator()
        assert coord.ownership.reserve_agent(project) is True
        board = project / ".saipen" / "BOARD.md"
        with pytest.raises(AgentOwnershipError):
            coord.mutate_doc(board, lambda t: t + "x")
        assert "T-999" not in read_doc(board)
        coord.ownership.release_agent(project)
        # Released -> the mutation goes through.
        coord.mutate_doc(board, lambda t: t + "- [ ] T-999 later\n")
        assert "T-999" in read_doc(board)

    def test_ui_mutation_refused_while_agent_runs(self, api, tmp_path):
        root = tmp_path / "proj"
        saipen = root / ".saipen"
        saipen.mkdir(parents=True)
        (saipen / "STATE.md").write_text(
            "---\nphase: BUILD\ntask: T-001\n---\n", encoding="utf-8"
        )
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## TODO\n- [ ] T-001 thing\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        (saipen / "LOG.md").write_text(
            "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
        )
        api._config["pinned_roots"] = [str(root)]
        # Reserve the agent ownership directly (simulates a live Core agent).
        coord = get_coordinator()
        assert coord.ownership.reserve_agent(root)
        try:
            res = api.record_manual_work(str(root), "while agent runs")
            assert res.get("ok") is False
            res2 = api.toggle_ticket_status(str(root), "T-001", "start")
            assert res2.get("ok") is False
            assert "T-002" not in read_doc(saipen / "BOARD.md")
        finally:
            coord.ownership.release_agent(root)

    def test_launch_reservation_while_ui_transaction_held(self, project):
        # The reverse TOCTOU: a mutation that passed its guard must not be
        # followed by a launch slipping in -- both serialize on the one lock.
        coord = get_coordinator()
        outcomes: list[str] = []
        barrier = threading.Barrier(2)

        def mutator():
            barrier.wait()
            with coord.locked(project):
                res = record_manual_work(project, "a")
                outcomes.append("mutation:" + str(res.get("ok")))

        def launcher():
            barrier.wait()
            # Between the mutation's guard and its write, a launch attempt
            # arrives; it must either wait (lock held) or refuse, and once the
            # mutation finishes the launch may reserve.
            ok = coord.ownership.reserve_agent(project)
            if ok:
                outcomes.append("launch:ok")
                coord.ownership.release_agent(project)
            else:
                outcomes.append("launch:refused")

        t1 = threading.Thread(target=mutator)
        t2 = threading.Thread(target=launcher)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert "mutation:True" in outcomes
        # The launch either refused while the mutation held the lock, or
        # reserved after it finished -- never "reserved mid-write".
        assert outcomes[-1] == "launch:ok"


class TestCrossDocumentConflict:
    def test_external_state_edit_during_board_log_transaction_aborts(self, project):
        # record_manual_work writes BOARD+LOG and depends on STATE; an external
        # STATE edit between its read and its commit must abort the whole
        # transaction, never compose two realities.
        state = project / ".saipen" / "STATE.md"
        real_read = __import__(
            "saipenview.protocol_write", fromlist=["read_doc_meta"]
        ).read_doc_meta
        injected = {"done": False}

        def sabotaging_read(path, *a, **k):
            if not injected["done"] and Path(path) == project / ".saipen" / "LOG.md":
                injected["done"] = True
                state.write_text(
                    "---\nphase: HUNT\ntask: external\n---\n", encoding="utf-8"
                )
            return real_read(path, *a, **k)

        with patch("saipenview.protocol_write.read_doc_meta", sabotaging_read):
            res = record_manual_work(project, "a")
        assert res.get("ok") is False
        assert "concurrently" in res.get("error", "")
        # Nothing was written: no ticket, no LOG line.
        board = read_doc(project / ".saipen" / "BOARD.md")
        log = read_doc(project / ".saipen" / "LOG.md")
        assert "T-004" not in board
        assert "[E-2]" not in log

    def test_external_board_edit_during_collect_aborts(self, tmp_path):
        from conftest import make_ready_outbox

        root = tmp_path / "proj"
        saipen = root / ".saipen"
        saipen.mkdir(parents=True)
        (saipen / "STATE.md").write_text(
            "---\nphase: DONE\ntask: none\n---\n", encoding="utf-8"
        )
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## TODO\n- [ ] T-001 existing\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        (saipen / "LOG.md").write_text(
            "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
        )
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")

        real_read = __import__(
            "saipenview.protocol_write", fromlist=["read_doc_meta"]
        ).read_doc_meta
        injected = {"done": False}
        board = saipen / "BOARD.md"

        def sabotaging_read(path, *a, **k):
            if not injected["done"] and Path(path) == board:
                injected["done"] = True
                board.write_text(
                    board.read_text(encoding="utf-8") + "- [ ] T-099 external\n",
                    encoding="utf-8",
                )
            return real_read(path, *a, **k)

        with patch("saipenview.protocol_write.read_doc_meta", sabotaging_read):
            res = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert res.get("ok") is False
        assert "concurrently" in res.get("message", "")
        outbox = saipen / "extensions" / "subs" / "saihunt" / "kitchen" / "OUTBOX.md"
        assert "reviewed" not in outbox.read_text(encoding="utf-8")
        log = read_doc(saipen / "LOG.md")
        assert "collect saihunt HUNT-001" not in log

    def test_two_simultaneous_collects_do_not_duplicate(self, tmp_path):
        from conftest import make_ready_outbox

        root = tmp_path / "proj"
        saipen = root / ".saipen"
        saipen.mkdir(parents=True)
        (saipen / "STATE.md").write_text(
            "---\nphase: DONE\ntask: none\n---\n", encoding="utf-8"
        )
        (saipen / "BOARD.md").write_text(
            "# BOARD\n## TODO\n- [ ] T-001 existing\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        (saipen / "LOG.md").write_text(
            "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
        )
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")

        results: list[dict] = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(collect_outbox_entry(root, "saihunt", "HUNT-001"))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r["ok"] is True for r in results)
        board = read_doc(saipen / "BOARD.md")
        log = read_doc(saipen / "LOG.md")
        assert board.count("T-002") == 1, "two collects duplicated the ticket"
        assert log.count("collect saihunt HUNT-001") == 1
        outbox = saipen / "extensions" / "subs" / "saihunt" / "kitchen" / "OUTBOX.md"
        assert outbox.read_text(encoding="utf-8").count("reviewed") == 1
