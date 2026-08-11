"""T-166: agent process lifecycle races.

Three classes of defect this locks down:

1. launch() checked "is there a running process" under the lock, RELEASED the
   lock, ran Popen, and only then recorded the process -- two concurrent
   launches of the same project could both pass the check and spawn twice.
2. kill() and the reader thread's EOF tail both wrote finished state and both
   published `agent.finished`; the transcript was finished once, but the
   event fired twice.
3. get_output() arithmetic (`since + len(lines)`) loses the rollover boundary
   and resends already-seen lines; the cursor must come from the backend's
   canonical `next_since`.
"""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import patch

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.events import event_bus
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _EchoEngine(AgentEngine):
    def __init__(self, script: str | None = None, name: str = "echo-test") -> None:
        self._script = script or "print('line 0', flush=True)\n"
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return "Echo Test"

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


class TestConcurrentLaunch:
    def test_two_concurrent_launches_yield_one_process(self, manager, tmp_path):
        root = str(tmp_path)
        block = threading.Event()
        real_popen = sys.modules["subprocess"].Popen

        def slow_popen(*a, **kw):
            if not block.is_set():
                block.wait(timeout=10)
            return real_popen(*a, **kw)

        results = {}

        def do_launch():
            results["first"] = manager.launch(_EchoEngine(), root, "go")

        with patch("saipenview.runtime.subprocess.Popen", side_effect=slow_popen):
            t = threading.Thread(target=do_launch)
            t.start()
            assert _wait_for(
                lambda: manager.ownership.agent_owns(tmp_path) or "first" in results
            ), "first launch never took the reservation"
            second = manager.launch(_EchoEngine(), root, "go2")
            assert second["ok"] is False
            assert (
                "running" in second["error"].lower()
                or "already" in second["error"].lower()
            )
            block.set()
            t.join(timeout=10)
            if t.is_alive():
                block.set()

        assert results["first"]["ok"] is True
        assert len(manager.list_running()) == 1, "the project has more than one process"

    def test_case_variant_alias_cannot_launch_again(self, manager, tmp_path):
        root = str(tmp_path)
        engine = _EchoEngine(script="import time\nwhile True:\n    time.sleep(0.2)\n")
        manager.launch(engine, root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "running")

        alias = root.upper()
        res = manager.launch(_EchoEngine(), alias, "go2")
        assert res["ok"] is False
        assert "already" in res["error"].lower()
        assert len(manager.list_running()) == 1


class TestExactlyOnceFinish:
    def test_agent_finished_published_exactly_once(self, manager, tmp_path):
        root = str(tmp_path)
        counts = {"finished": 0}

        def on_finished(_data):
            counts["finished"] += 1

        event_bus.subscribe("agent.finished", on_finished)
        try:
            engine = _EchoEngine(
                script="import time\nwhile True:\n    time.sleep(0.2)\n"
            )
            manager.launch(engine, root, "go")
            assert _wait_for(lambda: manager.get_status(root)["status"] == "running")

            manager.kill(root)
            assert _wait_for(lambda: manager.get_status(root)["status"] == "killed")
            # Give the reader thread's EOF tail its chance to double-fire.
            time.sleep(0.6)
        finally:
            event_bus.unsubscribe("agent.finished", on_finished)

        assert counts["finished"] == 1, (
            f"agent.finished fired {counts['finished']} times -- kill() and the "
            "reader tail both published it"
        )
        assert manager.sessions.history(root)[0]["status"] == "killed"

    def test_transcript_finished_once(self, manager, tmp_path):
        root = str(tmp_path)
        manager.launch(_EchoEngine(), root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
        rec = manager.sessions.history(root)[0]
        assert rec["status"] == "done"


class TestOutputRollover:
    def test_buffer_3_of_10_lines_no_repeat_canonical_cursor(self, tmp_path):
        pm = ProcessManager(buffer_size=3)
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                script="for i in range(10):\n    print('l%d' % i, flush=True)\n"
            )
            pm.launch(engine, root, "go")
            assert _wait_for(lambda: pm.get_status(root)["status"] == "done")

            res = pm.get_output(root, since_line=0)
            assert res["lines"] == ["l7", "l8", "l9"], res["lines"]
            assert res["total"] == 10
            assert res["first_available"] == 7
            assert res["dropped_count"] == 7
            assert res["next_since"] == 10

            # A second poll with the canonical cursor repeats nothing.
            res2 = pm.get_output(root, since_line=res["next_since"])
            assert res2["lines"] == []
            assert res2["next_since"] == 10
        finally:
            pm.stop_all()

    def test_no_repeat_when_polling_through_a_live_run(self, tmp_path):
        pm = ProcessManager(buffer_size=5)
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                script=(
                    "import time\n"
                    "for i in range(3):\n"
                    "    print('l%d' % i, flush=True)\n"
                    "    time.sleep(0.15)\n"
                )
            )
            pm.launch(engine, root, "go")
            cursor = 0
            seen = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                res = pm.get_output(root, since_line=cursor)
                seen.extend(res["lines"])
                cursor = res["next_since"]
                if pm.get_status(root)["status"] == "done":
                    break
                time.sleep(0.1)
            assert seen == ["l0", "l1", "l2"], seen
        finally:
            pm.stop_all()
