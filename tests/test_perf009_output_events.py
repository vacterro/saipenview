"""T-598 / PERF-009: the agent-output event path must cost nothing when
nobody listens, and must never emit one bridge call per stdout line.

The reader thread used to build a structured payload (engine parse + dict)
for every line and publish it to an event with zero production subscribers,
while the UI stayed on a five-second poll. The contract now is:

* default (unsubscribed) run: no per-line payload work, no events at all;
* a legacy ``agent.output`` subscriber still gets the exact per-line payload;
* a coalesced ``agent.output_available`` subscriber gets bounded-cadence root
  notices -- thousands of lines collapse to at most one notification per
  interval per root;
* the frontend keeps single-flight cursor semantics and moves live output off
  the registry poll onto its own ticker that stays silent while hidden.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.events import EventBus
from saipenview.runtime import OUTPUT_NOTIFY_INTERVAL_SECONDS, ProcessManager
from saipenview.sessions import SessionStore

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


class _EchoEngine(AgentEngine):
    def __init__(self, script: str) -> None:
        self._script = script

    @property
    def name(self) -> str:
        return "echo-perf009"

    @property
    def display_name(self) -> str:
        return "Echo PERF-009"

    def detect(self) -> bool:
        return True

    def build_command(self, project_root, instruction, *, extra_args=None):
        return [sys.executable, "-c", self._script]

    @property
    def supports_stdin(self) -> bool:
        return False


def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def manager(tmp_path):
    pm = ProcessManager()
    pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
    yield pm
    pm.stop_all()
    pm._output_notifier.cancel()


class TestEventBusHasSubscribers:
    def test_reflects_registration_exactly(self):
        bus = EventBus()

        def cb(data):
            pass

        assert bus.has_subscribers("agent.output") is False
        bus.subscribe("agent.output", cb)
        assert bus.has_subscribers("agent.output") is True
        bus.unsubscribe("agent.output", cb)
        assert bus.has_subscribers("agent.output") is False

    def test_other_event_types_are_not_visible(self):
        bus = EventBus()

        def cb(data):
            pass

        bus.subscribe("other.event", cb)
        assert bus.has_subscribers("agent.output") is False


class TestDefaultRunPublishesNothing:
    def test_unsubscribed_run_emits_no_output_events(self, manager, tmp_path):
        root = str(tmp_path)
        seen: list[str] = []
        original = manager._output_notifier._bus.publish

        def recorder(event_type, data=None):
            seen.append(event_type)
            original(event_type, data)

        manager._output_notifier._bus.publish = recorder
        engine = _EchoEngine("for i in range(50):\n    print('l%d' % i, flush=True)\n")
        manager.launch(engine, root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "done")

        time.sleep(OUTPUT_NOTIFY_INTERVAL_SECONDS * 3)
        assert not any(t.startswith("agent.output") for t in seen), seen

    def test_unsubscribed_touch_allocates_no_timer(self, tmp_path):
        notifier = ProcessManager()._output_notifier
        notifier.touch(str(tmp_path))
        assert notifier._roots == {}


class TestLegacyPerLineContract:
    def test_subscriber_gets_exact_per_line_payloads(self, manager, tmp_path):
        from saipenview.events import event_bus

        payloads: list[dict] = []
        event_bus.subscribe("agent.output", payloads.append)
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                "for i in range(3):\n    print('line %d' % i, flush=True)\n"
            )
            manager.launch(engine, root, "go")
            assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
            time.sleep(0.2)

            assert [p["line"] for p in payloads] == ["line 0", "line 1", "line 2"]
            assert all(p["root"] == root for p in payloads)
            assert [p["line_num"] for p in payloads] == [1, 2, 3]
            assert all(p["engine"] == "echo-perf009" for p in payloads)
            assert all(p["event"] is None for p in payloads)
        finally:
            from saipenview.events import event_bus as bus

            bus.unsubscribe("agent.output", payloads.append)


class TestCoalescedNotifications:
    def test_burst_collapses_to_bounded_notifications(self, manager, tmp_path):
        from saipenview.events import event_bus

        notices: list[dict] = []
        event_bus.subscribe("agent.output_available", notices.append)
        try:
            root = str(tmp_path)
            # The run must outlive one notification interval: a run that
            # finishes faster than that has its pending timer cancelled by
            # finalization -- correct, because agent.finished already makes
            # the UI pull the complete transcript.
            engine = _EchoEngine(
                "import time\n"
                "for i in range(80):\n"
                "    print('burst %d' % i, flush=True)\n"
                "    time.sleep(0.01)\n"
            )
            started = time.monotonic()
            manager.launch(engine, root, "go")
            assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
            # Let any last in-window timer fire before counting.
            time.sleep(OUTPUT_NOTIFY_INTERVAL_SECONDS * 2)
            elapsed = time.monotonic() - started

            bound = elapsed / OUTPUT_NOTIFY_INTERVAL_SECONDS + 3
            roots = {n["root"] for n in notices}
            assert roots == {root}
            assert len(notices) <= max(bound, 2), (len(notices), bound)
            assert len(notices) >= 1
        finally:
            event_bus.unsubscribe("agent.output_available", notices.append)

    def test_finalization_cancels_pending_notice_of_a_fast_run(self, manager, tmp_path):
        """A run that ends inside one interval delivers no availability notice
        -- the terminal event owns the refresh instead.

        PERF-001 rewrite: deterministic, no wall-clock dependence. The fire
        callback is held behind a gate from BEFORE the timer can transition,
        so the finalization cancel() always wins the race regardless of how
        fast the subprocess drains. On the pre-barrier notifier the released
        fire still published (red control); the synchronized lifecycle
        suppresses it because the root was cancelled before the transition.
        """
        from saipenview.events import event_bus

        notices: list[dict] = []
        event_bus.subscribe("agent.output_available", notices.append)
        notifier = manager._output_notifier
        gate = threading.Event()
        entered = threading.Event()
        original_fire = notifier._fire

        def gated_fire(root, gen):
            entered.set()
            gate.wait()
            original_fire(root, gen)

        notifier._fire = gated_fire
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                "for i in range(200):\n    print('l%d' % i, flush=True)\n"
            )
            manager.launch(engine, root, "go")
            assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
            # The pending/in-flight fire (if its timer activated) is still
            # parked behind the gate; finalization's cancel has already run.
            gate.set()
            # Either the fire thread entered (branch 1) or the timer was
            # cancelled before its tick (branch 2); both must stay silent.
            entered.wait(timeout=5)
            assert _wait_for(
                lambda: root not in notifier._roots
                or (
                    notifier._roots[root].timer is None
                    and not notifier._roots[root].publishers
                )
            )
            assert notices == []
            # ...and the data is not lost: the cursor API answers for it all.
            out = manager.get_output(root)
            assert out["total"] == 200
        finally:
            notifier._fire = original_fire
            event_bus.unsubscribe("agent.output_available", notices.append)


class TestDeterministicCancelBarrier:
    """PERF-001: cancel() is a barrier, not a dictionary remove.

    A fire that already entered _fire used to publish after cancel()
    returned. The synchronized lifecycle gives cancel exactly one of two
    outcomes: the racing publication is suppressed (cancel won the
    transition race) or completes before cancel returns (fire was already
    in-flight). Both halves are proven here without wall-clock games.
    """

    def _notifier(self, bus, interval=0.05):
        from saipenview.runtime import _OutputNotifier

        return _OutputNotifier(bus=bus, interval=interval)

    def _blocking_bus(self, recorder, release: threading.Event):
        class _Bus:
            def has_subscribers(self, event_type):
                return event_type == "agent.output_available"

            def publish(self, event_type, data=None):
                release.wait()
                recorder.append(data)

        return _Bus()

    def _root_state(self, notifier, root):
        return notifier._roots.get(root)

    def _drained(self, notifier, root):
        st = self._root_state(notifier, root)
        return st is None or (st.timer is None and not st.publishers)

    def _has_publisher(self, notifier, root):
        st = self._root_state(notifier, root)
        return st is not None and bool(st.publishers)

    def _has_timer(self, notifier, root):
        st = self._root_state(notifier, root)
        return st is not None and st.timer is not None

    def _barriered(self, notifier, root):
        # cancel(root) must have atomically invalidated the pending cycle
        # (gen cleared) and detached its Timer BEFORE it released the mutex to
        # wait for older publishers.
        with notifier._cond:
            st = notifier._roots.get(root)
            return st is not None and st.timer is None and st.gen == -1

    def _pending_gen(self, notifier, root):
        with notifier._cond:
            st = notifier._roots.get(root)
            if st is None:
                return None
            t2 = st.timer
            gen2 = st.gen
        if t2 is not None:
            t2.cancel()  # physically stop the real timer; attempt it on demand
        return gen2

    def test_cancel_before_fire_transition_suppresses_publication(self):
        """F. Park _fire at entry -> cancel(root) -> release -> no publication."""
        recorder: list[dict] = []
        gate = threading.Event()
        bus = self._blocking_bus(recorder, gate)
        notifier = self._notifier(bus)
        root = "/r/suppress"
        entered = threading.Event()
        original_fire = notifier._fire

        def gated_fire(r, gen):
            entered.set()
            gate.wait()
            original_fire(r, gen)

        notifier._fire = gated_fire
        try:
            notifier.touch(root)
            # Confirm the fire thread is parked at entry BEFORE cancelling,
            # so the cancel provably lands while the fire cannot transition.
            assert entered.wait(timeout=2), "fire never reached the gate"
            notifier.cancel(root)
            gate.set()
            assert _wait_for(lambda: self._drained(notifier, root))
            assert root not in notifier._roots, "cancelled root left residue"
            assert recorder == [], "publication escaped a canceled root"
        finally:
            notifier._fire = original_fire
            gate.set()

    def test_cancel_waits_for_in_flight_publication(self):
        """G. Publication genuinely started before cancellation: cancel waits
        for that SAME root's running publication; it completes before cancel
        returns; no later publication escapes."""
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus)
        root = "/r/inflight"
        notifier.touch(root)
        assert _wait_for(lambda: self._has_publisher(notifier, root)), (
            "fire never reached in-flight"
        )
        done = threading.Thread(target=lambda: notifier.cancel(root))
        done.start()
        try:
            done.join(timeout=0.3)
            assert done.is_alive(), (
                "cancel returned while the in-flight fire was still publishing"
            )
            release.set()
            done.join(timeout=5)
            assert not done.is_alive(), "cancel never drained the in-flight fire"
            assert len(recorder) == 1, recorder
            assert _wait_for(lambda: root not in notifier._roots)
        finally:
            release.set()
            done.join(timeout=5)

    def test_root_specific_cancel_is_isolated(self):
        """A. B blocked in-flight; cancel(A) returns without waiting for B;
        B stays legitimate and publishes exactly its own notice."""
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus)
        root_a, root_b = "/r/iso-a", "/r/iso-b"
        notifier.touch(root_b)
        assert _wait_for(lambda: self._has_publisher(notifier, root_b)), (
            "B never reached in-flight"
        )
        # cancel(A) while B is publishing: must return promptly without B.
        t0 = time.monotonic()
        notifier.cancel(root_a)
        assert time.monotonic() - t0 < 1.0, "cancel(A) waited for unrelated B"
        assert self._has_publisher(notifier, root_b), "cancel(A) disturbed B"
        assert root_a not in notifier._roots, "no-op cancel allocated state"
        # Releasing B permits exactly its expected publication.
        release.set()
        assert _wait_for(lambda: len(recorder) == 1)
        assert [d["root"] for d in recorder] == [root_b]
        assert _wait_for(lambda: root_b not in notifier._roots)

    def test_cross_root_reentrant_callback_no_deadlock(self):
        """B. The original deadlock: B is the ONLY in-flight root; B's
        subscriber synchronously calls cancel(A) for an UNTOUCHED root A.
        A root-scoped cancel must not union B, so it returns immediately,
        the callback completes, B drains, and A keeps no pending/in-flight
        state. On the old global-target cancel this hung forever."""
        recorder: list[dict] = []
        cancelled_a = threading.Event()
        notifier = None
        root_a, root_b = "/r/re-a", "/r/re-b"

        class _ReentrantBus:
            def has_subscribers(self, event_type):
                return event_type == "agent.output_available"

            def publish(self, event_type, data=None):
                if data.get("root") == root_b and notifier is not None:
                    # root A was never touched; only B is globally in-flight.
                    notifier.cancel(root_a)
                    cancelled_a.set()
                recorder.append(data)

        notifier = self._notifier(_ReentrantBus(), interval=0.05)
        notifier.touch(root_b)
        # If cancel(root_a) wrongly waited on B, this never resolves.
        assert cancelled_a.wait(timeout=5), "cross-root cancel(A) deadlocked on B"
        assert _wait_for(lambda: len(recorder) == 1), "B never published"
        assert recorder[0]["root"] == root_b
        assert _wait_for(lambda: self._drained(notifier, root_b))
        assert root_b not in notifier._roots, "B residue"
        assert root_a not in notifier._roots, "cancel(A) allocated A state"

    def test_same_root_reentrant_cancel_no_self_deadlock(self):
        """Same-root rule: a callback reached synchronously from R's own
        publication may cancel(R) without self-deadlock; the running
        publication is the caller's own frame and completes normally."""
        recorder: list[dict] = []
        notifier = None

        class _SelfCancelBus:
            def has_subscribers(self, event_type):
                return event_type == "agent.output_available"

            def publish(self, event_type, data=None):
                notifier.cancel(data["root"])
                recorder.append(data)

        notifier = self._notifier(_SelfCancelBus())
        root = "/r/self"
        notifier.touch(root)
        assert _wait_for(lambda: len(recorder) == 1), "publication never ran"
        assert recorder[0]["root"] == root
        assert _wait_for(lambda: root not in notifier._roots)

    def test_pending_next_cycle_suppressed_while_cancel_waits(self):
        """PERF-001 barrier race: a next coalesced Timer scheduled while an
        older publication is in-flight must NOT be able to transition to a
        second publisher behind cancel()'s back.

        Deterministic (interval=30.0, transitions invoked manually): the
        pending cycle's _fire is invoked directly while cancel() is provably
        still waiting for the older publication -- modelling the interleaving
        where that Timer callback already passed Timer.cancel() and is racing
        for the mutex.
        """
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus, interval=30.0)
        root = "/r/pending-next"

        # Cycle 1: arm, physically stop the timer, transition on demand.
        notifier.touch(root)
        gen1 = self._pending_gen(notifier, root)
        pub1 = threading.Thread(target=notifier._fire, args=(root, gen1))
        pub1.daemon = True
        pub1.start()
        assert _wait_for(lambda: self._has_publisher(notifier, root)), (
            "publication 1 never reached in-flight"
        )
        # Schedule the next cycle while publication 1 is still publishing.
        notifier.touch(root)
        assert self._has_timer(notifier, root), "cycle 2 never armed"
        gen2 = self._pending_gen(notifier, root)

        cancel_thread = threading.Thread(target=lambda: notifier.cancel(root))
        cancel_thread.daemon = True
        late: threading.Thread | None = None
        try:
            cancel_thread.start()
            # Barrier (pending gen invalidated, Timer detached) must be up
            # BEFORE cancel releases the mutex to wait for older publisher.
            assert _wait_for(lambda: self._barriered(notifier, root)), (
                "cancel did not invalidate the pending generation under the lock"
            )
            # The cancelled cycle's callback attempts the transition NOW, while
            # cancel still waits for publication 1 (release not set).
            late = threading.Thread(target=notifier._fire, args=(root, gen2))
            late.daemon = True
            late.start()
            late.join(timeout=2)
            assert not late.is_alive(), "cancelled-cycle _fire hung (no barrier)"
            assert len(recorder) == 0, recorder
            # cancel did NOT return while publication 1 was still in-flight.
            assert cancel_thread.is_alive(), (
                "cancel returned before the older in-flight publication drained"
            )
        finally:
            # Always release so a barrier-less (red) build drains its escaped
            # publisher instead of hanging the process on non-daemon threads.
            release.set()
            pub1.join(timeout=5)
            cancel_thread.join(timeout=5)
            if late is not None:
                late.join(timeout=5)

        assert not cancel_thread.is_alive(), "cancel never drained publication 1"
        assert len(recorder) == 1, recorder
        assert _wait_for(lambda: root not in notifier._roots), (
            "state not reclaimed after the barrier drained"
        )
        # A later fresh touch starts an independent valid lifecycle.
        notifier.touch(root)
        gen3 = self._pending_gen(notifier, root)
        notifier._fire(root, gen3)
        assert _wait_for(lambda: len(recorder) == 2), (
            "fresh lifecycle after barrier did not publish"
        )
        assert _wait_for(lambda: root not in notifier._roots)

    def test_same_root_reentrant_suppresses_pending_next_cycle(self):
        """Same-root re-entrancy under the barrier: publication 1's own
        (synchronous) subscriber touch(R)+cancel(R) must not self-deadlock AND
        must suppress a second pending cycle for the same root. The caller's
        own in-flight frame is excluded from the wait; everything else from
        the cancelled lifecycle is fenced by the invalidated generation.
        """
        recorder: list[dict] = []
        notifier = None
        state: dict = {}
        root = "/r/self-pending"

        class _ReentrantSelfCancelBus:
            def has_subscribers(self, event_type):
                return event_type == "agent.output_available"

            def publish(self, event_type, data=None):
                # Runs on the publishing thread -- a same-root re-entry.
                if not state.get("armed"):
                    state["armed"] = True
                    # touch(R) from inside R's own publication: schedules the
                    # second pending Timer for the same root.
                    notifier.touch(root)
                    state["gen2"] = self_ref._pending_gen(notifier, root)
                    # Same-root cancel: must exclude this frame (no deadlock)
                    # yet barrier the pending cycle 2 it just armed.
                    notifier.cancel(root)
                    # Race cycle 2's callback while THIS frame is still the
                    # only publisher. With the barrier it is suppressed; on a
                    # barrier-less implementation it would publish here.
                    notifier._fire(root, state["gen2"])
                recorder.append(data)

        self_ref = self
        notifier = self._notifier(_ReentrantSelfCancelBus(), interval=30.0)
        notifier.touch(root)
        gen1 = self._pending_gen(notifier, root)
        pub1 = threading.Thread(target=notifier._fire, args=(root, gen1))
        pub1.start()
        pub1.join(timeout=5)
        assert not pub1.is_alive(), "same-root reentrant cancel self-deadlocked"
        assert len(recorder) == 1, recorder
        # State drained completely once the caller's frame finished.
        assert _wait_for(lambda: root not in notifier._roots), "same-root residue"
        # Fresh later touch still works.
        recorder.clear()
        notifier.touch(root)
        gen3 = self._pending_gen(notifier, root)
        notifier._fire(root, gen3)
        assert _wait_for(lambda: len(recorder) == 1), (
            "fresh lifecycle after cancel died"
        )
        assert _wait_for(lambda: root not in notifier._roots)

    def test_mutual_cross_root_cancel_no_publisher_wait_cycle(self):
        """T-842 A: mutual cross-root re-entrant cancellation must not form a
        publisher-to-publisher wait cycle.

        A and B are BOTH actively publishing; A's subscriber cancels B and
        B's subscriber cancels A. A cancel() that synchronously waits for the
        other root's publisher deadlocks here forever. The repaired contract:
        re-entrant cancellation (arriving inside a notifier publication)
        invalidates/barriers the target lifecycle without synchronously
        waiting for any other publisher. External cancel() retains strong
        blocking drain semantics (covered by tests G/E above).
        """
        recorder: list[dict] = []
        notifier = None
        root_a, root_b = "/r/mutual-a", "/r/mutual-b"
        entered_a = threading.Event()
        entered_b = threading.Event()
        release_a = threading.Event()
        release_b = threading.Event()

        class _MutualCancelBus:
            def has_subscribers(self, event_type):
                return event_type == "agent.output_available"

            def publish(self, event_type, data=None):
                root = data["root"]
                if root == root_a:
                    entered_a.set()
                    release_a.wait(timeout=10)
                    # A's callback re-entrantly cancels B's lifecycle.
                    if notifier is not None:
                        notifier.cancel(root_b)
                    recorder.append(data)
                else:
                    entered_b.set()
                    release_b.wait(timeout=10)
                    # B's callback re-entrantly cancels A's lifecycle.
                    if notifier is not None:
                        notifier.cancel(root_a)
                    recorder.append(data)

        notifier = self._notifier(_MutualCancelBus(), interval=30.0)
        notifier.touch(root_a)
        notifier.touch(root_b)
        gen_a = self._pending_gen(notifier, root_a)
        gen_b = self._pending_gen(notifier, root_b)
        pub_a = threading.Thread(target=notifier._fire, args=(root_a, gen_a))
        pub_b = threading.Thread(target=notifier._fire, args=(root_b, gen_b))
        pub_a.daemon = True
        pub_b.daemon = True
        pub_a.start()
        pub_b.start()
        try:
            assert entered_a.wait(timeout=5), "A never reached publication"
            assert entered_b.wait(timeout=5), "B never reached publication"
            # Both publishers are parked in their callbacks; releasing either
            # lets its callback re-entrantly cancel the OTHER root. On the
            # pre-fix implementation cancel(A) inside B's callback waits for
            # A's publisher and cancel(B) inside A's callback waits for B's
            # -- a mutual wait cycle; both threads never reach recorder.
            release_a.set()
            release_b.set()
            pub_a.join(timeout=10)
            pub_b.join(timeout=10)
            assert not pub_a.is_alive(), "A deadlocked in mutual cross-root cancel"
            assert not pub_b.is_alive(), "B deadlocked in mutual cross-root cancel"
            assert len(recorder) == 2, recorder
            assert _wait_for(lambda: root_a not in notifier._roots), "A residue"
            assert _wait_for(lambda: root_b not in notifier._roots), "B residue"
            assert notifier._roots == {}, "cancellation/root-state residue"
        finally:
            release_a.set()
            release_b.set()
            pub_a.join(timeout=5)
            pub_b.join(timeout=5)

    def test_touch_inside_active_cancel_does_not_rearm(self):
        """T-842 B: a touch arriving while an external cancel(R) is actively
        draining R's in-flight publication must not silently arm another
        notification from the cancelled lifecycle.

        Deterministic: external cancel(R) is provably inside its drain wait
        (it cannot return while the publisher is parked) when touch(R) runs;
        the blocked touch must leave no Timer, and after the drain completes
        no publication from the cancelled lifecycle may occur. A genuinely
        later fresh touch still publishes normally.
        """
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus, interval=30.0)
        root = "/r/cancel-vs-touch"
        notifier.touch(root)
        gen1 = self._pending_gen(notifier, root)
        pub = threading.Thread(target=notifier._fire, args=(root, gen1))
        pub.daemon = True
        pub.start()
        assert _wait_for(lambda: self._has_publisher(notifier, root)), (
            "R never reached in-flight"
        )

        cancel_thread = threading.Thread(target=lambda: notifier.cancel(root))
        cancel_thread.daemon = True
        cancel_thread.start()
        try:
            # Prove cancellation is actively draining: it cannot return while
            # the publisher is still parked inside publish().
            cancel_thread.join(timeout=0.3)
            assert cancel_thread.is_alive(), "cancel returned before drain"
            # touch(R) arrives inside the active cancellation barrier.
            notifier.touch(root)
            with notifier._cond:
                st = notifier._roots.get(root)
                assert st is None or st.timer is None, (
                    "touch re-armed a Timer inside the cancellation barrier"
                )
            # Release the original publisher; cancel must now return.
            release.set()
            cancel_thread.join(timeout=5)
            assert not cancel_thread.is_alive(), "cancel never drained"
            # Prove no publication from the cancelled lifecycle afterward.
            time.sleep(OUTPUT_NOTIFY_INTERVAL_SECONDS * 2)
            assert len(recorder) == 1, recorder
            assert _wait_for(lambda: root not in notifier._roots), "state residue"
        finally:
            release.set()
            cancel_thread.join(timeout=5)
            pub.join(timeout=5)

        # A genuinely later fresh touch must work normally.
        notifier.touch(root)
        assert _wait_for(lambda: self._has_timer(notifier, root)), (
            "fresh touch after cancellation never armed"
        )
        gen = self._pending_gen(notifier, root)
        notifier._fire(root, gen)
        assert _wait_for(lambda: len(recorder) == 2), (
            "fresh lifecycle after cancellation did not publish"
        )
        assert _wait_for(lambda: root not in notifier._roots)

    def test_noop_cancel_retains_no_state(self):
        """C. Hundreds of unique idle-root cancels: bounded state, no
        tombstones accumulate."""
        notifier = self._notifier(EventBus())
        for i in range(1000):
            notifier.cancel(f"/never/{i}")
        assert notifier._roots == {}, "idle-root cancels allocated state"

    def test_cancelled_pending_roots_are_reclaimed(self):
        """D. Pending notifications cancelled before firing: timers gone,
        in-flight gone, cancellation metadata gone."""
        bus = EventBus()
        bus.subscribe("agent.output_available", lambda data: None)
        notifier = self._notifier(bus, interval=30.0)
        roots = [f"/r/pend/{i}" for i in range(20)]
        for r in roots:
            notifier.touch(r)
        assert len(notifier._roots) == len(roots)
        for r in roots:
            notifier.cancel(r)
        assert notifier._roots == {}, "cancelled pending roots left residue"

    def test_cancel_all_drains_pending_and_in_flight(self):
        """E. cancel(None): mixed pending + in-flight roots all drain; no
        Timer objects, no in-flight state, no stale metadata remain."""
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus)
        inflight_root = "/r/all-a"
        pending_root = "/r/all-b"
        baseline_threads = threading.active_count()
        notifier.touch(inflight_root)
        assert _wait_for(lambda: self._has_publisher(notifier, inflight_root))
        notifier.touch(pending_root)
        assert self._has_timer(notifier, pending_root)

        done = threading.Thread(target=lambda: notifier.cancel())
        done.start()
        try:
            done.join(timeout=0.3)
            assert done.is_alive(), "cancel-all returned with a fire in-flight"
            release.set()
            done.join(timeout=5)
            assert not done.is_alive()
            assert notifier._roots == {}, "cancel-all left per-root residue"
            assert _wait_for(
                lambda: threading.active_count() <= baseline_threads + 1
            ), "leaked Timer thread"
        finally:
            release.set()
            done.join(timeout=5)

    def test_fresh_touch_after_cancel_publishes_again(self):
        """H. Fresh lifecycle: after cancel + full drain, a later touch(root)
        starts a clean cycle and delivers exactly one legitimate notice; no
        stale cancellation state suppresses it."""
        recorder: list[dict] = []
        release = threading.Event()
        bus = self._blocking_bus(recorder, release)
        notifier = self._notifier(bus)
        root = "/r/relaunch"
        notifier.touch(root)
        assert _wait_for(lambda: self._has_publisher(notifier, root))
        release.set()
        assert _wait_for(lambda: len(recorder) == 1)
        assert _wait_for(lambda: root not in notifier._roots)
        notifier.cancel(root)
        notifier.touch(root)
        assert _wait_for(lambda: len(recorder) == 2), (
            "stale cancel state suppressed the fresh notification cycle"
        )
        release.set()
        assert _wait_for(lambda: root not in notifier._roots)

    def test_cancel_drops_the_pending_notification(self, tmp_path):
        """I. Coalescing: repeated touch(root) inside one interval owns at
        most one pending Timer; cancel drops it silently."""
        bus = EventBus()
        seen: list[dict] = []
        bus.subscribe("agent.output_available", seen.append)
        notifier = type(ProcessManager()._output_notifier)(bus=bus, interval=30.0)
        root = str(tmp_path)
        notifier.touch(root)
        notifier.touch(root)  # second touch within window is a no-op
        assert self._has_timer(notifier, root)
        assert len([r for r in notifier._roots]) == 1
        notifier.cancel(root)
        assert notifier._roots == {}
        time.sleep(OUTPUT_NOTIFY_INTERVAL_SECONDS * 2)
        assert seen == []


