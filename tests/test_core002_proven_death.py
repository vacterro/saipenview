"""T-7 / CORE-002: _finalize must not commit terminal state before proven death."""
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


class DummyProcess:
    """Stubs subprocess.Popen API for lifecycle testing."""

    def __init__(self, returncode=None, delay: float = 0.0, stay_alive=False):
        self.returncode = returncode
        self.delay = delay
        self.stay_alive = stay_alive  # if True, ignore terminate()/kill()
        self.pid = 12345

    def wait(self, timeout=None):
        if self.delay > 0:
            time.sleep(self.delay)
        if self.returncode is None:
            raise subprocess.TimeoutExpired("proc", timeout or 0)

    def poll(self):
        return self.returncode

    def kill(self):
        if not self.stay_alive:
            self.returncode = -9

    def terminate(self):
        self.kill()


class DummyAgent:
    def __init__(self):
        self.process = DummyProcess(returncode=0, delay=0.0)
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
        self._reader_thread = None
        self.status = "running"

    def elapsed_seconds(self):
        return 0.0


def test_finalize_blocks_terminal_when_returncode_none():
    """_finalize must NOT publish session, event, or release ownership
    when process death is unproven (returncode None). _finalized may be
    set to prevent double-finalize, but no terminal state is committed."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    ap.process.returncode = None  # never resolved
    ap.process.delay = 10.0  # wait() will block

    with patch.object(registry, "ownership") as mock_ownership, \
         patch.object(registry, "sessions") as mock_sessions, \
         patch("saipenview.runtime.event_bus") as mock_bus, \
         patch("saipenview.runtime._schedule_reaper") as mock_reaper:

        registry._finalize(ap)

        # No session finish, no event publish, no ownership release.
        mock_sessions.finish.assert_not_called()
        mock_bus.publish.assert_not_called()
        mock_ownership.release_agent.assert_not_called()
        # A reaper was scheduled to wait for proven death.
        mock_reaper.assert_called_once_with(registry, ap, "failed")
        # _finalized may be True (bail-out guard), but terminal state is not committed.
        assert mock_sessions.finish.call_count == 0
        assert mock_bus.publish.call_count == 0
        assert mock_ownership.release_agent.call_count == 0


def test_finalize_commits_after_proven_death():
    """Once poll/wait yields a non-None returncode, terminal state is committed."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
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


def test_kill_sets_intent_no_terminal_without_death():
    """kill() records intent and sends signal; if process won't die,
    no terminal state is committed (session, event, ownership)."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    # Register the process so kill() can find it.
    registry._processes[registry._key(ap.project_root)] = ap
    # Process refuses to exit even after terminate(): stay_alive=True keeps
    # returncode as None, simulating an unkillable process.
    ap.process = DummyProcess(returncode=None, delay=10.0, stay_alive=True)

    with patch("saipenview.runtime._schedule_reaper") as mock_reaper, \
         patch.object(registry, "ownership") as mock_ownership, \
         patch.object(registry, "sessions") as mock_sessions, \
         patch("saipenview.runtime.event_bus") as mock_bus:

        result = registry.kill(ap.project_root)

    # kill() returns ok because it sent the signal; death proof is deferred.
    assert result == {"ok": True}
    # Intent recorded.
    assert ap._kill_intent is True
    # But no terminal state is committed -- death is unproven.
    assert mock_sessions.finish.call_count == 0
    assert mock_bus.publish.call_count == 0
    assert mock_ownership.release_agent.call_count == 0
    # A reaper was scheduled to wait for proven death.
    mock_reaper.assert_called_once()
