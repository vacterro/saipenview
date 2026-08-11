"""T-183 + P0: the per-project write coordinator.

Every `.saipen/` mutation goes through ONE coordinator, which commits through
the CANONICAL writer pipeline (OS lock + journal + recovery + verification).
App threads serialize on the per-root lock; cross-process writers are excluded
by the canonical OS lock; decisions are bound to the snapshot whose hashes
become the plan's preconditions, so a stale decision aborts STALE_STATE with
zero writes.
"""

from __future__ import annotations

import re
import threading
from unittest.mock import patch

import pytest
from conftest import make_conformant_project

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.parser import move_ticket, parse_board, record_manual_work
from saipenview.protocol_write import get_coordinator
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(
        tmp_path,
        board_text="# BOARD\n## DOING\n\n## TODO\n- [ ] T-002 open\n"
        "## DONE\n## BLOCKED\n",
    )


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


def _all_ids(text: str, prefix: str) -> list[int]:
    # Events ride in [E-N] brackets (a [parent: E-N] ref is not an event);
    # tickets are bare T-NNN tokens.
    anchor = r"\[E-" if prefix == "E" else r"\bT-"
    return sorted(int(m) for m in re.findall(rf"{anchor}(\d+)\b", text))


def test_two_concurrent_records_allocate_distinct_ids(project):
    results: list[dict] = []
    barrier = threading.Barrier(2)

    def worker(name: str):
        barrier.wait()
        results.append(record_manual_work(project, name))

    threads = [threading.Thread(target=worker, args=(f"edit {i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r["ok"] is True for r in results)
    ticket_ids = {r["ticket_id"] for r in results}
    events = {r["event"] for r in results}
    assert len(ticket_ids) == 2, f"two writers shared a ticket id: {ticket_ids}"
    assert len(events) == 2, f"two writers shared an event id: {events}"

    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert len(_all_ids(board, "T")) == len(set(_all_ids(board, "T")))
    assert len(_all_ids(log, "E")) == len(set(_all_ids(log, "E")))
    assert len(_all_ids(board, "T")) == 3  # 1 seeded + 2 new


def test_external_change_between_read_and_commit_aborts(project):
    # A stale CAS baseline must not commit: the coordinator's mutate_doc with
    # an expected fingerprint that no longer matches refuses STALE_STATE with
    # zero writes.
    coord = get_coordinator()
    board = project / ".saipen" / "BOARD.md"
    result = coord.mutate_doc(
        board, lambda t: t + "- [ ] T-999 LOST\n", expected_fingerprint="deadbeef"
    )
    assert result["ok"] is False
    assert result["code"] == "STALE_STATE", result
    assert "T-999" not in read_doc(board)


def test_ids_are_centralized(project):
    # The ONE allocation authority is the canonical SAIOPS allocator (sealed
    # history included, synthetic T-998/999 excluded).
    from saipenview import saio

    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert saio.next_ticket_id(project, board, log) == 3
    assert saio.next_event_id(project, log) == 3


def test_stale_reader_cannot_append_to_a_moved_tail(project):
    """The LOG split-brain regression (T-184): a decision read when the tail
    ended at E-2 must not commit once the tail has moved. The plan's
    precondition is the OLD snapshot's hash; the moved tail makes the commit
    STALE_STATE."""
    log = project / ".saipen" / "LOG.md"
    docs = __import__("saipenview.saio", fromlist=["snapshot"]).snapshot(
        project, [".saipen/LOG.md"]
    )
    old_hash = docs[".saipen/LOG.md"].raw_hash
    # The canonical writer moves the tail.
    first = record_manual_work(project, "canonical append")
    assert first["ok"] is True and first["event"] == "E-3"
    # A stale writer still holding the old baseline tries to append.
    coord = get_coordinator()
    result = coord.mutate_doc(
        log,
        lambda t: t + "- 11.08.26 09:25 [E-356] RUN: stale fork\n",
        expected_fingerprint=old_hash,
    )
    assert result["ok"] is False
    assert result["code"] == "STALE_STATE", result
    log_text = read_doc(log)
    assert "[E-356]" not in log_text, "stale writer forked the active graph"
    assert log_text.count("[E-3]") == 1


def test_mutation_refused_while_agent_runs(api, tmp_path):
    root = make_conformant_project(
        tmp_path,
        phase="BUILD",
        task="T-001",
        next_action="PHASE BUILD T-001",
        board_text="# BOARD\n## DOING\n- [/] T-001 x\n## TODO\n## DONE\n## BLOCKED\n",
    )
    api._config["pinned_roots"] = [str(root)]

    coord = get_coordinator()
    assert coord.ownership.reserve_agent(root)
    try:
        res = api.record_manual_work(str(root), "while agent runs")
        assert res.get("ok") is False
        assert (
            "agent" in res.get("error", "").lower()
            or "busy" in res.get("code", "").lower()
        )
        res2 = api.toggle_ticket_status(str(root), "T-001", "block", "why")
        assert res2.get("ok") is False
    finally:
        coord.ownership.release_agent(root)


def test_mutation_allowed_when_no_agent_runs(api, tmp_path):
    root = make_conformant_project(tmp_path)
    api._config["pinned_roots"] = [str(root)]
    res = api.record_manual_work(str(root), "no agent")
    assert res["ok"] is True


# --- T-190 origin attribution (backend-side, per (root,file) fingerprint) ---


def _window_stub(pushed):
    return type("W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)})()


def test_self_write_origin_after_coordinator_mutation(api, tmp_path):
    root = make_conformant_project(tmp_path)
    pushed = {}
    api._window = _window_stub(pushed)
    with patch.object(api, "_refresh_one_project"):
        res = record_manual_work(root, "self write")
        assert res["ok"] is True
        # Simulate the watcher firing for the changed files.
        api._on_file_changed({"root": str(root), "file": "LOG.md"})
    assert '"self"' in pushed["js"], pushed["js"]


def test_external_write_reports_external(api, tmp_path):
    root = make_conformant_project(tmp_path)
    pushed = {}
    api._window = _window_stub(pushed)
    with patch.object(api, "_refresh_one_project"):
        # No coordinator write happened; an outside edit did.
        state = root / ".saipen" / "STATE.md"
        state.write_text(
            read_doc(state).replace("phase: DONE", "phase: HUNT"), encoding="utf-8"
        )
        api._on_file_changed({"root": str(root), "file": "STATE.md"})
    assert '"external"' in pushed["js"], pushed["js"]


def test_external_edit_after_self_write_reports_external(api, tmp_path):
    root = make_conformant_project(tmp_path)
    pushed = {}
    api._window = _window_stub(pushed)
    with patch.object(api, "_refresh_one_project"):
        res = record_manual_work(root, "self write")
        assert res["ok"] is True
        # A human/tool overwrites AFTER our write: the content is no longer ours.
        log = root / ".saipen" / "LOG.md"
        log.write_text(read_doc(log) + "external noise\n", encoding="utf-8")
        api._on_file_changed({"root": str(root), "file": "LOG.md"})
    assert '"external"' in pushed["js"], pushed["js"]


def test_failed_write_never_registers(project):
    coord = get_coordinator()
    board = project / ".saipen" / "BOARD.md"
    before = coord.self_writes.consume(str(project), "BOARD.md", "anything")
    assert before is False
    result = coord.mutate_doc(board, lambda t: t + "x", expected_fingerprint="stale")
    assert result["ok"] is False
    after = coord.self_writes.consume(str(project), "BOARD.md", "anything")
    assert after is False, "a failed write registered a self-write"


def test_concurrent_mixed_mutations_keep_board_valid(project):
    barrier = threading.Barrier(3)

    def toggle():
        barrier.wait()
        move_ticket(project, "T-002", "start")

    def record_a():
        barrier.wait()
        record_manual_work(project, "a")

    def record_b():
        barrier.wait()
        record_manual_work(project, "b")

    threads = [
        threading.Thread(target=toggle),
        threading.Thread(target=record_a),
        threading.Thread(target=record_b),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    board_text = read_doc(project / ".saipen" / "BOARD.md")
    board = parse_board(board_text)
    t_ids = _all_ids(board_text, "T")
    assert len(t_ids) == len(set(t_ids)), f"duplicate T ids: {t_ids}"
    log = read_doc(project / ".saipen" / "LOG.md")
    events = _all_ids(log, "E")
    assert len(events) == len(set(events)), f"duplicate E ids: {events}"
    assert events == sorted(events), f"E ids out of order: {events}"
    # T-002 was claimed (started) by the canonical claim op.
    assert any(t.ticket_id == "T-002" for t in board.doing)
    assert all(
        t.description.startswith("Manual:")
        for t in board.todo
        if t.ticket_id not in ("T-002",)
    )
