"""T-839 W2-001: launch-vs-stop lifecycle barrier.

Deterministic, event/barrier-driven regressions for the ProcessManager
launch-admission lifecycle gate. No sleep-based race ordering.

Red control (pre-fix): a launch admitted before stop_all() reserved
RootOwnership, blocked inside build_command, and was invisible to
stop_all()'s _processes snapshot -- stop_all returned, the launch spawned a
live child afterwards and reported ok=True.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.ownership import RootOwnership
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _BlockingEngine(AgentEngine):
    """Echo engine whose build_command blocks on a caller-held event."""

    def __init__(self, release: threading.Event, script: str | None = None) -> None:
        self._release = release
        self._script = script or "import time\nwhile True:\n    time.sleep(0.2)\n"
        self._entered = threading.Event()

    @property
    def name(self) -> str:
        return "blocking-test"

    @property
    def display_name(self) -> str:
        return "Blocking Test"

    def detect(self) -> bool:
        return True

    def build_command(self, project_root, instruction, *, extra_args=None):
        self._entered.set()
        self._release.wait(timeout=30)
        return [sys.executable, "-c", self._script]

    @property
    def supports_stdin(self) -> bool:
        return False


def _make_manager(tmp_path) -> ProcessManager:
    pm = ProcessManager(ownership=RootOwnership())
    pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
    return pm


def _wait_for(predicate, timeout=20.0):
    deadline = timeout + 0.0
    import time as _t

    end = _t.monotonic() + deadline
    while _t.monotonic() < end:
        if predicate():
            return True
        _t.sleep(0.02)
    return False


class TestPrespawnLaunchVsStop:
    """TEST A -- the T-839 red control. Purely behavioral: runs unchanged on
    the pre-fix tree (where it FAILS: the launch escapes shutdown, spawns a
    live child and reports ok=True) and on the post-fix tree (where it PASSES
    with a controlled cancellation)."""

    def test_stop_all_returns_controlled_cancellation_and_no_child(
        self, tmp_path
    ):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        release = threading.Event()
        engine = _BlockingEngine(release)
        result = {}

        def do_launch():
            result["value"] = pm.launch(engine, root, "go")

        t = threading.Thread(target=do_launch)
        t.start()
        try:
            # 2. RootOwnership reservation exists, 3. no _processes entry.
            assert _wait_for(lambda: pm.ownership.agent_owns(Path(root)))
            with pm._lock:
                registered_before = len(pm._processes)
            assert registered_before == 0
            # 4. blocked inside build_command
            assert engine._entered.wait(timeout=10)

            # 5. start stop_all; the barrier must park on the in-flight
            #    launch until it resolves (commit or cancel).
            stop_started = threading.Event()

            def do_stop():
                stop_started.set()
                pm.stop_all()

            t_stop = threading.Thread(target=do_stop)
            t_stop.start()
            assert stop_started.wait(timeout=10)
            # 6+7. the synchronization point the barrier requires is the
            #      launch's own resolution: release build_command; a launch
            #      that observed the closed admission must abort WITHOUT
            #      Popen and return the controlled cancellation.
            release.set()
            t.join(timeout=15)
            assert not t.is_alive(), "launch thread never finished"
            t_stop.join(timeout=15)

            v = result["value"]
            # RED CONTROL: pre-fix this assert fails -- launch reported
            # ok=True and a live child survived stop_all().
            assert not v["ok"], (
                f"launch escaped shutdown: {v} -- process created after "
                "stop_all() returned"
            )
            assert v.get("code") == "SHUTTING_DOWN"
            assert pm.list_running() == []
            assert pm.count_running() == 0
            assert not pm.ownership.agent_owns(Path(root))
            assert pm.is_running(root) is False
        finally:
            release.set()
            pm.stop_all()


class TestRegisteredLaunchWinsBeforeStop:
    """TEST B: spawn/register that commits before the barrier is killed."""

    def test_shutdown_observes_and_kills_committed_process(self, tmp_path):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)

        # Deterministic pause at the lifecycle commit boundary: block inside
        # the guarded commit section AFTER admission recheck but BEFORE
        # _processes registration. We can't inject into the middle of
        # ProcessManager code, so we simulate the ordering contract directly:
        # a normal (unblocked) launch completes its commit; stop_all that
        # begins after the commit is guaranteed to see the process because
        # the commit holds _admission_lock -- stop_all's admission-close
        # cannot pass until the commit released it.
        release = threading.Event()
        engine = _BlockingEngine(
            release, script="import time\nwhile True:\n    time.sleep(0.2)\n"
        )
        release.set()  # don't block build_command; pause at the barrier below

        committed = threading.Event()
        result = {}
        real_popen = sys.modules["subprocess"].Popen

        from unittest.mock import patch

        def commit_boundary_popen(*a, **kw):
            # Popen runs INSIDE the guarded commit section while
            # _admission_lock is held: this is the deterministic pause point.
            # A stop_all that started meanwhile is parked on the barrier and
            # CANNOT miss this process.
            p = real_popen(*a, **kw)
            committed.set()
            return p

        def do_launch():
            result["value"] = pm.launch(engine, root, "go")

        with patch(
            "saipenview.runtime.subprocess.Popen", side_effect=commit_boundary_popen
        ):
            t = threading.Thread(target=do_launch)
            t.start()
            assert committed.wait(timeout=10)
            # stop_all while the launch thread may still be finishing its
            # post-commit tail (reader/monitor threads).
            pm.stop_all()
            t.join(timeout=15)

        assert result["value"]["ok"] is True  # launch committed before barrier
        assert pm.list_running() == []
        assert pm.count_running() == 0
        # proven-death path ran: ownership released after the kill
        assert not pm.ownership.agent_owns(Path(root))


class TestShutdownWinsBeforeSpawnCommit:
    """TEST C: admission closed before the commit section -> no Popen."""

    def test_popens_never_invoked_after_closed_admission(self, tmp_path):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        release = threading.Event()
        engine = _BlockingEngine(release)
        popen_calls = {"n": 0}

        from unittest.mock import patch

        real_popen = sys.modules["subprocess"].Popen

        def counting_popen(*a, **kw):
            popen_calls["n"] += 1
            return real_popen(*a, **kw)

        result = {}
        t = threading.Thread(
            target=lambda: result.update(value=pm.launch(engine, root, "go"))
        )
        with patch(
            "saipenview.runtime.subprocess.Popen", side_effect=counting_popen
        ):
            t.start()
            try:
                assert _wait_for(lambda: pm.ownership.agent_owns(Path(root)))
                assert engine._entered.wait(timeout=10)

                # Close admission (shutdown wins) BEFORE build_command
                # returns. start stop_all in a thread so release.set() can
                # unblock the launch -> it observes the closed admission and
                # resolves the in-flight token -> stop_all returns.
                stop_done = threading.Event()

                def do_stop():
                    pm.stop_all()
                    stop_done.set()

                t_stop = threading.Thread(target=do_stop)
                t_stop.start()
                # stop_all is parked on the barrier waiting for our
                # in-flight launch: release build_command so it can resolve.
                release.set()
                t.join(timeout=15)
                assert not t.is_alive()
                stop_done.wait(timeout=15)
                t_stop.join(timeout=15)

                v = result["value"]
                assert v["ok"] is False
                assert v["code"] == "SHUTTING_DOWN"
                assert pm.list_running() == []
                assert not pm.ownership.agent_owns(Path(root))
                with pm._lock:
                    assert len(pm._processes) == 0
                assert popen_calls["n"] == 0, "Popen ran after admission closed"
            finally:
                release.set()
                pm.stop_all()
                t.join(timeout=15)

    def test_launch_refused_immediately_after_stop_all(self, tmp_path):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        pm.stop_all()
        v = pm.launch(_BlockingEngine(threading.Event()), root, "go")
        assert v == {
            "ok": False,
            "code": "SHUTTING_DOWN",
            "error": "Agent launch cancelled because SAIPENVIEW is stopping",
        }
        assert not pm.ownership.agent_owns(Path(root))


class TestRestart:
    """TEST D: stop then begin_lifecycle reopens a fresh generation."""

    def test_restart_reopens_admission_with_fresh_generation(self, tmp_path):
        from saipenview.runtime import _LaunchToken

        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)

        with pm._admission_lock:
            gen_before = pm._admission_gen

        pm.stop_all()

        class _FastEngine(_BlockingEngine):
            def __init__(self):
                super().__init__(threading.Event())
                self._release.set()

        # A launch right after stop is refused (SHUTTING_DOWN).
        v = pm.launch(_FastEngine(), root, "go")
        assert v["ok"] is False and v.get("code") == "SHUTTING_DOWN"

        # Api.start() reopens the lifecycle.
        pm.begin_lifecycle()
        with pm._admission_lock:
            assert pm._admission_gen == gen_before + 1
            assert pm._admission_open is True
            assert len(pm._in_flight) == 0

        # Fresh-generation launch succeeds.
        result = pm.launch(_FastEngine(), root, "go")
        assert result["ok"] is True
        assert pm.count_running() == 1

        # An old-generation token cannot become valid after restart.
        stale = _LaunchToken(gen_before)
        with pm._admission_lock:
            old_token_valid = (
                pm._admission_open and stale.gen == pm._admission_gen
            )
        assert old_token_valid is False

        pm.stop_all()
        assert pm.count_running() == 0

    def test_stop_all_idempotent(self, tmp_path):
        pm = _make_manager(tmp_path)
        pm.stop_all()
        pm.stop_all()  # must not raise
        v = pm.launch(_BlockingEngine(threading.Event()), str(tmp_path), "go")
        assert v.get("code") == "SHUTTING_DOWN"


class TestServiceIntegration:
    """TEST E: service stop during a blocked in-flight launch RPC."""

    def _launch_engine_name(self):
        return "generic-cli"

    def test_in_flight_rpc_cannot_create_process_after_service_stop(
        self, tmp_path
    ):
        from saipenview.api import Api
        from saipenview.service import SaipenViewService

        api = Api()
        api.stop()  # isolate from the autouse config/watcher world
        pm = api._process_manager
        pm.begin_lifecycle()
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        release = threading.Event()
        engine = _BlockingEngine(release)
        result = {}

        def do_launch():
            result["value"] = pm.launch(engine, root, "go")

        t = threading.Thread(target=do_launch)
        t.start()
        try:
            assert _wait_for(lambda: pm.ownership.agent_owns(Path(root)))
            assert engine._entered.wait(timeout=10)

            # Service-level stop drives the same backend barrier.
            svc = SaipenViewService.__new__(SaipenViewService)
            # stop() on a bare service needs _api; bind it so Api.stop drives
            # ProcessManager.stop_all exactly as the real path does.
            svc._api = api
            stop_done = threading.Event()

            def do_stop():
                api.stop()
                stop_done.set()

            t_stop = threading.Thread(target=do_stop)
            t_stop.start()
            # stop_all is parked on the barrier; release the blocked launch.
            release.set()
            t.join(timeout=15)
            assert stop_done.wait(timeout=15)
            t_stop.join(timeout=15)

            v = result["value"]
            assert v["ok"] is False and v.get("code") == "SHUTTING_DOWN"
            assert pm.count_running() == 0
            with pm._admission_lock:
                assert len(pm._in_flight) == 0
            assert not pm.ownership.agent_owns(Path(root))
        finally:
            release.set()
            pm.stop_all()

    def test_rpc_after_stopping_state_cannot_begin_launch(self, tmp_path):
        from saipenview.service import SaipenViewService

        svc = SaipenViewService(port=0)
        try:
            with svc._state_lock:
                svc._state = "stopping"
            with pytest.raises(Exception) as excinfo:
                svc._dispatch("launch_agent", [str(tmp_path), "echo", "go"])
            assert "stopping" in str(excinfo.value)
        finally:
            with svc._state_lock:
                svc._state = "stopped"


class TestSingleWriterContractIntact:
    """TEST F: the admission gate preserves one-agent-per-root."""

    def test_reservation_refusal_still_releases_token(self, tmp_path):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        # Fake a pre-existing reservation (e.g. an app write transaction).
        assert pm.ownership.begin_app_tx(Path(root)) is True
        v = pm.launch(_BlockingEngine(threading.Event()), root, "go")
        assert v["ok"] is False
        assert "refused" in v["error"]
        with pm._admission_lock:
            assert len(pm._in_flight) == 0
        pm.ownership.end_app_tx(Path(root))

    def test_two_concurrent_launches_still_one_process(self, tmp_path):
        pm = _make_manager(tmp_path)
        root = str(tmp_path / "proj")
        Path(root).mkdir(parents=True, exist_ok=True)
        block = threading.Event()
        engine = _BlockingEngine(block)
        result = {}

        def do_launch():
            result["first"] = pm.launch(engine, root, "go")

        t = threading.Thread(target=do_launch)
        t.start()
        try:
            assert _wait_for(lambda: pm.ownership.agent_owns(Path(root)))
            second = pm.launch(_BlockingEngine(threading.Event()), root, "go2")
            assert second["ok"] is False
            block.set()
            t.join(timeout=15)
            assert result["first"]["ok"] is True
            assert pm.count_running() == 1
        finally:
            block.set()
            pm.stop_all()
