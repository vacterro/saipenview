"""T-7 / CORE-002: _finalize must not commit terminal state before proven death."""

import collections
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
        # W2-004: transcript-deferral fields used by the new _finalize path.
        self._transcript_lock = threading.Lock()
        self._transcript_done = False
        self._transcript_pending = None
        self.output_lines = collections.deque(maxlen=5000)
        # T-834: lifecycle completion primitive. The proc-none defensive
        # finalize branch must NEVER set this; only the real boundary
        # (terminal status + ownership release) may.
        self._lifecycle_complete = threading.Event()

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

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
        patch("saipenview.runtime._schedule_reaper") as mock_reaper,
    ):
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

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
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

    with (
        patch("saipenview.runtime._schedule_reaper") as mock_reaper,
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
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


def test_finalize_concurrent_callers_no_crash_exactly_once():
    """W2-002: two concurrent _finalize callers (kill + exit-monitor paths)
    racing through the guard. Exactly one commit (session finish, ownership
    release, agent.finished publish); the loser uses its captured local
    ``proc`` and never dereferences the cleared ``ap.process`` after the
    winner compacts. A barrier forces both threads past the same pre-commit
    window, so any regression in the stable-proc capture crashes here."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    ap.process = DummyProcess(returncode=0, delay=0.0)
    barrier = threading.Barrier(2)

    errors: list[BaseException] = []

    def caller(requested_status):
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass
        try:
            registry._finalize(ap, requested_status)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
        t_a = threading.Thread(target=caller, args=("killed",))
        t_b = threading.Thread(target=caller, args=(None,))
        t_a.start()
        t_b.start()
        t_a.join(timeout=10)
        t_b.join(timeout=10)

    assert not errors, f"concurrent finalizers raised: {errors}"
    assert ap._finalized is True
    assert ap.process is None
    assert mock_sessions.finish.call_count == 1, (
        f"expected exactly one session finish, got {mock_sessions.finish.call_count}"
    )
    assert mock_ownership.release_agent.call_count == 1, (
        f"expected exactly one ownership release, got {mock_ownership.release_agent.call_count}"
    )
    assert mock_bus.publish.call_count == 1, (
        f"expected exactly one agent.finished publish, got {mock_bus.publish.call_count}"
    )


def test_exit_monitor_after_compact_no_crash():
    """W2-002: _exit_monitor must capture a stable proc reference. If a
    concurrent kill won finalization and compacted ap.process = None before
    the monitor's wait(), the monitor must not dereference the cleared
    field."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    ap.process = DummyProcess(returncode=0, delay=0.0)
    ap.process = None  # compact already happened

    # Should return without exception and without touching ap.process.
    registry._exit_monitor(ap)


def test_kill_after_compact_no_crash():
    """W2-002: kill() must capture a stable proc reference. If the reader
    thread already finalized + compacted ap.process = None before kill()
    runs, kill() must not dereference the cleared field.

    T-834: under the new publication order compaction happens AFTER the
    lifecycle boundary (terminal status + ownership release, which sets
    _lifecycle_complete), so a genuinely "compacted" process means the
    winning finalizer already crossed that boundary -- the lifecycle Event
    is set and kill() returns success without waiting."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    registry._processes[registry._key(ap.project_root)] = ap
    ap.process = None  # compact already happened
    ap._kill_intent = True  # a prior finalizer recorded intent
    ap._lifecycle_complete.set()  # winning finalizer crossed the boundary

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
        result = registry.kill(ap.project_root)

    assert result == {"ok": True}, result
    assert ap._kill_intent is True


def test_proc_none_finalize_does_not_signal_lifecycle():
    """T-834 invariant: _finalize() reaching a detached process (proc is
    None) must mark _finalized defensively but MUST NOT set _lifecycle_complete.
    Process detachment alone is never sufficient evidence that the lifecycle
    boundary (terminal status + ownership release) has completed. The old
    code set the Event here, manufacturing completion while ownership was
    still reserved."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    ap.process = None  # detached, but lifecycle not yet complete
    ap.status = "running"
    ap._lifecycle_complete.clear()

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
        registry._finalize(ap)

    assert ap._finalized is True
    assert ap._lifecycle_complete.is_set() is False
    # No terminal state was fabricated: no session commit, no event publish,
    # ownership stays reserved.
    mock_sessions.finish.assert_not_called()
    mock_bus.publish.assert_not_called()
    mock_ownership.release_agent.assert_not_called()
    assert ap.status == "running"


def test_kill_proc_none_race_pending_while_lifecycle_unset(monkeypatch):
    """T-834 invariant: kill() reaching a detached process (proc is None)
    while the lifecycle Event is still unset and ownership reserved must NOT
    return success. The OLD code returned {"ok": True} here. The NEW kill
    waits on the lifecycle primitive and returns FINALIZATION_PENDING when the
    bounded wait expires, leaving the winning finalizer free to complete."""
    import saipenview.runtime as rt_module

    from saipenview.runtime import ProcessManager

    monkeypatch.setattr(rt_module, "_KILL_LIFECYCLE_WAIT_SECONDS", 0.3)

    registry = ProcessManager()
    ap = DummyAgent()
    registry._processes[registry._key(ap.project_root)] = ap
    ap.process = None  # competing finalizer detached the process
    ap.status = "running"
    ap._lifecycle_complete.clear()  # boundary NOT yet crossed

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
        result = registry.kill(ap.project_root)

    assert result["ok"] is False
    assert result.get("code") == "FINALIZATION_PENDING"
    # kill must not manufacture lifecycle completion or release ownership.
    assert ap._lifecycle_complete.is_set() is False
    mock_ownership.release_agent.assert_not_called()
    mock_bus.publish.assert_not_called()


def test_kill_proc_none_race_ok_when_lifecycle_set():
    """T-834: when the lifecycle Event is already set (the winning finalizer
    crossed the boundary before kill() captured proc=None), kill() returns
    success immediately -- no wait, no fabrication."""
    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    ap = DummyAgent()
    registry._processes[registry._key(ap.project_root)] = ap
    ap.process = None
    ap.status = "running"
    ap._lifecycle_complete.set()  # boundary already crossed

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus") as mock_bus,
    ):
        result = registry.kill(ap.project_root)

    assert result == {"ok": True}, result
    assert ap._lifecycle_complete.is_set() is True


def test_kill_proc_none_race_blocks_until_lifecycle_event(monkeypatch):
    """T-834: kill() must NOT return before the lifecycle Event is set, even
    though proc is None. A winning finalizer that completes only after kill
    has parked must unblock it with success (ownership then released)."""
    import saipenview.runtime as rt_module

    from saipenview.runtime import ProcessManager

    monkeypatch.setattr(rt_module, "_KILL_LIFECYCLE_WAIT_SECONDS", 5.0)

    registry = ProcessManager()
    ap = DummyAgent()
    root = ap.project_root
    registry._processes[registry._key(root)] = ap
    ap.process = None
    ap.status = "running"
    ap._lifecycle_complete.clear()

    result: dict = {}
    returned = threading.Event()

    def run_kill():
        result.update(registry.kill(root))
        returned.set()

    worker = threading.Thread(target=run_kill, daemon=True)
    worker.start()

    # Kill is parked on the lifecycle primitive, not returned.
    assert not returned.wait(0.5), "kill returned before lifecycle completion"
    assert result == {}, "kill must not have produced a result yet"
    # The winning finalizer crosses the boundary now.
    ap._lifecycle_complete.set()
    assert returned.wait(5), "kill never returned after lifecycle completion"
    assert result == {"ok": True}, result
