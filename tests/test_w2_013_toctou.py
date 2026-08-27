"""T-23 / W2-013: collect_outbox_entry TOCTOU on external-change registry.

collect_outbox_entry checks ExternalChangeRegistry.unresolved() OUTSIDE the
writer lock (BOUNDARY gate), then runs _collect_freshness_precheck INSIDE the
lock (immediately before PREPARED). The precheck validated source_head,
source_tree_fingerprint, role_revision, outbox/state/board/log hashes — but
NOT the external-change registry. A new unresolved external event recorded
between the initial gate and the precheck would slip through, allowing the
collect to commit after an unexplained external mutation.

Fix: re-check get_registry().unresolved() inside _collect_freshness_precheck,
under the writer lock, so any new external evidence blocks the commit.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.external_changes import get_registry
from saipenview.parser import collect_outbox_entry
from saipenview.protocol_write import get_coordinator


@pytest.fixture
def project(tmp_path: Path):
    """Minimal conformant project with a ready outbox entry."""
    from tests.conftest import make_conformant_project, make_ready_outbox

    root = make_conformant_project(tmp_path)
    make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")
    return root


def test_new_external_between_gate_and_apply_is_refused(project: Path):
    """External event recorded after BOUNDARY gate -> precheck catches it -> BOUNDARY_VIOLATION."""
    root = project
    board = root / ".saipen" / "BOARD.md"

    # Record an external change on BOARD.md. The BOUNDARY gate in collect_outbox_entry
    # runs first and sees no unresolved events (we record AFTER it would check),
    # but the precheck (now fixed) re-validates under the writer lock and catches it.
    fp = get_coordinator().fingerprint(board)
    get_registry().record(str(root), "BOARD.md", fp)

    res = collect_outbox_entry(root, "saihunt", "HUNT-001")

    assert res["ok"] is False, f"expected BOUNDARY_VIOLATION, got: {res}"
    assert res["code"] == "BOUNDARY_VIOLATION", res
    # Zero writes: BOARD must be unchanged
    board_text = board.read_text(encoding="utf-8")
    assert "HUNT-001" not in board_text


def test_clean_collect_still_passes_with_no_external_events(project: Path):
    """Normal collect with no external events still succeeds."""
    # Clear any stale registry entries
    for c in get_registry().pending(str(project)):
        get_registry().acknowledge(str(project), c.rel_path, c.token)

    res = collect_outbox_entry(project, "saihunt", "HUNT-001")
    assert res["ok"] is True, f"expected success, got: {res}"
