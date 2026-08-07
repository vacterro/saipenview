"""T-183: the per-project write coordinator.

Every `.saipen/` mutation goes through ONE coordinator: per-root lock
(serialization of the app's own threads) + optimistic fingerprint/CAS (an
external writer between our read and our commit is a controlled ConflictError,
never a lost update) + the two id allocators that are the ONLY way a T-/E- id
is ever derived.
"""

from __future__ import annotations

import re
import threading
from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.parser import move_ticket, parse_board, record_manual_work
from saipenview.protocol_write import (
    ConflictError,
    get_coordinator,
    next_event_id,
    next_ticket_id,
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
    return sorted(int(m) for m in re.findall(rf"{prefix}-(\d+)", text))


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
    assert len(_all_ids(board, "T")) == 5  # 3 seeded + 2 new


def test_external_change_between_read_and_write_aborts(project):
    board = project / ".saipen" / "BOARD.md"
    coord = get_coordinator()

    def sabotage_then_mutate(text: str) -> str:
        # An external writer lands between our read and our commit.
        board.write_text("# BOARD\n## TODO\n- [ ] T-099 external\n", encoding="utf-8")
        return text + "- [ ] T-999 LOST\n"

    with pytest.raises(ConflictError):
        coord.mutate_doc(board, sabotage_then_mutate)
    # The external write survived; our update was NOT applied.
    assert "T-999" not in read_doc(board)
    assert "T-099 external" in read_doc(board)


def test_stale_cas_baseline_is_rejected(project):
    board = project / ".saipen" / "BOARD.md"
    coord = get_coordinator()
    # The caller read an OLD fingerprint; the file has moved since.
    with pytest.raises(ConflictError):
        coord.mutate_doc(board, lambda t: t + "x", expected_fingerprint="deadbeef")


def test_ids_are_centralized(project):
    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert next_ticket_id(board) == 4
    assert next_event_id(log) == 2


def test_stale_reader_cannot_append_to_a_moved_tail(project):
    """The LOG split-brain regression (T-184): a writer that read the log when
    its tail ended at E-1 must NOT append E-2 once the active tail has moved.
    The coordinator's CAS baseline is the fingerprint of the read the writer
    reasoned from -- if the tail moved since, the write aborts instead of
    forking the graph."""
    log = project / ".saipen" / "LOG.md"
    coord = get_coordinator()
    stale_fp = coord.fingerprint(log)  # the state the stale writer saw
    # The canonical writer moves the tail.
    first = record_manual_work(project, "canonical append")
    assert first["ok"] is True and first["event"] == "E-2"
    # The stale writer still holds its old baseline and tries to append.
    with pytest.raises(ConflictError):
        coord.mutate_doc(
            log,
            lambda t: t + "- 07.08.26 09:25 [E-356] RUN: stale fork\n",
            expected_fingerprint=stale_fp,
        )
    log_text = read_doc(log)
    assert "[E-356]" not in log_text, "stale writer forked the active graph"
    assert log_text.count("[E-2]") == 1


def test_mutation_refused_while_agent_runs(api, tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text(
        "---\nphase: HUNT\ntask: T-009\nupdated: 2026-08-01T00:00:00Z\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## TODO\n- [ ] T-009 thing\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    api._config["pinned_roots"] = [str(tmp_path)]
    with patch.object(api._process_manager, "is_running", return_value=True):
        res = api.record_manual_work(str(tmp_path), "while agent runs")
        assert res.get("ok") is False
        assert "agent" in res["error"].lower()
        res2 = api.toggle_ticket_status(str(tmp_path), "T-009", "start")
        assert res2.get("ok") is False
        # Nothing was written.
        assert "T-010" not in read_doc(saipen / "BOARD.md")
        assert read_doc(saipen / "LOG.md").count("[E-2]") == 0


def test_mutation_allowed_when_no_agent_runs(api, tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text(
        "---\nphase: HUNT\ntask: T-009\nupdated: 2026-08-01T00:00:00Z\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# BOARD\n## TODO\n- [ ] T-009 thing\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "- 07.08.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    api._config["pinned_roots"] = [str(tmp_path)]
    with patch.object(api._process_manager, "is_running", return_value=False):
        res = api.record_manual_work(str(tmp_path), "no agent")
        assert res["ok"] is True


# --- T-190 origin attribution (backend-side, per (root,file) fingerprint) ---


def test_self_write_origin_after_coordinator_mutation(api, tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    coord = get_coordinator()
    pushed = {}
    api._window = type(
        "W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)}
    )()
    with patch.object(api, "_refresh_one_project"):
        # Simulate the coordinator writing BOARD.md (registers the self-write),
        # then the watcher firing for it.
        coord.mutate_doc(saipen / "STATE.md", lambda t: t.replace("DONE", "HUNT"))
        api._on_file_changed({"root": str(tmp_path), "file": "STATE.md"})
    assert '"self"' in pushed["js"], pushed["js"]


def test_external_write_reports_external(api, tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    pushed = {}
    api._window = type(
        "W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)}
    )()
    with patch.object(api, "_refresh_one_project"):
        # No coordinator write happened; an outside edit did.
        (saipen / "STATE.md").write_text("---\nphase: HUNT\n---\n", encoding="utf-8")
        api._on_file_changed({"root": str(tmp_path), "file": "STATE.md"})
    assert '"external"' in pushed["js"], pushed["js"]


def test_external_edit_after_self_write_reports_external(api, tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    coord = get_coordinator()
    pushed = {}
    api._window = type(
        "W", (), {"evaluate_js": lambda self, s: pushed.setdefault("js", s)}
    )()
    with patch.object(api, "_refresh_one_project"):
        coord.mutate_doc(saipen / "STATE.md", lambda t: t.replace("DONE", "HUNT"))
        # A human/tool overwrites AFTER our write: the content is no longer ours.
        (saipen / "STATE.md").write_text("---\nphase: BLOCKED\n---\n", encoding="utf-8")
        api._on_file_changed({"root": str(tmp_path), "file": "STATE.md"})
    assert '"external"' in pushed["js"], pushed["js"]


def test_failed_write_never_registers(project):
    board = project / ".saipen" / "BOARD.md"
    coord = get_coordinator()
    before = coord.self_writes.consume(str(project), "BOARD.md", "anything")
    assert before is False
    with pytest.raises(ConflictError):
        coord.mutate_doc(board, lambda t: t + "x", expected_fingerprint="stale")
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
    # Checkbox vs section agreement: DONE only [x], DOING only [/], TODO [ ].
    lines = board_text.splitlines()
    current = None
    for line in lines:
        if line.startswith("## "):
            current = line[3:]
            continue
        m = re.match(r"^- \[( |x|/)\] T-\d+", line)
        if m:
            box = m.group(1)
            if current == "DONE":
                assert box == "x", line
            elif current == "DOING":
                assert box == "/", line
            elif current in ("TODO", "BLOCKED"):
                assert box == " ", line
    log = read_doc(project / ".saipen" / "LOG.md")
    events = _all_ids(log, "E")
    assert len(events) == len(set(events)), f"duplicate E ids: {events}"
    assert events == sorted(events), f"E ids out of order: {events}"
    # T-002 moved to DOING, and both records are present.
    assert any(t.ticket_id == "T-002" for t in board.doing)
    assert any(t.ticket_id in ("T-004", "T-005") for t in board.todo)
    assert all(
        t.description.startswith("Manual:")
        for t in board.todo
        if t.ticket_id != "T-002"
    )
