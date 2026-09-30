"""W2-001: Popen failures cancel their token and leave lifecycle usable.

These regressions preserve the original self-deadlock repair while W2-002
moves Popen outside the lifecycle lock: a failed spawn must release its root
reservation, retire its token, and leave later launches and shutdown usable.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.ownership import RootOwnership
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


class _ReadyEngine(AgentEngine):
    """A launchable engine that never blocks: build_command returns at once."""

    @property
    def name(self) -> str:
        return "ready-test"

    @property
    def display_name(self) -> str:
        return "Ready Test"

    def detect(self) -> bool:
        return True

    def build_command(self, project_root, instruction, *, extra_args=None):
        return [sys.executable, "-c", "pass"]

    @property
    def supports_stdin(self) -> bool:
        return False


def _make_manager(tmp_path) -> ProcessManager:
    pm = ProcessManager(ownership=RootOwnership())
    pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
    return pm


def _run_with_popen_error(tmp_path, exc: Exception) -> dict:
    pm = _make_manager(tmp_path)
    root = str(tmp_path / "proj")
    Path(root).mkdir(parents=True, exist_ok=True)
    engine = _ReadyEngine()
    result: dict = {}

    def do_launch():
        # Patch inside the thread so the exception lands exactly on this
        # launch's Popen call.
        with patch("saipenview.runtime.subprocess.Popen", side_effect=exc):
            result["value"] = pm.launch(engine, root, "go")

    t = threading.Thread(target=do_launch)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "launch thread self-deadlocked after Popen failure"

    v = result["value"]
    assert v["ok"] is False, v
    # The failed root reservation is released and the token retired.
    assert not pm.ownership.agent_owns(Path(root))
    with pm._admission_lock:
        assert len(pm._in_flight) == 0, "in-flight token not retired"
    # The admission lock is free again: a non-blocking acquire must succeed.
    acquired = pm._admission_lock.acquire(blocking=False)
    assert acquired, "_admission_lock leaked after Popen failure"
    pm._admission_lock.release()
    # The manager is still fully usable: stop_all returns, a second launch runs.
    pm.stop_all()
    return v


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("no such executable"),
        NotADirectoryError("bad cwd"),
        OSError("spawn fail"),
        __import__("subprocess").SubprocessError("subprocess boom"),
    ],
)
def test_popen_failure_returns_promptly_and_releases_lock(tmp_path, exc):
    v = _run_with_popen_error(tmp_path, exc)
    assert "error" in v


def test_second_launch_and_stop_all_do_not_block_after_popen_failure(tmp_path):
    pm = _make_manager(tmp_path)
    root = str(tmp_path / "proj")
    Path(root).mkdir(parents=True, exist_ok=True)
    engine = _ReadyEngine()

    with patch(
        "saipenview.runtime.subprocess.Popen", side_effect=OSError("spawn fail")
    ):
        first = pm.launch(engine, root, "go")
    assert first["ok"] is False

    # stop_all must return promptly (not block on a leaked admission lock).
    done = threading.Event()

    def do_stop():
        pm.stop_all()
        done.set()

    t = threading.Thread(target=do_stop)
    t.start()
    assert done.wait(timeout=10), "stop_all blocked after a Popen failure"
    t.join(timeout=10)

    # A fresh lifecycle can still launch successfully (real Popen: the engine
    # is a short-lived `python -c pass`).
    pm.begin_lifecycle()
    second = pm.launch(engine, root, "go again")
    try:
        assert second["ok"] is True, second
    finally:
        pm.stop_all()