class TestFrontendWiring:
    """Source-shape guards: the fast loop exists, is guarded, and the slow
    registry poll no longer drives the output panel (test_frontend_ordering
    precedent -- there is no JS test runner, `node --check` is the gate)."""

    def _function_body(self, src: str, name: str) -> str:
        start = src.index(f"function {name}")
        brace = src.index("{", start)
        depth = 0
        i = brace
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    return src[start : i + 1]
            i += 1
        raise AssertionError(f"function {name} never closes")

    def test_slow_poll_drives_only_the_badge(self):
        body = self._function_body(APP_JS.read_text(encoding="utf-8"), "poll")
        assert "pollAgentsBadge()" in body
        assert "pollAgentOutput()" not in body

    def test_fast_ticker_is_guarded_and_self_scheduling(self):
        src = APP_JS.read_text(encoding="utf-8")
        body = self._function_body(src, "_outputPollTick")
        assert "!windowVisible || !showAgentPanel || !currentDetailRoot" in body
        assert 'st.status === "running"' in body
        assert "setTimeout(_outputPollTick, OUTPUT_POLL_MS)" in body
        # The delta path keeps W2-006's single-flight guard.
        delta = self._function_body(src, "_fetchAgentOutputDelta")
        assert "_outputPollInFlight[root]" in delta

    def test_delta_fetch_is_single_flight_per_root(self):
        src = APP_JS.read_text(encoding="utf-8")
        body = self._function_body(src, "_fetchAgentOutputDelta")
        early = body.index("if (_outputPollInFlight[root]) return;")
        set_pos = body.index("_outputPollInFlight[root] = true;", early)
        assert early < set_pos
