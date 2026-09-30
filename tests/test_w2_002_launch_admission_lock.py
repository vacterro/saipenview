"""W2-002: slow spawn/accounting must not hold the admission lock."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import saipenview.runtime as runtime
from saipenview.engines.base import AgentEngine
from saipenview.ownership import RootOwnership
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _Engine(AgentEngine):
    def __init__(self, command: list[str]) -> None:
        self._command = command

    @property
    def name(self) -> str:
        return "admission-test"

    @property
    def display_name(self) -> str:
        return "Admission Test"

    def detect(self) -> bool:
        return True

    def build_command(self, project_root, instruction, *, extra_args=None):
        return self._command

    @property
    def supports_stdin(self) -> bool:
        return False


def _manager(tmp_path: Path) -> ProcessManager:
    manager = ProcessManager(ownership=RootOwnership())
    manager.sessions = SessionStore(base_dir=tmp_path / "sessions")
    return manager


def _wait_for_token_resolution(manager, monkeypatch):
    waiting = threading.Event()
    original = runtime._LaunchToken.wait

    def observed(token, timeout=None):
        waiting.set()
        return original(token, timeout)

    monkeypatch.setattr(runtime._LaunchToken, "wait", observed)
    return waiting


def test_stop_closes_admission_while_popen_is_blocked(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    root = tmp_path / "spawned"
    other = tmp_path / "later"
    root.mkdir()
    other.mkdir()
    engine = _Engine([sys.executable, "-c", "import time; time.sleep(30)"])
    popen_entered = threading.Event()
    release_popen = threading.Event()
    token_waiting = _wait_for_token_resolution(manager, monkeypatch)
    real_popen = runtime.subprocess.Popen
    popen_calls = []
    launch_result: dict = {}
    launch_errors: list[BaseException] = []

    def blocked_popen(*args, **kwargs):
        popen_calls.append("popen")
        popen_entered.set()
        assert release_popen.wait(timeout=10), "test never released Popen"
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(runtime.subprocess, "Popen", blocked_popen)

    def launch():
        try:
            launch_result["value"] = manager.launch(engine, str(root), "run")
        except BaseException as exc:  # preserve worker errors for the main test
            launch_errors.append(exc)

    launch_thread = threading.Thread(target=launch)
    stop_done = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (manager.stop_all(), stop_done.set())
    )
    launch_thread.start()
    assert popen_entered.wait(timeout=5), "launch never entered Popen"
    stop_thread.start()
    try:
        assert token_waiting.wait(timeout=5), (
            "stop_all could not close admission while Popen was blocked"
        )
        with manager._admission_lock:
            assert manager._admission_open is False
            token = next(iter(manager._in_flight))
            assert token.state == "spawning"
        assert not stop_done.is_set()

        # The closed generation rejects another root while the admitted spawn
        # is still pending; it must not queue behind Popen's operating-system call.
        refused = manager.launch(engine, str(other), "must not spawn")
        assert refused["code"] == "SHUTTING_DOWN"
        assert popen_calls == ["popen"]

        release_popen.set()
        launch_thread.join(timeout=10)
        stop_thread.join(timeout=10)
        assert not launch_thread.is_alive()
        assert not stop_thread.is_alive()
        assert launch_errors == []
        # SRC-018 R006: once Popen returns, the child is registered and its
        # token resolved committed BEFORE the blocking session persistence. A
        # shutdown racing that window may finalize the child either just after
        # it publishes (launch reports ok=True, then stop kills it) or before
        # publication (launch reports the controlled SHUTTING_DOWN). The
        # binding invariant is that NO child survives -- not which of the two
        # legal outcomes won the race.
        v = launch_result["value"]
        assert v["ok"] is True or v.get("code") == "SHUTTING_DOWN"
        assert token.state in ("committed", "cancelled")
        assert token.wait(timeout=0)
        assert stop_done.is_set()
        assert manager.list_running() == []
        assert not manager.ownership.agent_owns(root)
    finally:
        release_popen.set()
        launch_thread.join(timeout=10)
        stop_thread.join(timeout=10)
        manager.stop_all()


def test_shutdown_accounts_for_child_while_session_start_is_blocked(
    tmp_path, monkeypatch
):
    """SRC-018 R006 core acceptance oracle.

    A real child exists (Popen succeeded) but SessionStore.start() -- the
    nonessential/blocking persistence -- has not returned. The audit contract
    requires that shutdown can ALREADY identify and terminate that child
    WITHOUT waiting for storage latency. This test deliberately keeps
    SessionStore.start blocked while stop_all runs to completion and proves
    the child was killed; it does NOT obtain GREEN by releasing start and
    watching eventual cleanup (that was the old insufficient behavior).
    """
    manager = _manager(tmp_path)
    root = tmp_path / "session-start"
    root.mkdir()
    engine = _Engine([sys.executable, "-c", "import time; time.sleep(30)"])
    session_entered = threading.Event()
    release_session = threading.Event()
    original_start = manager.sessions.start
    launch_result: dict = {}
    launch_errors: list[BaseException] = []
    started_events: list[dict] = []

    def _record_started(payload):
        started_events.append(payload)

    runtime.event_bus.subscribe("agent.started", _record_started)

    def blocked_session_start(*args, **kwargs):
        session_entered.set()
        assert release_session.wait(timeout=15), (
            "test never released SessionStore.start"
        )
        return original_start(*args, **kwargs)

    monkeypatch.setattr(manager.sessions, "start", blocked_session_start)

    def launch():
        try:
            launch_result["value"] = manager.launch(engine, str(root), "run")
        except BaseException as exc:  # preserve worker errors for the main test
            launch_errors.append(exc)

    launch_thread = threading.Thread(target=launch)
    launch_thread.start()
    try:
        assert session_entered.wait(timeout=10), (
            "launch never entered SessionStore.start"
        )
        # The child is accountable BEFORE the blocking persistence: it is in
        # the process registry and its admission token is already committed.
        with manager._lock:
            ap = manager._processes[manager._key(str(root))]
        assert ap.status == "running"
        assert ap.process.poll() is None, "real child is alive"
        token = next(iter(manager._in_flight), None)
        # Token resolved committed at registration; _in_flight is drained.
        assert token is None
        assert manager.ownership.agent_owns(root)

        # stop_all runs to completion WHILE SessionStore.start is still
        # blocked. It must not wait on storage latency.
        stop_done = threading.Event()
        stop_thread = threading.Thread(
            target=lambda: (manager.stop_all(), stop_done.set())
        )
        stop_thread.start()
        assert stop_done.wait(timeout=15), (
            "stop_all blocked on session persistence -- the child was not "
            "accountable before SessionStore.start"
        )
        # Proven: the spawned child was terminated by shutdown, persistence
        # still parked.
        assert not session_completed(release_session)
        assert ap.status == "killed"
        assert ap.process is None or ap.process.poll() is not None
        assert manager.list_running() == []
        assert not manager.ownership.agent_owns(root)

        # Release persistence: the launch thread must NOT resurrect the
        # already-terminal child, must NOT start a new live lifecycle and must
        # report the controlled cancellation.
        release_session.set()
        launch_thread.join(timeout=10)
        assert not launch_thread.is_alive()
        assert launch_errors == []
        assert launch_result["value"]["code"] == "SHUTTING_DOWN"
        assert ap.status == "killed"
        assert manager.list_running() == []
        assert manager.count_running() == 0
        assert not manager.ownership.agent_owns(root)
        # agent.started must never fire for a child a shutdown finalized.
        assert started_events == []
    finally:
        release_session.set()
        launch_thread.join(timeout=10)
        manager.stop_all()
        runtime.event_bus.unsubscribe("agent.started", _record_started)


def session_completed(release_session: threading.Event) -> bool:
    """SessionStore.start only returns after this event; not yet set == blocked."""
    return release_session.is_set()


def test_restart_generation_after_blocked_launch_accounts_child(
    tmp_path, monkeypatch
):
    """A blocked-persistence launch does not stall a stop/restart cycle."""
    manager = _manager(tmp_path)
    root = tmp_path / "restart"
    root.mkdir()
    engine = _Engine([sys.executable, "-c", "import time; time.sleep(30)"])
    session_entered = threading.Event()
    release_session = threading.Event()
    original_start = manager.sessions.start
    launch_result: dict = {}

    def blocked_session_start(*args, **kwargs):
        session_entered.set()
        assert release_session.wait(timeout=15)
        return original_start(*args, **kwargs)

    monkeypatch.setattr(manager.sessions, "start", blocked_session_start)

    generation = manager._admission_gen
    launch_thread = threading.Thread(
        target=lambda: launch_result.update(
            value=manager.launch(engine, str(root), "run")
        )
    )
    launch_thread.start()
    try:
        assert session_entered.wait(timeout=10)
        manager.stop_all()  # terminates the accountable child, no waiting
        # A launch on the closed generation is refused.
        refused = manager.launch(engine, str(root / "second"), "closed")
        assert refused["code"] == "SHUTTING_DOWN"
        manager.begin_lifecycle()
        with manager._admission_lock:
            assert manager._admission_open is True
            assert manager._admission_gen == generation + 1
            assert not manager._in_flight
        release_session.set()
        launch_thread.join(timeout=10)
        assert launch_result["value"]["code"] == "SHUTTING_DOWN"
        assert manager.list_running() == []
        assert not manager.ownership.agent_owns(root)
    finally:
        release_session.set()
        launch_thread.join(timeout=10)
        manager.stop_all()
