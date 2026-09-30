"""CORE-002: every write-capable protocol path uses the authoritative
ownership transaction, not the bare per-root RLock.

`WriteCoordinator.locked()` is only an RLock: it serializes threads while held
but does NOT inspect `_agent_owned`. `parser.move_ticket` delegated start/done/
block/unblock under `locked()` alone, so a launch could reserve the root after
the API pre-guard passed and the canonical mutation would still proceed.
`WriteCoordinator.recover()` had the same lock-only gap and additionally
skipped self-write attribution.

The fix is `WriteCoordinator.delegate()`: per-root lock + authoritative
`begin_app_tx` (refuses an agent-owned root) + delegated op + SelfWriteRegistry
finalization + guaranteed end. These tests pin both the refusal and the
attribution.
"""

from __future__ import annotations

import pytest
from conftest import make_conformant_project

from saipenview.parser import move_ticket
from saipenview.protocol_write import get_coordinator


@pytest.fixture
def project(tmp_path):
    return make_conformant_project(tmp_path, board_text=BOARD_TODO)


BOARD_TODO = (
    "# BOARD\n## DOING\n\n## TODO\n"
    "- [ ] T-001 open ticket\n- [ ] T-003 another\n"
    "## DONE\n- [x] T-004 finished | verify: it shipped\n"
    "## BLOCKED\n- [ ] T-005 stuck | blocker: external dep\n"
)


class TestMoveTicketOwnership:
    @pytest.mark.parametrize("action", ["start", "block", "unblock"])
    def test_move_ticket_refused_while_agent_owns(self, project, action):
        coord = get_coordinator()
        assert coord.ownership.reserve_agent(project) is True
        try:
            # The delegated canonical SAIO mutation must NOT run while an
            # agent owns the root.
            res = move_ticket(project, "T-001", action, "why")
            assert res.get("ok") is False, res
            assert res.get("code") == "WRITER_BUSY", res
        finally:
            coord.ownership.release_agent(project)

    def test_move_ticket_refused_for_done_while_agent_owns(self, project):
        coord = get_coordinator()
        assert coord.ownership.reserve_agent(project) is True
        try:
            res = move_ticket(project, "T-001", "done")
            assert res.get("ok") is False
            assert res.get("code") == "WRITER_BUSY", res
        finally:
            coord.ownership.release_agent(project)

    def test_guard_to_mutation_race_is_closed(self, project):
        """The exact CORE-002 TOCTOU: the caller's pre-check observes no agent,
        then a launch reserves the root BEFORE the delegated op takes its
        authoritative transaction. The op must refuse, never become writer #2.
        """
        coord = get_coordinator()
        # Simulate the API pre-guard seeing no agent (read-only pre-check).
        assert coord.ownership.agent_owns(project) is False

        # A launch reserves the root after the pre-check but before the op.
        assert coord.ownership.reserve_agent(project) is True
        try:
            res = move_ticket(project, "T-001", "start")
            assert res.get("ok") is False
            assert res.get("code") == "WRITER_BUSY", res
        finally:
            coord.ownership.release_agent(project)


class TestRecoverOwnership:
    def test_recover_refused_while_agent_owns(self, project, monkeypatch):
        from saipenview import saio

        called = {"n": 0}
        real_recover = saio.recover

        def spy(root, op_id=None):
            called["n"] += 1
            return real_recover(root, op_id)

        monkeypatch.setattr(saio, "recover", spy)

        coord = get_coordinator()
        assert coord.ownership.reserve_agent(project) is True
        try:
            res = coord.recover(project)
            assert res.get("ok") is False
            assert res.get("code") == "WRITER_BUSY", res
            assert called["n"] == 0, "saio.recover was invoked while agent owned"
        finally:
            coord.ownership.release_agent(project)

    def test_recover_arms_self_writes_for_changed_files(self, project, monkeypatch):
        """A successful recovery registers its changed_files so the watcher
        attributes them as self, not external (CORE-002).
        """
        coord = get_coordinator()

        # No pending op: recover returns a plain clean result. Use the real
        # delegate path and assert attribution plumbing by wrapping the op.
        registered: list[tuple[str, list[str]]] = []
        real_finalize = coord.finalize_self_writes

        def spy_finalize(root, rel_paths, fingerprints=None):
            registered.append((str(root), list(rel_paths)))
            return real_finalize(root, rel_paths, fingerprints)

        monkeypatch.setattr(coord, "finalize_self_writes", spy_finalize)
        res = coord.recover(project)
        # On a clean project recovery succeeds and the delegate finalizes
        # whatever it changed (possibly none) -- the call must happen.
        assert res.get("ok") is True, res
        assert registered, "recover did not reach the self-write finalizer"
