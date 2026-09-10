"""ProcessManager must actually write the transcript, not merely own a store.

These drive a real subprocess (this interpreter, printing known lines) through
the real launch/read/finish path, because the wiring between the reader thread
and the session store is exactly the part a unit test of either half misses.

T-834: terminal status publication may not outrun the session commit. The
first externally observable done/failed/killed from ProcessManager.get_status
must imply SessionStore.finish has already returned -- history terminal,
transcript complete -- with no second eventual-consistency wait. Proven with
synchronization barriers (never sleeps): the finish call is held open while
the public status is observed.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _EchoEngine(AgentEngine):
    """Prints three lines and exits 0. No agent CLI needed."""

    def __init__(self, script: str | None = None, name: str = "echo-test") -> None:
        self._script = script or (
            "import sys\nfor i in range(3):\n    print('line %d' % i, flush=True)\n"
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


# ---------------------------------------------------------------------------
# T-834: terminal publication may not outrun the session commit.
# ---------------------------------------------------------------------------


class _BlockedFinish:
    """Wrap sessions.finish with a barrier the test controls.

    finish_entered fires when the finalizer reaches SessionStore.finish;
    the call then blocks until allow_finish is set; finish_returned fires
    after the real finish returns. Deterministic: no sleeps anywhere.
    """

    def __init__(self, pm: ProcessManager, timeout: float = 20.0) -> None:
        real_finish = pm.sessions.finish
        self.finish_entered = threading.Event()
        self.allow_finish = threading.Event()
        self.finish_returned = threading.Event()
        self.timeout = timeout
        self.calls: list[tuple[str, str, int | None]] = []

        def blocked_finish(run_id, status, exit_code):
            self.calls.append((run_id, status, exit_code))
            self.finish_entered.set()
            assert self.allow_finish.wait(self.timeout), "finish never released"
            try:
                return real_finish(run_id, status, exit_code)
            finally:
                self.finish_returned.set()

        pm.sessions.finish = blocked_finish  # type: ignore[method-assign]


class TestTerminalPublicationWaitsForSessionCommit:
    """While SessionStore.finish is blocked mid-commit, the ProcessManager
    status must NOT yet be terminal; once finish returns and the status is
    first observed terminal, history/transcript must already agree -- with
    zero retries and zero sleeps between the two observations."""

    @pytest.mark.parametrize(
        "script,terminal",
        [
            (
                "for i in range(3):\n    print('line %d' % i, flush=True)\n",
                "done",
            ),
            (
                "import sys; print('bad', flush=True); sys.exit(3)",
                "failed",
            ),
        ],
        ids=["done", "failed"],
    )
    def test_first_terminal_status_implies_session_is_terminal(
        self, manager, tmp_path, script, terminal
    ):
        root = str(tmp_path)
        blocked = _BlockedFinish(manager)

        assert manager.launch(_EchoEngine(script=script), root, "go")["ok"] is True
        assert blocked.finish_entered.wait(20), "finalizer never reached finish"

        # THE INVARIANT: finish is still blocked, so no terminal status may
        # be published yet. The old code reported done/failed here.
        assert manager.get_status(root)["status"] == "running"

        blocked.allow_finish.set()
        assert blocked.finish_returned.wait(20), "finish never returned"

        # Wait ONLY for the public status transition itself, then assert the
        # session truth immediately -- no retry, no transcript/history poll.
        assert _wait_for(lambda: manager.get_status(root)["status"] == terminal)
        history = manager.sessions.history(root)
        assert history[0]["status"] == terminal
        assert history[0]["exit_code"] == (3 if terminal == "failed" else 0)

        transcript = manager.sessions.transcript(history[0]["run_id"])
        if terminal == "done":
            assert transcript["lines"] == ["line 0", "line 1", "line 2"]
            assert transcript["total"] == 3
        else:
            assert transcript["lines"] == ["bad"]
            assert transcript["total"] == 1

    def test_finishing_exactly_once_even_when_observed_mid_commit(
        self, manager, tmp_path
    ):
        # A status poll racing the commit window must not perturb the
        # exactly-once contract: one finish call, one terminal history row.
        root = str(tmp_path)
        blocked = _BlockedFinish(manager)
        manager.launch(_EchoEngine(), root, "go")
        assert blocked.finish_entered.wait(20)

        seen: list[str] = []
        saw_terminal = threading.Event()

        def poller():
            while not saw_terminal.is_set():
                status = manager.get_status(root)["status"]
                seen.append(status)
                if status == "done":
                    saw_terminal.set()
                time.sleep(0.001)

        thread = threading.Thread(target=poller, daemon=True)
        thread.start()
        try:
            blocked.allow_finish.set()
            assert blocked.finish_returned.wait(20)
            assert _wait_for(
                lambda: manager.get_status(root)["status"] == "done"
            )
            assert saw_terminal.wait(10), "poller never observed the transition"
        finally:
            saw_terminal.set()
            thread.join(timeout=5)

        assert blocked.calls.count(blocked.calls[0]) == 1
        assert len(manager.sessions.history(root)) == 1
        assert set(seen) <= {"running", "done"}
        assert "done" in seen


class TestKillPublicationObeysTheSameBoundary:
    def test_first_killed_status_implies_session_is_terminal(self, manager, tmp_path):
        # An ordinarily drained kill: terminate() makes stdout hit EOF, so the
        # reader drains within the bounded window and the same commit-before-
        # publish boundary applies. When get_status first exposes "killed",
        # the session record must already be killed and the drained tail
        # readable.
        root = str(tmp_path)
        engine = _EchoEngine(
            script="import sys\nprint('before stop', flush=True)\n"
            "import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        result = manager.launch(engine, root, "go")
        run_id = result["run_id"]
        assert _wait_for(
            lambda: manager.get_status(root)["status"] == "running"
        )
        # The live buffer is the pre-commit tail record (the transcript file
        # only receives its flush at _FLUSH_EVERY/finish); wait until the
        # drained output is really there.
        assert _wait_for(
            lambda: manager.get_output(root)["total"] >= 1
        )

        assert manager.kill(root)["ok"] is True
        assert _wait_for(lambda: manager.get_status(root)["status"] == "killed")

        # Immediately, with no retry: the session record agrees.
        rec = manager.sessions.history(root)[0]
        assert rec["status"] == "killed"
        body = manager.sessions.transcript(rec["run_id"])
        assert "before stop" in body["lines"]

    def test_a_late_kill_cannot_relabel_an_already_finalizing_run(
        self, manager, tmp_path
    ):
        # The finalizer holds _finalized=True while SessionStore.finish is in
        # flight; public status is still "running" during that window. A Stop
        # click landing there must NOT terminate or relabel the already-dead
        # run as killed -- it reuses the existing not-running error contract.
        root = str(tmp_path)
        blocked = _BlockedFinish(manager)
        manager.launch(_EchoEngine(), root, "go")
        assert blocked.finish_entered.wait(20), "finalizer never reached finish"

        result = manager.kill(root)
        assert result["ok"] is False
        assert "not running" in result["error"]

        # The run still completes naturally; nothing was relabelled killed.
        blocked.allow_finish.set()
        assert blocked.finish_returned.wait(20)
        assert _wait_for(lambda: manager.get_status(root)["status"] == "done")
        history = manager.sessions.history(root)
        assert history[0]["status"] == "done"
        assert history[0]["exit_code"] == 0


class TestKillWaitsForTheCompetingFinalizer:
    """T-834 regression: kill() legitimately began on a live run, recorded
    intent, and proved death -- then the exit monitor won the exactly-once
    _finalize token and parked inside SessionStore.finish. The OLD kill
    returned {"ok": True} at that moment with status still "running" and
    the reservation still held, so the immediate relaunch that follows a
    successful Stop was intermittently rejected ("Agent already running").
    The NEW kill must not report success until the winning finalizer
    completed the lifecycle boundary (terminal status + ownership release),
    and the immediate second launch must succeed. Pinned with events only --
    no sleep-based oracle.
    """

    def test_kill_waits_for_the_exit_monitor_finalization(
        self, manager, tmp_path
    ):
        root = str(tmp_path)
        engine = _EchoEngine(
            script="import sys\nprint('held', flush=True)\n"
            "import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        blocked = _BlockedFinish(manager)
        assert manager.launch(engine, root, "go")["ok"] is True
        assert _wait_for(lambda: manager.get_output(root)["total"] >= 1)

        # Pin the interleaving: the kill thread's _finalize call must not
        # run until the exit monitor has claimed the exactly-once token
        # and parked inside the blocked SessionStore.finish. The monitor's
        # own _finalize (and any other thread's) proceeds untouched.
        real_finalize = manager._finalize
        kill_thread: list[threading.Thread] = []
        kill_finalize_done = threading.Event()
        parked = threading.Event()
        real_event: list[threading.Event] = []

        class _ParkObserver:
            """Reports the moment kill() parks on the lifecycle primitive;
            everything else delegates to the real event. Installed on the
            AgentProcess BEFORE the kill thread reaches its wait so the
            red/green observation is deterministic."""

            def is_set(self):
                return real_event[0].is_set()

            def wait(self, timeout=None):
                parked.set()
                return real_event[0].wait(timeout)

            def set(self):
                real_event[0].set()

        def hooked_finalize(ap, requested_status=None):
            if kill_thread and threading.current_thread() is kill_thread[0]:
                assert blocked.finish_entered.wait(20), (
                    "exit monitor never claimed the token"
                )
                # Swap in the observer now -- before the kill thread returns
                # to kill() and blocks on the lifecycle primitive.
                real_event.append(ap._lifecycle_complete)
                ap._lifecycle_complete = _ParkObserver()
                result = real_finalize(ap, requested_status)
                kill_finalize_done.set()
                return result
            return real_finalize(ap, requested_status)

        manager._finalize = hooked_finalize  # type: ignore[method-assign]

        kill_result: dict = {}
        kill_returned = threading.Event()

        def run_kill():
            kill_result.update(manager.kill(root))
            kill_returned.set()

        worker = threading.Thread(target=run_kill, name="t834-kill", daemon=True)
        kill_thread.append(worker)
        worker.start()

        # The exit monitor claimed the token and is parked mid-commit.
        assert blocked.finish_entered.wait(20), "monitor never reached finish"
        # The kill thread's own _finalize has now run and lost the race
        # (no-op against the claimed token).
        assert kill_finalize_done.wait(20), "kill finalize never ran"

        # THE NEW INVARIANT: with the competitor still parked inside
        # finish, kill must be parked on the per-process lifecycle
        # completion primitive -- not returned. (The old implementation
        # returned success here; it never touched the primitive, so
        # `parked` never fires and this deterministic red control fails on it.)
        # Wait for the kill thread to reach its lifecycle wait. In the old
        # implementation kill returned immediately after its _finalize
        # no-op, so `parked` never fires -- this assert is the deterministic
        # red control for the OLD code and always passes on the NEW code.
        assert parked.wait(20), "kill returned before lifecycle completion"
        assert not kill_returned.is_set()
        assert manager.get_status(root)["status"] == "running"

        # 7-10: release the commit; the finalizer publishes killed,
        # releases ownership, and only then does kill() return success.
        blocked.allow_finish.set()
        assert blocked.finish_returned.wait(20)
        assert kill_returned.wait(20), "kill never returned"
        assert kill_result["ok"] is True

        # Terminal status is visible the instant kill reports success --
        # no eventual-consistency wait.
        assert manager.get_status(root)["status"] == "killed"

        # 11: the immediate second launch on the same root succeeds --
        # the old run's reservation is gone, not merely in flight.
        second = _EchoEngine(
            script="import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        assert manager.launch(second, root, "go2")["ok"] is True


class TestDeferredReaderPath:
    """W2-004, preserved by contract: when a descendant inherits stdout and
    the reader outlives the 10-second bounded drain, the process status MAY
    publish terminal while the transcript close waits on reader EOF. This is
    the one intentional exception to the commit-before-publish ordering.

    Windows-only because the deterministic pipe-holder relies on Job Object
    containment: the child assigns its own descendant to the run's Job
    Object, so closing the run's Job handle terminates exactly that
    descendant -- no PID bookkeeping, no unrelated-process kills, nothing
    orphaned. On the drained-path platforms the drained path is exercised
    everywhere else in this module.
    """

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="deterministic pipe-holder inheritance uses STARTF_USESTDHANDLES",
    )
    def test_terminal_status_may_lead_a_deferred_transcript(
        self, manager, tmp_path, monkeypatch
    ):
        # W2-033 closes the run's Job handle at proven death, which would
        # terminate an in-job pipe-holder and drain the pipe -- so this test
        # disables the Job assignment to build the real W2-004 scenario: a
        # descendant that outlives the run and holds the inherited pipe.
        monkeypatch.setattr(
            "saipenview.runtime._assign_job_object", lambda proc: None
        )
        root = str(tmp_path)
        grand_file = tmp_path / "grand.py"
        grand_file.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        grand_ref = str(grand_file).replace("\\", "/")
        # STARTF_USESTDHANDLES with no stdout override makes the grandchild
        # inherit the child's stdout -- which IS the app's transcript pipe.
        # Deterministic pipe-holder, no unrelated processes involved.
        # The child exits quickly; the 11s drain comes from the 10s bounded
        # join in _finalize (change nothing here -- it is the W2-004 budget).
        engine = _EchoEngine(
            script="print('early', flush=True)\n"
            "import sys, subprocess, time\n"
            f"grand = subprocess.Popen([sys.executable, '{grand_ref}'],\n"
            "    startupinfo=subprocess.STARTUPINFO(\n"
            "        dwFlags=subprocess.STARTF_USESTDHANDLES),\n"
            "    stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "print('grand %d' % grand.pid, flush=True)\n"
            "time.sleep(1)\n"
        )
        finish_calls: list[str] = []
        real_finish = manager.sessions.finish

        def counting_finish(run_id, status, exit_code):
            finish_calls.append(run_id)
            return real_finish(run_id, status, exit_code)

        manager.sessions.finish = counting_finish  # type: ignore[method-assign]

        result = manager.launch(engine, root, "go")
        assert result["ok"] is True
        run_id = result["run_id"]

        # Find the pipe-holder's pid from the live buffer (the transcript
        # file only receives its flush at _FLUSH_EVERY/finish).
        grand_pid = None
        deadline = time.monotonic() + 15
        while grand_pid is None and time.monotonic() < deadline:
            for line in manager.get_output(root)["lines"]:
                if line.startswith("grand "):
                    grand_pid = int(line.split()[1])
            if grand_pid is None:
                time.sleep(0.1)
        assert grand_pid is not None, "pipe-holder pid never reached the buffer"

        # THE INTENTIONAL EXCEPTION (W2-004): terminal status publishes
        # BEFORE the transcript commit -- a dead process must not stay
        # "running" for an indefinitely-held pipe.
        assert _wait_for(
            lambda: manager.get_status(root)["status"] == "done", timeout=30
        )

        # The deferred commit has NOT run: the session record is still open
        # ("running" in history, not "interrupted") with the terminal
        # metadata parked in _transcript_pending for the reader's EOF path.
        with manager._lock:
            ap = manager._processes[manager._key(root)]
        with ap._transcript_lock:
            assert ap._transcript_pending == ("done", 0)
            assert ap._transcript_done is False
        hist = manager.sessions.history(root)
        assert hist and hist[0]["run_id"] == run_id
        assert hist[0]["status"] == "running"

        # Release the pipe: the reader reaches EOF and the deferred commit
        # fires exactly once with the stored terminal metadata.
        import psutil

        try:
            psutil.Process(grand_pid).kill()
        except psutil.NoSuchProcess:
            pass

        assert _wait_for(
            lambda: manager.sessions.history(root)[0]["status"] == "done",
            timeout=30,
        )
        rec = manager.sessions.history(root)[0]
        assert rec["exit_code"] == 0
        body = manager.sessions.transcript(rec["run_id"])
        assert body["found"] is True
        assert "early" in body["lines"]
        assert finish_calls.count(run_id) == 1, "transcript committed twice"
        manager.stop_all()


# ---------------------------------------------------------------------------
# T-834: kill() timeout must return FINALIZATION_PENDING, not false success.
# ---------------------------------------------------------------------------


class TestKillWaitTimeoutReturnsPending:
    """T-834 regression: kill() legitimately began on a live run, exit monitor
    won the exactly-once _finalize token and parked inside SessionStore.finish.
    The OLD kill returned {"ok": True} when the lifecycle wait timed out,
    while status remained "running" and the lifecycle event stayed unset.
    The NEW kill must return {"ok": False, "code": "FINALIZATION_PENDING"}
    when the bounded wait expires, leaving the winning finalizer free to
    complete later. Deterministic with monkeypatched timeout constant.
    """

    def test_kill_timeout_returns_finalization_pending(self, manager, tmp_path, monkeypatch):
        # Monkeypatch the lifecycle wait to a small deterministic value:
        # long enough that "kill is parked" is observable, short enough
        # that expiry needs no wall-clock patience.
        import saipenview.runtime as rt_module

        monkeypatch.setattr(rt_module, "_KILL_LIFECYCLE_WAIT_SECONDS", 0.5)

        root = str(tmp_path)
        blocked = _BlockedFinish(manager)
        engine = _EchoEngine(
            script="import sys\nprint('held', flush=True)\n"
            "import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        assert manager.launch(engine, root, "go")["ok"] is True
        assert _wait_for(lambda: manager.get_output(root)["total"] >= 1)

        # Arrange the exact interleaving: exit monitor claims token,
        # blocks in finish; kill loses token, waits on lifecycle primitive.
        real_finalize = manager._finalize
        kill_thread: list[threading.Thread] = []
        kill_finalize_done = threading.Event()
        parked = threading.Event()
        real_event: list[threading.Event] = []

        class _ParkObserver:
            def is_set(self):
                return real_event[0].is_set()

            def wait(self, timeout=None):
                parked.set()
                return real_event[0].wait(timeout)

            def set(self):
                real_event[0].set()

        def hooked_finalize(ap, requested_status=None):
            if kill_thread and threading.current_thread() is kill_thread[0]:
                assert blocked.finish_entered.wait(20), "exit monitor never claimed token"
                real_event.append(ap._lifecycle_complete)
                ap._lifecycle_complete = _ParkObserver()
                result = real_finalize(ap, requested_status)
                kill_finalize_done.set()
                return result
            return real_finalize(ap, requested_status)

        manager._finalize = hooked_finalize  # type: ignore[method-assign]

        kill_result: dict = {}
        kill_returned = threading.Event()

        def run_kill():
            kill_result.update(manager.kill(root))
            kill_returned.set()

        worker = threading.Thread(target=run_kill, name="t834-kill-timeout", daemon=True)
        kill_thread.append(worker)
        worker.start()

        # Exit monitor claimed token, parked in finish; kill finalize ran no-op.
        assert blocked.finish_entered.wait(20), "monitor never reached finish"
        assert kill_finalize_done.wait(20), "kill finalize never ran"

        # Kill is now parked on the lifecycle wait. Wait for it to reach wait.
        assert parked.wait(20), "kill returned before lifecycle completion"
        assert not kill_returned.is_set()
        assert manager.get_status(root)["status"] == "running"

        # The bounded wait expires on its own (finish still blocked).
        # kill() must return FINALIZATION_PENDING, not success.
        assert kill_returned.wait(20), "kill never returned"
        assert kill_result["ok"] is False
        assert kill_result.get("code") == "FINALIZATION_PENDING"
        assert "finalization is still pending" in kill_result.get("error", "")

        # Lifecycle event still unset, ownership still reserved.
        with manager._lock:
            ap = manager._processes[manager._key(root)]
        assert real_event[0].is_set() is False
        assert manager.get_status(root)["status"] == "running"

        # Now release the real finalizer; it must complete normally.
        blocked.allow_finish.set()
        assert blocked.finish_returned.wait(20)
        # Wait on the LIFECYCLE PRIMITIVE itself, never on public status:
        # status == "killed" only proves terminal publication, which runs
        # BEFORE ownership release and the lifecycle Event set -- polling
        # status and immediately asserting the Event would be a scheduling
        # race, not a contract check.
        assert real_event[0].wait(20), "lifecycle event never fired"

        # The Event implies the FULL boundary: terminal status published,
        # ownership released, history terminal, transcript complete.
        assert real_event[0].is_set() is True
        assert manager.get_status(root)["status"] == "killed"
        hist = manager.sessions.history(root)
        assert hist[0]["status"] == "killed"
        body = manager.sessions.transcript(hist[0]["run_id"])
        assert "held" in body["lines"]
        manager.stop_all()


# ---------------------------------------------------------------------------
# T-834: _lifecycle_complete must fire BEFORE synchronous agent.finished
# subscribers. A slow subscriber must not delay kill() completion.
# ---------------------------------------------------------------------------


class TestLifecycleEventBeforeSubscribers:
    """T-834 regression: EventBus.publish calls subscribers synchronously.
    If _lifecycle_complete.set() happens AFTER publish, a blocking subscriber
    would delay kill()'s return. The boundary kill() waits for is the
    lifecycle event, so it must be signaled before publish.
    """

    def test_lifecycle_event_before_subscriber_invocation(self, manager, tmp_path):
        from pathlib import Path as _Path

        from saipenview.events import event_bus

        root = str(tmp_path)
        callback_entered = threading.Event()
        subscriber_blocked = threading.Event()
        subscriber_released = threading.Event()
        lifecycle_set_at_entry: list[bool] = []
        status_at_entry: list[str] = []
        owned_at_entry: list[bool] = []

        def blocking_subscriber(payload):
            with manager._lock:
                ap = manager._processes.get(manager._key(root))
            lifecycle_set_at_entry.append(
                ap is not None and ap._lifecycle_complete.is_set()
            )
            status_at_entry.append(manager.get_status(root)["status"])
            owned_at_entry.append(manager.ownership.agent_owns(_Path(root)))
            # Signal entry only AFTER the observations are recorded -- the
            # main thread reads the lists the moment this fires.
            callback_entered.set()
            # Park until the main thread has inspected the boundary state.
            subscriber_blocked.wait(10)
            subscriber_released.set()

        event_bus.subscribe("agent.finished", blocking_subscriber)

        engine = _EchoEngine(
            script="import sys\nprint('before stop', flush=True)\n"
            "import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        assert manager.launch(engine, root, "go")["ok"] is True
        assert _wait_for(lambda: manager.get_output(root)["total"] >= 1)

        kill_result: dict = {}
        kill_returned = threading.Event()

        def run_kill():
            kill_result.update(manager.kill(root))
            kill_returned.set()

        worker = threading.Thread(target=run_kill, name="t834-kill-sub", daemon=True)
        worker.start()

        try:
            # The subscriber is invoked synchronously on the kill worker
            # thread, mid-finalization. THE NEW INVARIANT: by the time it is
            # entered, the lifecycle boundary is ALREADY complete (event set,
            # status terminal, ownership released). The old implementation
            # set the event only after publish, so this observes unset.
            assert callback_entered.wait(20), "subscriber never invoked"
            assert lifecycle_set_at_entry[0] is True
            assert status_at_entry[0] == "killed"
            assert owned_at_entry[0] is False

            # The kill worker is still parked inside the subscriber -- the
            # subscriber has not returned, yet the boundary it guards is
            # already published. Release it and let kill finish.
            assert not kill_returned.is_set()
            subscriber_blocked.set()
            assert subscriber_released.wait(5)
            assert kill_returned.wait(20), "kill never returned"
            assert kill_result["ok"] is True
        finally:
            subscriber_blocked.set()
            event_bus.unsubscribe("agent.finished", blocking_subscriber)
            worker.join(timeout=15)
            manager.stop_all()
