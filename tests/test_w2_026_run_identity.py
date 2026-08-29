"""T-36 / W2-026: agent run identity.

Agent control APIs identified target only by canonical project root.
Backend launch response did not expose run_id. Delayed stop for old run
R1 killed new run R2 on the same root (exit_code -15).

Fix: expose immutable run_id from launch, require run-aware target for
stop/input, reject expected_run_id != active_run_id.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.runtime import ProcessManager


class _FakeEngine:
    def __init__(self, cmd: list[str]):
        self.cmd = cmd
        self.name = "test"
        self.display_name = "Test"
        self.default_env = None
        self.supports_stdin = True

    def build_command(self, project_root: str, instruction: str) -> list[str]:
        return self.cmd

    def detect(self) -> bool:
        return True


class _FakeOwnership:
    def __init__(self):
        self._reserved = False

    def reserve_agent(self, root: Path) -> bool:
        if self._reserved:
            return False
        self._reserved = True
        return True

    def release_agent(self, root: Path) -> None:
        self._reserved = False

    def agent_owns(self, root: Path) -> bool:
        return self._reserved


def _make_pm() -> ProcessManager:
    with patch("saipenview.protocol_write.get_coordinator") as mock_coord:
        mock_coord.return_value.ownership = _FakeOwnership()
        return ProcessManager()


def _pid_alive(pid: int) -> bool:
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/pid", str(pid), "/fo", "none", "/n"],
            capture_output=True,
        )
        return False
    except OSError:
        return True


def test_launch_exposes_run_id(tmp_path: Path):
    """launch() response includes run_id."""
    child = tmp_path / "child.py"
    child.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()

    result = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert result["ok"] is True
    assert "run_id" in result
    assert result["run_id"] is not None
    run_id = result["run_id"]

    # get_status should include run_id
    status = pm.get_status(root)
    assert status.get("run_id") == run_id

    # get_output should include run_id
    output = pm.get_output(root)
    assert output.get("run_id") == run_id

    pm.kill(root)


def test_stale_kill_refused(tmp_path: Path):
    """kill with wrong run_id is refused, new run unaffected."""
    child = tmp_path / "child.py"
    child.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()

    # Launch R1
    r1 = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert r1["ok"] is True
    r1_id = r1["run_id"]

    # Wait for R1 to be fully running
    time.sleep(0.5)

    # Kill R1 properly
    r1_result = pm.kill(root)
    assert r1_result["ok"] is True

    # Launch R2 on same root
    r2 = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go2")
    assert r2["ok"] is True
    r2_id = r2["run_id"]

    # Try to kill with R1's stale run_id -> must be refused
    stale = pm.kill(root, expected_run_id=r1_id)
    assert stale["ok"] is False
    assert stale.get("code") == "RUN_STALE", stale

    # R2 must still be running
    status = pm.get_status(root)
    assert status["status"] == "running"
    assert status["run_id"] == r2_id

    # Kill R2 with correct run_id -> succeeds
    ok = pm.kill(root, expected_run_id=r2_id)
    assert ok["ok"] is True

    # Verify R2 is gone (status becomes terminal, not "none")
    status = pm.get_status(root)
    assert status["status"] in ("killed", "done", "failed", "none")


def test_send_input_rejects_stale_run_id(tmp_path: Path):
    """send_input with wrong run_id is refused."""
    child = tmp_path / "child.py"
    child.write_text("import time; time.sleep(30)\n", encoding="utf-8")
    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()

    r1 = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert r1["ok"] is True
    r1_id = r1["run_id"]

    time.sleep(0.5)

    # Stale run_id -> refused
    stale = pm.send_input(root, "hello", expected_run_id="stale-id")
    assert stale["ok"] is False
    assert stale.get("code") == "RUN_STALE"

    # Correct run_id -> succeeds
    ok = pm.send_input(root, "hello", expected_run_id=r1_id)
    assert ok["ok"] is True

    pm.kill(root)
