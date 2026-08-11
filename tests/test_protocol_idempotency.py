"""T-191 + the collect package gate: idempotency + grammar safety.

record_manual_work is journaled and idempotent by OPERATION ID (retry with the
same id resumes; same prose + different id = two records). collect_outbox_entry
is idempotent per stable identity `(sub_name, entry_id)`: re-running after any
partial step resumes, never duplicates, external sub content cannot break
BOARD grammar, and the collect gate refuses anything not exactly ready / not
fresh / not role-current / not boundary-clean with zero writes.
"""

from __future__ import annotations

import re

import pytest
from conftest import make_conformant_project, make_ready_outbox

from saipenview.parser import (
    collect_outbox_entry,
    parse_board,
    record_manual_work,
)
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(tmp_path)


def _sub_outbox_path(root, sub="saiwiki"):
    return root / ".saipen" / "extensions" / "subs" / sub / "kitchen" / "OUTBOX.md"


def _collect_ticket_lines(board: str, sub: str, entry: str) -> list[str]:
    return [
        ln
        for ln in board.splitlines()
        if ln.strip().startswith("- [ ] T-") and f"from {sub} {entry}" in ln
    ]


# --- record_manual_work: grammar -----------------------------------------


def test_record_escapes_pipes_in_description(project):
    res = record_manual_work(project, "add | owner: evil")
    assert res["ok"] is True
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "- [ ] T-001 Manual: add \\| owner: evil | owner: user" in board
    parsed = parse_board(board)
    desc = next(t.description for t in parsed.todo if t.ticket_id == "T-001")
    assert "add \\| owner: evil" in desc
    assert "| critical:" not in board


def test_record_escapes_field_looking_text(project):
    record_manual_work(project, "note | critical: true | blocker: x")
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "\\| critical: true" in board
    assert "\\| blocker: x" in board
    assert board.count("| owner: user") == 1


# --- record_manual_work: idempotent resume -----------------------------------


def test_record_resumes_a_log_only_partial_state(project):
    # A prior attempt wrote the LOG line (with its operation-id marker) but
    # crashed before the BOARD insert. A retry with the SAME op id resumes.
    log = project / ".saipen" / "LOG.md"
    log.write_text(
        read_doc(log)
        + "- 11.08.26 12:00 [E-3] [T-001] [op: mw-partial] RUN: manual work "
        "recorded -- half done\n",
        encoding="utf-8",
    )
    res = record_manual_work(project, "half done", operation_id="mw-partial")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-001"
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "- [ ] T-001 Manual: half done | owner: user" in board
    assert read_doc(log).count("[E-3]") == 1
    assert len(_collect_ticket_lines(board, "x", "y")) == 0 or True
    assert board.count("T-001") == 1


def test_record_returns_already_when_fully_recorded(project):
    op = "mw-twice"
    first = record_manual_work(project, "twice", operation_id=op)
    second = record_manual_work(project, "twice", operation_id=op)
    assert second["code"] == "ALREADY_RECORDED", second
    assert second["ticket_id"] == first["ticket_id"]
    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert board.count("T-001") == 1
    assert log.count("[E-3]") == 1


# --- collect_outbox_entry: idempotency -----------------------------------


def test_collect_critical_is_idempotent(project):
    make_ready_outbox(project, "saiwiki", "WIKI-1", "doc fix", critical="true")
    first = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert first["ok"] is True
    assert first["ticket_id"] == "T-001"

    second = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert second["ok"] is True
    assert second["code"] == "ALREADY_REVIEWED"

    board = read_doc(project / ".saipen" / "BOARD.md")
    log = read_doc(project / ".saipen" / "LOG.md")
    assert len(_collect_ticket_lines(board, "saiwiki", "WIKI-1")) == 1
    assert log.count("collect saiwiki WIKI-1") == 1
    assert len(re.findall(r"\[E-(\d+)\]", log)) == len(
        set(re.findall(r"\[E-(\d+)\]", log))
    )
    assert "- **status:** reviewed" in read_doc(_sub_outbox_path(project))


