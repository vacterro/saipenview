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
        assert notifier._timers == {}


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
        -- the terminal event owns the refresh instead."""
        from saipenview.events import event_bus

        notices: list[dict] = []
        event_bus.subscribe("agent.output_available", notices.append)
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                "for i in range(200):\n    print('l%d' % i, flush=True)\n"
            )
            manager.launch(engine, root, "go")
            assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
            time.sleep(OUTPUT_NOTIFY_INTERVAL_SECONDS * 3)
            assert notices == []
            # ...and the data is not lost: the cursor API answers for it all.
            out = manager.get_output(root)
            assert out["total"] == 200
        finally:
            event_bus.unsubscribe("agent.output_available", notices.append)

    def test_cancel_drops_the_pending_notification(self, tmp_path):
        bus = EventBus()
        seen: list[dict] = []
        bus.subscribe("agent.output_available", seen.append)
        notifier = type(ProcessManager()._output_notifier)(bus=bus)
        notifier.touch(str(tmp_path))
        notifier.touch(str(tmp_path))  # second touch within window is a no-op
        assert len(notifier._timers) == 1
        notifier.cancel(str(tmp_path))
        assert notifier._timers == {}
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
