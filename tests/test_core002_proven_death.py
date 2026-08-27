"""T-7 / CORE-002: _finalize must not commit terminal state before proven death."""
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class FakeProcess:
    """Delivers returncode on first poll after a configurable delay."""

    def __init__(self, returncode: int | None = 0, delay: float = 0.0):
        self.returncode = returncode
        self.delay = delay
        self._waited = False

    def wait(self, timeout: float | None = None) -> None:
        self._waited = True
        if self.delay > 0:
            time.sleep(self.delay)
        if not isinstance(self.returncode, int):
            # Never resolved -- re-raise as if still running
            raise subprocess.TimeoutExpired("proc", timeout or 0)

    def kill(self) -> None:
        self.returncode = -9


class DummyAgent:
    def __init__(self):
        self.process = FakeProcess(returncode=0, delay=0.0)
        self.project_root = "/fake/root"
        self.engine = MagicMock()
        self.engine.name = "test"
        self._io_lock = threading.Lock()
        self._finalize_lock = threading.Lock()
        self._finalized = False
        self._kill_intent = False
        self.run_id = "run-1"
        self.exit_code = None
        self.finished_at = None
        self._psutil_proc = None

    def elapsed_seconds(self) -> float:
        return 0.0


def test_finalize_blocks_when_returncode_none():
    """_finalize must NOT flip _finalized nor publish when process is still alive."""
    from saipenview.runtime import AgentRegistry, AgentProcess

    registry = AgentRegistry()
    ap = DummyAgent()
    ap.process.returncode = None  # never resolved
    ap.process.delay = 10.0  # wait() will block

    with patch.object(registry, "ownership") as mock_ownership, \
         patch.object(registry, "sessions") as mock_sessions, \
         patch("saipenview.runtime.event_bus") as mock_bus, \
         patch("saipenview.runtime.threading") as mock_threading:

        # Spawn the reaper path by feeding a returncode=None into _finalize.
        # _finalize internally calls process.wait(timeout=5); with delay=10 that
        # raises TimeoutExpired, leaving returncode=None.
        registry._finalize(ap)

        # _finalized must remain False: no commit happened.
        assert ap._finalized is False
        # No session finish, no event publish, no ownership release.
        mock_sessions.finish.assert_not_called()
        mock_bus.publish.assert_not_called()
        mock_ownership.release_agent.assert_not_called()
        # A reaper thread must have been scheduled.
        mock_threading.Thread.assert_called_once()


def test_finalize_commits_after_proven_death():
    """Once poll/wait yields a non-None returncode, terminal state is committed."""
    from saipenview.runtime import AgentRegistry

    registry = AgentRegistry()
    ap = DummyAgent()
    ap.process.returncode = 0  # already dead

    with patch.object(registry, "ownership") as mock_ownership, \
         patch.object(registry, "sessions") as mock_sessions, \
         patch("saipenview.runtime.event_bus") as mock_bus:
        registry._finalize(ap)

        assert ap._finalized is True
        assert ap.status == "done"
        assert ap.exit_code == 0
        assert ap.finished_at is not None
        mock_sessions.finish.assert_called_once_with("run-1", "done", 0)
        mock_bus.publish.assert_called_once_with(
            "agent.finished",
            {
                "root": ap.project_root,
                "engine": ap.engine.name,
                "status": "done",
                "exit_code": 0,
                "elapsed": 0.0,
            },
        )
        mock_ownership.release_agent.assert_called_once()


def test_kill_sets_intent_before_signal_no_finalize_without_death():
    """kill() records intent and sends signal; if process won't die, finalize
    must still not commit terminal state or publish agent.finished."""
    from saipenview.runtime import AgentRegistry

    registry = AgentRegistry()
    ap = DummyAgent()
    # Process refuses to exit: returncode stays None even after kill()
    ap.process.returncode = None
    ap.process.delay = 10.0

    result = registry.kill(ap.project_root)

    # kill() returns ok because it sent the signal; death proof is deferred.
    assert result == {"ok": True}
    # Intent recorded.
    assert ap._kill_intent is True
    # But finalize did NOT commit -- returncode is still None.
    assert ap._finalized is False
    assert ap.status != "killed"  # status not yet updated to terminal
    assert ap.finished_at is None
