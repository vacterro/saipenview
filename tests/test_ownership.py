"""Single-writer ownership: app mutation vs agent launch, atomically decided.

The launch reservation and the app-protocol-transaction marker live in ONE
shared per-root lock (ownership.py); the canonical OS writer lock excludes
cross-process writers; multi-file operations carry every canonical dependency
as a plan precondition, so an external edit to a non-target dependency aborts
STALE_STATE with zero writes.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest
from conftest import make_conformant_project

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.parser import collect_outbox_entry, record_manual_work
from saipenview.protocol_write import get_coordinator
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(tmp_path)


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
        try:
            res = record_manual_work(project, "while agent owns")
            assert res.get("ok") is False
            assert res["code"] in ("WRITER_BUSY", "RECOVERY_REQUIRED"), res
            board = read_doc(project / ".saipen" / "BOARD.md")
            assert "T-001" not in board
        finally:
            coord.ownership.release_agent(project)
        # Released -> the mutation goes through.
        ok = record_manual_work(project, "after release")
        assert ok.get("ok") is True

    def test_ui_mutation_refused_while_agent_runs(self, api, tmp_path):
        root = make_conformant_project(tmp_path)
        api._config["pinned_roots"] = [str(root)]
        coord = get_coordinator()
        assert coord.ownership.reserve_agent(root)
        try:
            res = api.record_manual_work(str(root), "while agent runs")
            assert res.get("ok") is False
            res2 = api.toggle_ticket_status(str(root), "T-001", "block", "why")
            assert res2.get("ok") is False
            assert "T-001" not in read_doc(root / ".saipen" / "BOARD.md")
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
        assert outcomes[-1] == "launch:ok"


class TestCrossDocumentConflict:
    def test_external_state_edit_during_board_log_transaction_aborts(self, project):
        # record_manual_work writes LOG+BOARD+STATE and carries all three as
        # plan preconditions; an external STATE edit between the decision and
        # the commit aborts STALE_STATE with zero writes.
        from saipenview import saio

        def sabotage(root, plan):
            (root / ".saipen" / "STATE.md").write_text(
                read_doc(root / ".saipen" / "STATE.md") + "# external\n",
                encoding="utf-8",
            )
            return saio.apply(root, plan)

        def op_fn(r, attempt):
            docs = saio.snapshot(
                r, [".saipen/STATE.md", ".saipen/BOARD.md", ".saipen/LOG.md"]
            )
            return saio.plan(
                r,
                "viewer-test",
                {"operation": "viewer-test"},
                [
                    (
                        ".saipen/LOG.md",
                        "log",
                        docs[".saipen/LOG.md"].text_norm + "- 11.08.26 00:09 "
                        "[E-99] RUN: ext\n",
                        docs[".saipen/LOG.md"],
                    )
                ],
                {
                    ".saipen/LOG.md": docs[".saipen/LOG.md"].raw_hash,
                    ".saipen/BOARD.md": docs[".saipen/BOARD.md"].raw_hash,
                    ".saipen/STATE.md": docs[".saipen/STATE.md"].raw_hash,
                },
            )

        coord = get_coordinator()
        with coord.locked(project):
            plan = op_fn(project, 0)
            result = sabotage(project, plan)
        assert result["ok"] is False
        assert result["code"] in ("STALE_STATE", "CONFLICT"), result
        log = read_doc(project / ".saipen" / "LOG.md")
        assert "[E-99]" not in log

    def test_two_simultaneous_collects_do_not_duplicate(self, tmp_path):
        from conftest import make_ready_outbox

        root = make_conformant_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")

        results: list[dict] = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(
                collect_outbox_entry(root, "saihunt", "HUNT-001", explicit=True)
            )

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r["ok"] is True for r in results)
        board = read_doc(root / ".saipen" / "BOARD.md")
        log = read_doc(root / ".saipen" / "LOG.md")
        ticket_lines = [
            ln
            for ln in board.splitlines()
            if ln.strip().startswith("- [ ] T-") and "from saihunt HUNT-001" in ln
        ]
        assert len(ticket_lines) == 1, "two collects duplicated the ticket"
        assert log.count("collect saihunt HUNT-001") == 1
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        assert outbox.read_text(encoding="utf-8").count("reviewed") == 1
