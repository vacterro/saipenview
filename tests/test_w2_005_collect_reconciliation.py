"""W2-005 (SRC-018 R009): collect commits then acknowledgement fails.

collect_outbox_entry() commits the canonical BOARD/LOG/STATE/OUTBOX mutation,
then acknowledges the package's own external-change token in a SEPARATE
post-commit step. The old code discarded acknowledge()'s boolean result and
returned plain success, so a persistence failure in the acknowledgement left
the caller believing reconciliation was complete.

Fixed contract:
  * a committed canonical mutation stays committed;
  * an acknowledgement failure returns a stable
    ``COMMITTED_RECONCILIATION_REQUIRED`` code plus the exact
    root/rel_path/token identity for acknowledgement-only recovery;
  * the canonical mutation receipt (changed_files/op_id) is preserved;
  * BOARD/LOG/STATE/OUTBOX are NEVER rerun to repair acknowledgement;
  * a newer external-change token is never cleared by retrying the older
    acknowledgement.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.external_changes import get_registry, normalize_rel
from saipenview.parser import collect_outbox_entry


@pytest.fixture
def project(tmp_path: Path):
    from tests.conftest import make_conformant_project, make_ready_outbox

    root = make_conformant_project(tmp_path)
    make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", critical="true")
    return root


def _package_rel() -> str:
    return normalize_rel("extensions/subs/saihunt/kitchen/OUTBOX.md")


def test_commit_stands_but_reconciliation_required_when_ack_fails(project: Path):
    """Commit succeeds; the post-commit acknowledge fails -> stable
    committed-but-reconciliation-required result with exact identity, and the
    canonical mutation is NOT rerun."""
    root = project
    package_rel = _package_rel()
    token = get_registry().record(str(root), package_rel, "package-fp")

    ack_calls: list[tuple] = []

    def failing_ack(root_arg, rel_arg, token_arg=None):
        ack_calls.append((root_arg, rel_arg, token_arg))
        # The canonical mutation has already committed by the time this runs.
        return False

    board = root / ".saipen" / "BOARD.md"

    with patch.object(get_registry(), "acknowledge", side_effect=failing_ack):
        res = collect_outbox_entry(root, "saihunt", "HUNT-001", explicit=True)

    # The canonical mutation committed (BOARD carries the collected entry).
    assert "HUNT-001" in board.read_text(encoding="utf-8")
    # Stable committed-but-reconciliation-required contract.
    assert res["ok"] is True
    assert res["code"] == "COMMITTED_RECONCILIATION_REQUIRED"
    assert res["reconciliation_required"] is True
    rec = res["reconciliation"]
    assert rec["kind"] == "external_change_ack"
    assert rec["root"] == str(root)
    assert rec["rel_path"] == package_rel
    assert rec["token"] == token
    # The canonical receipt is preserved (changed_files present from the commit).
    assert res.get("changed_files")
    # Acknowledgement was attempted exactly once with the exact identity --
    # BOARD/LOG/STATE/OUTBOX were not rerun to repair it.
    assert ack_calls == [(str(root), package_rel, token)]


def test_later_reconciliation_clears_only_that_token(project: Path):
    """After a committed-but-reconciliation-required result, a later
    acknowledge with the exact recorded identity clears exactly that token."""
    root = project
    package_rel = _package_rel()
    get_registry().record(str(root), package_rel, "package-fp")

    with patch.object(get_registry(), "acknowledge", return_value=False):
        res = collect_outbox_entry(root, "saihunt", "HUNT-001", explicit=True)
    assert res["code"] == "COMMITTED_RECONCILIATION_REQUIRED"
    rec = res["reconciliation"]

    # The pending entry is still there (ack failed) -- reconcile it now.
    assert any(c.rel_path == package_rel for c in get_registry().pending(str(root)))
    ok = get_registry().acknowledge(rec["root"], rec["rel_path"], rec["token"])
    assert ok is True
    assert all(
        c.rel_path != package_rel for c in get_registry().pending(str(root))
    )


def test_newer_token_not_cleared_by_older_reconciliation(project: Path):
    """A newer external-change write on the same path must NOT be cleared by
    retrying the OLDER acknowledgement token."""
    root = project
    package_rel = _package_rel()
    old_token = get_registry().record(str(root), package_rel, "package-fp-old")

    with patch.object(get_registry(), "acknowledge", return_value=False):
        res = collect_outbox_entry(root, "saihunt", "HUNT-001", explicit=True)
    assert res["code"] == "COMMITTED_RECONCILIATION_REQUIRED"
    rec = res["reconciliation"]
    assert rec["token"] == old_token

    # A NEWER external write replaces the pending entry with a new token.
    new_token = get_registry().record(str(root), package_rel, "package-fp-new")
    assert new_token != old_token

    # Retrying the OLD token must refuse (stale) and leave the newer entry.
    assert get_registry().acknowledge(rec["root"], rec["rel_path"], old_token) is False
    pending = [c for c in get_registry().pending(str(root)) if c.rel_path == package_rel]
    assert len(pending) == 1
    assert pending[0].token == new_token


def test_success_when_ack_succeeds_has_no_reconciliation(project: Path):
    """The happy path: acknowledgement succeeds -> plain success, no
    reconciliation contract."""
    root = project
    package_rel = _package_rel()
    get_registry().record(str(root), package_rel, "package-fp")

    res = collect_outbox_entry(root, "saihunt", "HUNT-001", explicit=True)
    assert res["ok"] is True
    assert res.get("code") != "COMMITTED_RECONCILIATION_REQUIRED"
    assert "reconciliation_required" not in res
    assert get_registry().pending(str(root)) == []
