"""SRC-004 R011 / W2-003: two app writers on one root must be serialized.

`_git_mutation_tx` documented that it "acquires the RootOwnership lock before
fingerprint verification and retains it through the complete Git command".
It called `begin_app_tx`, which takes `lock(root)` inside its own `with` block
and releases it on return -- so no lock spanned the mutation, and the depth
counter let a second app writer increment to 2 and proceed. Reproduced against
the real `RootOwnership` as `A:ENTER B:ENTER B:EXIT A:EXIT`.

`tests/test_core001_git_tx.py` is the false-positive coverage the audit names:
every case there asserts app-vs-AGENT exclusion (`reserve_agent` blocks or
returns), which the reservation pair already provided. Nothing asserted
app-vs-app, which is the invariant the docstring claimed.

The two verbs are now distinct on purpose -- `begin_app_tx` MARKS app activity
(correct for the write coordinator, which takes the lock itself), and
`app_transaction` MARKS AND SERIALIZES -- so a caller cannot get the weaker one
by accident.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from saipenview.ownership import RootOwnership


@pytest.fixture
def own() -> RootOwnership:
    return RootOwnership()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "repo"


def _sequence_writer(own: RootOwnership, root: Path, seq: list[str], hold: float):
    def writer(name: str) -> None:
        with own.app_transaction(root) as owned:
            if not owned:
                seq.append(f"{name}:REFUSED")
                return
            seq.append(f"{name}:ENTER")
            time.sleep(hold)
            seq.append(f"{name}:EXIT")

    return writer


class TestAppVsAppSerialization:
    def test_two_app_writers_do_not_interleave(self, own, root):
        """The invariant the old docstring claimed and did not hold.

        Interleaving is what lets two commit/revert/clean operations verify the
        same fingerprint and then mix their index and worktree work, producing a
        combined tree effect outside the previewed transaction.
        """
        seq: list[str] = []
        writer = _sequence_writer(own, root, seq, hold=0.1)

        a = threading.Thread(target=writer, args=("A",))
        b = threading.Thread(target=writer, args=("B",))
        a.start()
        time.sleep(0.02)
        b.start()
        a.join(timeout=5)
        b.join(timeout=5)

        assert not a.is_alive() and not b.is_alive()
        assert seq in (
            ["A:ENTER", "A:EXIT", "B:ENTER", "B:EXIT"],
            ["B:ENTER", "B:EXIT", "A:ENTER", "A:EXIT"],
        ), f"app writers interleaved: {seq}"

    def test_bare_begin_app_tx_still_only_marks(self, own, root):
        """The weaker verb is documented as weaker, and proven so.

        The write coordinator holds `lock(root)` itself around the whole
        mutation, so `begin_app_tx` marking without serializing is correct
        THERE. Pinning the difference keeps the two from being quietly merged
        into one ambiguous call that some caller then relies on for exclusion.
        """
        assert own.begin_app_tx(root) is True
        assert own.begin_app_tx(root) is True, (
            "begin_app_tx is a depth counter, not a mutex -- if this ever "
            "refuses, app_transaction's reason for existing changed"
        )
        own.end_app_tx(root)
        own.end_app_tx(root)


class TestAgentExclusionUnchanged:
    def test_agent_owned_root_refuses_the_transaction(self, own, root):
        assert own.reserve_agent(root) is True
        with own.app_transaction(root) as owned:
            assert owned is False
        own.release_agent(root)
        with own.app_transaction(root) as owned:
            assert owned is True

    def test_a_launch_cannot_reserve_while_the_transaction_is_held(self, own, root):
        """App-vs-agent must keep working: the launch WAITS, it does not race.

        `reserve_agent` takes the same per-root lock, so while the serialized
        transaction holds it the launch makes no decision at all -- which is
        the point: it cannot observe a half-finished mutation. Once the context
        exits, the transaction is over and the launch legitimately succeeds.
        Both halves are asserted, because "blocked" alone would also be true of
        a launch that then reserved a root mid-mutation.
        """
        reserved: list[bool] = []

        def launch() -> None:
            reserved.append(own.reserve_agent(root))

        with own.app_transaction(root) as owned:
            assert owned is True
            t = threading.Thread(target=launch)
            t.start()
            time.sleep(0.1)
            assert reserved == [], "reserve_agent did not block on the held lock"

        t.join(timeout=5)
        assert not t.is_alive()
        assert reserved == [True], (
            f"the launch never completed after the transaction released: {reserved}"
        )
        own.release_agent(root)

    def test_a_launch_refuses_while_the_mark_outlives_the_lock(self, own, root):
        """The reservation pair, not the lock, is what refuses a launch.

        The coordinator marks a transaction and releases the lock between its
        own steps, so the refusal has to come from `_app_tx` being non-empty --
        otherwise a launch could slip into exactly that gap.
        """
        assert own.begin_app_tx(root) is True
        try:
            assert own.reserve_agent(root) is False
        finally:
            own.end_app_tx(root)
        assert own.reserve_agent(root) is True
        own.release_agent(root)

    def test_transaction_releases_on_exception(self, own, root):
        """A failing mutation must not leave the root permanently owned."""
        with pytest.raises(RuntimeError):
            with own.app_transaction(root) as owned:
                assert owned is True
                raise RuntimeError("mutation blew up")

        assert own.reserve_agent(root) is True, (
            "an exception inside the transaction leaked the app_tx mark"
        )
        own.release_agent(root)

    def test_reentrant_on_the_same_thread(self, own, root):
        """A coordinator mutation nested in the context must still work.

        The lock is an RLock and the counter is a depth counter, so nesting is
        legal. Without this, wrapping an existing coordinator call in the new
        context would deadlock.
        """
        with own.app_transaction(root) as outer:
            assert outer is True
            with own.app_transaction(root) as inner:
                assert inner is True
        assert own.reserve_agent(root) is True
        own.release_agent(root)


class TestGitMutationUsesTheSerializedForm:
    def test_git_mutation_tx_serializes_two_callers(self, tmp_path, monkeypatch):
        """End to end through the real Api wrapper, not the primitive.

        The audit's complaint was specifically about `_git_mutation_tx`, and the
        primitive being correct proves nothing if the wrapper still calls the
        weaker verb. The mutation body is a stub: this measures serialization,
        not git.
        """
        from saipenview.api import Api
        from saipenview.protocol_write import get_coordinator

        api = object.__new__(Api)
        root = str(tmp_path / "repo")
        seq: list[str] = []

        def slow_mutation(_root: str) -> dict:
            seq.append("ENTER")
            time.sleep(0.1)
            seq.append("EXIT")
            return {"ok": True}

        results: list[dict] = []

        def caller() -> None:
            results.append(api._git_mutation_tx(root, slow_mutation))

        a = threading.Thread(target=caller)
        b = threading.Thread(target=caller)
        a.start()
        time.sleep(0.02)
        b.start()
        a.join(timeout=5)
        b.join(timeout=5)

        assert not a.is_alive() and not b.is_alive()
        assert seq == ["ENTER", "EXIT", "ENTER", "EXIT"], (
            f"_git_mutation_tx let two mutations interleave: {seq}"
        )
        assert results == [{"ok": True}, {"ok": True}]

        # The root must be fully released afterwards.
        ownership = get_coordinator().ownership
        assert ownership.reserve_agent(Path(root)) is True
        ownership.release_agent(Path(root))

    def test_git_mutation_tx_refuses_while_an_agent_owns_the_root(self, tmp_path):
        from saipenview.api import Api
        from saipenview.protocol_write import get_coordinator

        api = object.__new__(Api)
        root = str(tmp_path / "repo")
        ownership = get_coordinator().ownership

        assert ownership.reserve_agent(Path(root)) is True
        try:
            result = api._git_mutation_tx(root, lambda _r: {"ok": True})
            assert result["ok"] is False
            assert result["code"] == "WRITER_BUSY"
        finally:
            ownership.release_agent(Path(root))