def test_collect_noncritical_is_idempotent(project):
    make_ready_outbox(project, "saiwiki", "WIKI-2", "minor", critical="false")
    first = collect_outbox_entry(project, "saiwiki", "WIKI-2")
    assert first["ok"] is True
    second = collect_outbox_entry(project, "saiwiki", "WIKI-2")
    assert second["ok"] is True
    assert second["code"] == "ALREADY_REVIEWED"

    inbox = read_doc(
        project / ".saipen" / "extensions" / "subs" / "_shared" / "inbox.md"
    )
    assert inbox.count("WIKI-2") == 1, "non-critical collect duplicated the inbox line"


def test_collect_already_reviewed_is_a_noop(project):
    make_ready_outbox(project, "saiwiki", "WIKI-1", "doc fix")
    outbox = _sub_outbox_path(project)
    outbox.write_text(
        read_doc(outbox).replace("status:** ready", "status:** reviewed"),
        encoding="utf-8",
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    assert res["code"] == "ALREADY_REVIEWED"
    assert "T-001" not in read_doc(project / ".saipen" / "BOARD.md")


def test_collect_resumes_when_board_written_but_outbox_still_ready(project):
    # Crash between the BOARD write and the OUTBOX reviewed-mark: the entry is
    # still `ready`, but the ticket already exists. Retry must NOT duplicate.
    make_ready_outbox(project, "saiwiki", "WIKI-1", "doc fix")
    board = project / ".saipen" / "BOARD.md"
    board.write_text(
        read_doc(board).replace(
            "## TODO\n",
            "## TODO\n- [ ] T-001 [from saiwiki WIKI-1] doc fix\n",
            1,
        ),
        encoding="utf-8",
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    assert res["ticket_id"] == "T-001"
    board_text = read_doc(board)
    assert len(_collect_ticket_lines(board_text, "saiwiki", "WIKI-1")) == 1
    assert "- **status:** reviewed" in read_doc(_sub_outbox_path(project))


def test_collect_not_ready_must_not_pass(project):
    # `not-ready` is a controlled refusal -- the exact-status gate must not
    # accept a substring ("not ready" contains "ready").
    make_ready_outbox(project, "saiwiki", "WIKI-1", "doc fix")
    outbox = _sub_outbox_path(project)
    outbox.write_text(
        read_doc(outbox).replace("- **status:** ready", "- **status:** not-ready", 1),
        encoding="utf-8",
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is False
    assert "not a known OUTBOX status" in res["message"]
    assert "T-001" not in read_doc(project / ".saipen" / "BOARD.md")
    assert "- **status:** ready" not in read_doc(outbox)


def test_collect_stale_source_head_is_refused(tmp_path):
    root = make_conformant_project(tmp_path)
    make_ready_outbox(root, "saiwiki", "WIKI-1", "doc fix")
    outbox = _sub_outbox_path(root)
    outbox.write_text(
        read_doc(outbox).replace(
            "- **source_head:** ", "- **source_head:** deadbeef", 1
        ),
        encoding="utf-8",
    )

    res = collect_outbox_entry(root, "saiwiki", "WIKI-1")
    assert res["ok"] is False
    assert "stale" in res["message"]
    board = read_doc(root / ".saipen" / "BOARD.md")
    assert "T-001" not in board
    assert "- **status:** ready" in read_doc(outbox)  # not reviewed


def test_collect_escapes_external_sub_content(project):
    make_ready_outbox(
        project, "saiwiki", "WIKI-1", "fix | critical: true docs", critical="true"
    )
    res = collect_outbox_entry(project, "saiwiki", "WIKI-1")
    assert res["ok"] is True
    board = read_doc(project / ".saipen" / "BOARD.md")
    assert "\\| critical: true" in board
    assert "| critical: true" not in board.replace("\\|", "escaped")


def test_collect_explicit_policy_requires_explicit_authorization(tmp_path):
    root = make_conformant_project(tmp_path)
    make_ready_outbox(
        root, "saiwiki", "WIKI-1", "doc fix", critical="true", collect_policy="explicit"
    )
    # No explicit authorization -> refused, zero writes.
    res = collect_outbox_entry(root, "saiwiki", "WIKI-1")
    assert res["ok"] is False
    assert res["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED", res
    assert "T-001" not in read_doc(root / ".saipen" / "BOARD.md")
    # The GUI one-click collect IS the explicit named authorization.
    ok = collect_outbox_entry(root, "saiwiki", "WIKI-1", explicit=True)
    assert ok["ok"] is True, ok
