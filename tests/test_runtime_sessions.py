"""ProcessManager must actually write the transcript, not merely own a store.

These drive a real subprocess (this interpreter, printing known lines) through
the real launch/read/finish path, because the wiring between the reader thread
and the session store is exactly the part a unit test of either half misses.
"""

from __future__ import annotations

import sys
import time

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _EchoEngine(AgentEngine):
    """Prints three lines and exits 0. No agent CLI needed."""

    def __init__(self, script: str | None = None, name: str = "echo-test") -> None:
        self._script = script or (
            "import sys\n"
            "for i in range(3):\n"
            "    print('line %d' % i, flush=True)\n"
        )
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


class TestTranscriptIsWritten:
    def test_a_completed_run_is_on_disk(self, manager, tmp_path):
        root = str(tmp_path)
        assert manager.launch(_EchoEngine(), root, "saipen continue")["ok"] is True
        assert _wait_for(lambda: manager.get_status(root)["status"] == "done")

        hist = manager.sessions.history(root)
        assert len(hist) == 1
        assert hist[0]["status"] == "done"
        assert hist[0]["exit_code"] == 0
        assert hist[0]["engine"] == "echo-test"
        assert hist[0]["instruction"] == "saipen continue"

        body = manager.sessions.transcript(hist[0]["run_id"])
        assert body["lines"] == ["line 0", "line 1", "line 2"]

    def test_a_fresh_store_still_finds_it(self, manager, tmp_path):
        # What a restarted SAIPENVIEW sees.
        root = str(tmp_path)
        manager.launch(_EchoEngine(), root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "done")

        reopened = SessionStore(base_dir=tmp_path / "sessions")
        last = reopened.last_run(root)
        assert last is not None
        assert reopened.transcript(last["run_id"])["lines"][-1] == "line 2"

    def test_a_failing_run_is_recorded_as_failed(self, manager, tmp_path):
        root = str(tmp_path)
        engine = _EchoEngine(script="import sys; print('bad', flush=True); sys.exit(3)")
        manager.launch(engine, root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "failed")

        rec = manager.sessions.history(root)[0]
        assert rec["status"] == "failed"
        assert rec["exit_code"] == 3


class TestKillIsNotAFailure:
    def test_killing_an_agent_reports_killed_not_failed(self, manager, tmp_path):
        # terminate() makes stdout hit EOF, so the reader thread wakes up right
        # after kill() recorded "killed" -- and a terminated process exits
        # non-zero, so the old unconditional assignment relabelled every
        # deliberate stop as "failed", i.e. as a crash.
        root = str(tmp_path)
        engine = _EchoEngine(script="import time\nwhile True:\n    time.sleep(0.2)\n")
        manager.launch(engine, root, "go")
        assert _wait_for(lambda: manager.get_status(root)["status"] == "running")

        assert manager.kill(root)["ok"] is True
        assert _wait_for(lambda: manager.get_status(root)["status"] == "killed")
        # Give the reader thread its chance to overwrite the status.
        time.sleep(0.5)
        assert manager.get_status(root)["status"] == "killed"
        assert manager.sessions.history(root)[0]["status"] == "killed"


class TestBufferOverflow:
    def test_the_disk_keeps_what_the_rolling_window_drops(self, tmp_path):
        # The in-memory deque is a window; the transcript is the record. With a
        # 10-line window and 200 lines of output, the window can only answer
        # for the tail -- the file has to answer for all of it.
        pm = ProcessManager(buffer_size=10)
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        try:
            root = str(tmp_path)
            engine = _EchoEngine(
                script="for i in range(200):\n    print('l%d' % i, flush=True)\n"
            )
            pm.launch(engine, root, "go")
            assert _wait_for(lambda: pm.get_status(root)["status"] == "done")

            assert pm.get_output(root)["total"] == 200
            rec = pm.sessions.history(root)[0]
            assert rec["line_count"] == 200
            body = pm.sessions.transcript(rec["run_id"])
            assert body["total"] == 200
            assert body["lines"][0] == "l0"
            assert body["lines"][-1] == "l199"
        finally:
            pm.stop_all()
