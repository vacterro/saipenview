"""T-34 / W2-024: record_manual_work operation_id payload binding.

LOG recovery keyed only on operation_id. Retrying with a DIFFERENT
description and the same op_id planned a new ticket while LOG remained
ORIGINAL. Mismatched retries returned ALREADY_RECORDED without
identifying the payload conflict.

Fix: bind operation_id to canonical normalized payload. Same id+same
payload -> resume/no-op. Same id+different payload -> IDEMPOTENCY_CONFLICT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saipenview.parser import record_manual_work
from tests.conftest import make_conformant_project


def test_same_id_same_payload_resumes(tmp_path: Path):
    """Exact retry is idempotent."""
    root = make_conformant_project(tmp_path)
    op = "mw-same-payload"
    first = record_manual_work(root, "updated docs", operation_id=op)
    second = record_manual_work(root, "updated docs", operation_id=op)
    assert second["code"] == "ALREADY_RECORDED"
    assert second["ticket_id"] == first["ticket_id"]


def test_same_id_different_payload_refused(tmp_path: Path):
    """Different description with same op_id -> IDEMPOTENCY_CONFLICT."""
    root = make_conformant_project(tmp_path)
    op = "mw-diff-payload"
    first = record_manual_work(root, "original desc", operation_id=op)
    assert first["ok"] is True
    second = record_manual_work(root, "different desc", operation_id=op)
    assert second["code"] == "IDEMPOTENCY_CONFLICT", second
    # Board must have exactly one ticket
    from saipenview.textio import read_doc

    board = read_doc(root / ".saipen" / "BOARD.md")
    assert board.count("Manual: original desc") == 1
    assert board.count("Manual: different desc") == 0


def test_matching_partial_retry_reconstructs_original(tmp_path: Path):
    """CRASH-recovery: partial LOG-only entry resumed with original text."""
    root = make_conformant_project(tmp_path)
    op = "mw-crash-resume"
    # First call creates the LOG line but we simulate a crash by manually
    # writing a partial log entry (no BOARD ticket).
    from saipenview.textio import read_doc
    import re

    log_path = root / ".saipen" / "LOG.md"
    log_text = read_doc(log_path)
    # Insert a manual-work LOG line with op_id but no corresponding BOARD ticket
    log_text += (
        "- 11.08.26 12:00 [E-3] [T-001] [op: "
        + op
        + "] RUN: manual work recorded -- crash-recovery desc\n"
    )
    log_path.write_text(log_text, encoding="utf-8")
    # Update last_event in STATE
    state_path = root / ".saipen" / "STATE.md"
    state_text = read_doc(state_path)
    state_text = re.sub(r"last_event:\s*\d+", "last_event: 3", state_text)
    state_path.write_text(state_text, encoding="utf-8")

    # Retry with SAME description -> resumes T-001
    res = record_manual_work(root, "crash-recovery desc", operation_id=op)
    assert res["ok"] is True
    assert res["ticket_id"] == "T-001"
    board = read_doc(root / ".saipen" / "BOARD.md")
    assert "T-001" in board
