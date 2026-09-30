"""W2-003 (SRC-018 R007): natural-death vs late-kill terminal claim.

The audited race: `_finalize()` proved OS death, then derived terminal status
from `_kill_intent` in a SEPARATE step from committing `_finalized`. A Stop
arriving after natural death was already proven could inject `_kill_intent`
into that window and relabel a natural `done`/`failed` run as `killed`.

These are deterministic event-barrier oracles -- never sleep-based race tests.
They pin the exact proven-death/status-decision window and prove:

  * a kill that arrives after OS death is proven refuses and does NOT mutate
    intent, so a natural zero exit stays `done` and a natural nonzero exit
    stays `failed`;
  * a genuine pre-death kill (intent set while the process is live) still
    yields `killed`;
  * exactly-once transcript/session publication is preserved.
"""

from __future__ import annotations

import collections
import subprocess
import threading
from unittest.mock import MagicMock, patch

from saipenview.runtime import ProcessManager


class _DummyProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode
        self.pid = 4321

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("proc", timeout or 0)

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9

    def terminate(self):
        self.kill()


class _DummyAgent:
    def __init__(self):
        self.process = _DummyProcess(returncode=0)
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
        self._transcript_lock = threading.Lock()
        self._transcript_done = False
        self._transcript_pending = None
        self._reader_eof_declined = False
        self.output_lines = collections.deque(maxlen=5000)
        self._lifecycle_complete = threading.Event()
        self._rollback = False

    def elapsed_seconds(self):
        return 0.0


def test_late_kill_after_proven_natural_zero_exit_stays_done():
    """A Stop landing AFTER the finalizer proved a zero exit must not relabel
    the run killed. It refuses; status stays done, kill intent untouched."""
    registry = ProcessManager()
    ap = _DummyAgent()
    ap.process = _DummyProcess(returncode=0)
    registry._processes[registry._key(ap.project_root)] = ap

    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus"),
    ):
        # Finalizer proves natural death first (no kill intent).
        registry._finalize(ap)
        assert ap._finalized is True
        assert ap.status == "done"
        assert ap._kill_intent is False

        # Late Stop click arrives now. Death is already proven and claimed.
        result = registry.kill(ap.project_root)

    assert result["ok"] is False
    assert "not running" in result["error"]
    assert ap.status == "done"
    assert ap._kill_intent is False  # intent was NOT injected
    # Exactly-once commit preserved.
    assert mock_sessions.finish.call_count == 1
    mock_sessions.finish.assert_called_once_with("run-1", "done", 0)
    assert mock_ownership.release_agent.call_count == 1


def test_late_kill_after_proven_natural_nonzero_exit_stays_failed():
    registry = ProcessManager()
    ap = _DummyAgent()
    ap.process = _DummyProcess(returncode=3)
    ap.run_id = "run-2"
    registry._processes[registry._key(ap.project_root)] = ap

    with (
        patch.object(registry, "ownership"),
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus"),
    ):
        registry._finalize(ap)
        assert ap.status == "failed"
        result = registry.kill(ap.project_root)

    assert result["ok"] is False
    assert ap.status == "failed"
    assert ap._kill_intent is False
    mock_sessions.finish.assert_called_once_with("run-2", "failed", 3)


def test_kill_intent_set_while_live_still_yields_killed():
    """A genuine pre-death kill records intent while the process is live; the
    finalizer's snapshot then reports killed."""
    registry = ProcessManager()
    ap = _DummyAgent()
    # Live at kill time (poll None), then dies before finalize proves it.
    ap.process = _DummyProcess(returncode=None)
    registry._processes[registry._key(ap.project_root)] = ap

    with (
        patch.object(registry, "ownership"),
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus"),
    ):
        # kill() sets intent (process live), terminate() makes it die.
        result = registry.kill(ap.project_root)
        assert result["ok"] is True
        assert ap._kill_intent is True
        assert ap.status == "killed"

    mock_sessions.finish.assert_called_once_with("run-1", "killed", -9)


def test_barrier_race_late_kill_cannot_win_the_terminal_claim():
    """Deterministic barrier oracle for the exact audited window.

    The finalizer is paused at the instant it has proven OS death but before
    it claims the terminal transition. A competing kill() is released into that
    window. Under the fixed code the terminal claim + kill-intent snapshot are
    atomic and kill() observes proven death under the same lock, so the late
    kill refuses; the natural `done` verdict survives.
    """
    registry = ProcessManager()
    ap = _DummyAgent()
    ap.process = _DummyProcess(returncode=0)
    registry._processes[registry._key(ap.project_root)] = ap

    kill_may_run = threading.Event()
    kill_done = threading.Event()
    kill_result: dict = {}

    real_wait = ap.process.wait
    wait_calls = {"n": 0}

    def gated_wait(timeout=None):
        rc = real_wait(timeout)
        wait_calls["n"] += 1
        # The finalizer's proven-death wait() has just returned (returncode is
        # already 0). Pause HERE -- after death is provable, before the
        # _finalized claim -- and release the late kill into that exact window.
        if wait_calls["n"] == 1 and threading.current_thread().name == "finalizer":
            kill_may_run.set()
            assert kill_done.wait(timeout=5), "late kill never completed"
        return rc

    ap.process.wait = gated_wait  # type: ignore[method-assign]

    with (
        patch.object(registry, "ownership"),
        patch.object(registry, "sessions") as mock_sessions,
        patch("saipenview.runtime.event_bus"),
    ):

        def run_finalize():
            registry._finalize(ap)

        def run_kill():
            assert kill_may_run.wait(timeout=5), "finalizer never proved death"
            kill_result.update(registry.kill(ap.project_root))
            kill_done.set()

        t_final = threading.Thread(target=run_finalize, name="finalizer")
        t_kill = threading.Thread(target=run_kill, name="late-kill")
        t_final.start()
        t_kill.start()
        t_final.join(timeout=10)
        t_kill.join(timeout=10)

    assert not t_final.is_alive()
    assert not t_kill.is_alive()
    # The natural verdict won; the late kill never relabelled it. Whether the
    # late kill reports ok=True (it observed proven death and drove the natural
    # finalize) or refuses is secondary -- the binding invariant is that the
    # run stays `done` and no kill intent was ever injected.
    assert ap.status == "done"
    assert ap._kill_intent is False
    # Exactly-once session commit with the natural status.
    mock_sessions.finish.assert_called_once_with("run-1", "done", 0)
