"""T-22 / W2-012: ProcessManager.launch post-spawn rollback.

Launch spawns child, starts session, installs _processes, starts reader/monitor
threads. If a post-spawn step (Thread.start, event publish) fails, the child is
killed and ownership released — but _processes still held a running-entry, so
the next launch on the same root was refused as "Agent already running."

Fix: remove ap from _processes (under lock) after proven child death and before
ownership.release_agent, so the next launch sees a clean slate.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.runtime import ProcessManager


class _FakeOwnership:
    """Minimal ownership stub that tracks reservation state."""

    def __init__(self) -> None:
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


class _FakeEngine:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        self.name = "test"
        self.display_name = "Test"
        self.default_env = None
        self.supports_stdin = False

    def build_command(self, project_root: str, instruction: str) -> list[str]:
        return self.cmd


def _make_pm() -> ProcessManager:
    with patch("saipenview.protocol_write.get_coordinator") as mock_coord:
        mock_coord.return_value.ownership = _FakeOwnership()
        return ProcessManager()


def test_reader_start_failure_clears_process_entry(tmp_path):
    """Reader Thread.start failure -> child killed, _processes cleaned, next launch OK."""
    child = tmp_path / "child.py"
    child.write_text("import time; time.sleep(30)\n", encoding="utf-8")

    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()

    call_count = [0]

    def counting_start(self):
        call_count[0] += 1
        if call_count[0] == 1:
            # First Thread.start (reader) fails
            raise RuntimeError("injected reader start failure")
        # Second Thread.start (monitor) succeeds
        import threading

        orig_start = threading.Thread.start
        orig_start(self)

    with patch("threading.Thread.start", counting_start):
        with pytest.raises(RuntimeError, match="reader start failure"):
            pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")

    # Verify: child is dead, process entry removed, ownership released
    time.sleep(0.3)
    assert pm._processes.get(root) is None, (
        "_processes must be cleaned on post-spawn failure"
    )
    assert not pm.ownership.agent_owns(Path(root)), (
        "ownership must be released on post-spawn failure"
    )

    # Key invariant: next launch on same root must succeed (not refused as "running")
    result = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert result["ok"] is True, f"second launch refused after rollback: {result}"
    pm.kill(root)


def test_session_start_failure_clears_process_entry(tmp_path):
    """sessions.start failure -> child killed, _processes cleaned, next launch OK."""
    child = tmp_path / "child.py"
    child.write_text("import time; time.sleep(30)\n", encoding="utf-8")

    pm = _make_pm()
    root = str(tmp_path / "proj")
    Path(root).mkdir()

    with patch.object(
        pm.sessions, "start", side_effect=RuntimeError("injected session boom")
    ):
        with pytest.raises(RuntimeError, match="session boom"):
            pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")

    time.sleep(0.3)
    assert pm._processes.get(root) is None
    assert not pm.ownership.agent_owns(Path(root))

    result = pm.launch(_FakeEngine([sys.executable, str(child)]), root, "go")
    assert result["ok"] is True, f"second launch refused: {result}"
    pm.kill(root)
