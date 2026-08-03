"""Agent process manager.

Manages the lifecycle of agent subprocesses: launch, monitor stdout,
kill, send stdin.  Enforces SAIPEN §1.4's one-agent-per-project rule.

The manager captures agent output in a rolling buffer and publishes
events to the event bus for real-time UI updates.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from saipenview.engines.base import AgentEngine
from saipenview.events import event_bus
from saipenview.sessions import SessionStore
from saipenview.watcher import SaipenWatcher

# Maximum lines to keep in the per-process output buffer.
DEFAULT_OUTPUT_BUFFER_SIZE = 5000


@dataclass
class AgentProcess:
    """A running or completed agent subprocess."""

    engine: AgentEngine
    project_root: str
    instruction: str
    process: subprocess.Popen
    status: Literal["running", "done", "failed", "killed"] = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    exit_code: int | None = None
    output_lines: deque[str] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_OUTPUT_BUFFER_SIZE)
    )
    _line_count: int = 0
    _reader_thread: threading.Thread | None = None
    # Set once the SessionStore has a transcript open for this run. None means
    # history could not be written (disk full, read-only _data/) -- the run
    # still proceeds, it just leaves no record.
    run_id: str | None = None

    def elapsed_seconds(self) -> float:
        """Return seconds since launch (or total if finished)."""
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()


class ProcessManager:
    """Manages agent subprocesses across all projects.

    Enforces one agent per project (SAIPEN §1.4).  Captures stdout/stderr
    in a rolling deque and publishes events for real-time UI.
    """

    def __init__(self, buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE) -> None:
        self._lock = threading.Lock()
        self._processes: dict[str, AgentProcess] = {}  # keyed by project_root
        self._buffer_size = buffer_size
        self.watcher = SaipenWatcher()
        self.sessions = SessionStore()

    def launch(
        self,
        engine: AgentEngine,
        project_root: str,
        instruction: str,
    ) -> dict:
        """Launch an agent process for a project.

        Args:
            engine: The AgentEngine to use.
            project_root: Absolute path to the project directory.
            instruction: Prompt/command to send to the agent.

        Returns:
            Status dict with 'ok' bool and 'error' string on failure.

        Raises nothing -- errors are returned in the dict.
        """
        with self._lock:
            existing = self._processes.get(project_root)
            if existing and existing.status == "running":
                return {
                    "ok": False,
                    "error": f"Agent already running on {project_root} "
                    f"(engine={existing.engine.name}, "
                    f"elapsed={existing.elapsed_seconds():.0f}s)",
                }

        cmd = engine.build_command(project_root, instruction)
        env = None
        if engine.default_env:
            import os

            env = {**os.environ, **engine.default_env}

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if engine.supports_stdin else subprocess.DEVNULL,
                env=env,
                text=True,
                bufsize=1,  # line-buffered
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"SAIPENVIEW: failed to launch {engine.name}: {exc}", file=sys.stderr)
            return {"ok": False, "error": str(exc)}

        ap = AgentProcess(
            engine=engine,
            project_root=project_root,
            instruction=instruction,
            process=proc,
            output_lines=deque(maxlen=self._buffer_size),
        )

        record = self.sessions.start(
            project_root, engine.name, engine.display_name, instruction, pid=proc.pid
        )
        if record is not None:
            ap.run_id = record.run_id

        with self._lock:
            self._processes[project_root] = ap

        # Start background reader thread
        reader = threading.Thread(
            target=self._read_output,
            args=(ap,),
            daemon=True,
            name=f"agent-reader-{engine.name}",
        )
        ap._reader_thread = reader
        reader.start()

        event_bus.publish(
            "agent.started",
            {
                "root": project_root,
                "engine": engine.name,
                "instruction": instruction,
            },
        )

        self.watcher.watch(project_root)

        return {"ok": True, "engine": engine.name, "pid": proc.pid}

    def kill(self, project_root: str) -> dict:
        """Kill a running agent process."""
        with self._lock:
            ap = self._processes.get(project_root)
        if not ap:
            return {"ok": False, "error": "No agent process found"}
        if ap.status != "running":
            return {"ok": False, "error": f"Agent is not running (status={ap.status})"}

        # Record the INTENT before terminating, not after. terminate() makes
        # stdout hit EOF immediately, so _read_output's tail can run and finish
        # the session before this method gets another line -- and it read the
        # status to decide what to store. Setting it afterwards left the disk
        # saying "failed" while memory said "killed": a deliberate stop filed
        # as a crash, and the two disagreeing about the same run.
        ap.status = "killed"
        try:
            ap.process.terminate()
            # Give it 3s to die gracefully, then force kill
            try:
                ap.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ap.process.kill()
                ap.process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError) as exc:
            ap.status = "running"  # still alive; the kill is what failed
            print(f"SAIPENVIEW: kill agent failed: {exc}", file=sys.stderr)
            return {"ok": False, "error": str(exc)}

        ap.finished_at = datetime.now(timezone.utc)
        ap.exit_code = ap.process.returncode

        event_bus.publish(
            "agent.finished",
            {
                "root": project_root,
                "engine": ap.engine.name,
                "status": "killed",
                "exit_code": ap.exit_code,
                "elapsed": ap.elapsed_seconds(),
            },
        )

        return {"ok": True}

    def send_input(self, project_root: str, text: str) -> dict:
        """Send text to a running agent's stdin."""
        with self._lock:
            ap = self._processes.get(project_root)
        if not ap:
            return {"ok": False, "error": "No agent process found"}
        if ap.status != "running":
            return {"ok": False, "error": f"Agent is not running (status={ap.status})"}
        if not ap.engine.supports_stdin:
            return {
                "ok": False,
                "error": f"Engine '{ap.engine.name}' does not support stdin",
            }

        try:
            ap.process.stdin.write(text + "\n")
            ap.process.stdin.flush()
        except OSError as exc:
            print(f"SAIPENVIEW: send_input failed: {exc}", file=sys.stderr)
            return {"ok": False, "error": str(exc)}

        return {"ok": True}

    def get_output(self, project_root: str, since_line: int = 0) -> dict:
        """Return new output lines since a given line number.

        Args:
            project_root: Project to query.
            since_line: Return lines after this index (0-based cumulative).

        Returns:
            Dict with 'lines' (list of str), 'total' (cumulative line count),
            'status' of the agent process.
        """
        with self._lock:
            ap = self._processes.get(project_root)
        if not ap:
            return {"lines": [], "total": 0, "status": "none"}

        # The deque is a rolling window.  _line_count is the total
        # cumulative count.  We need to figure out which lines in the
        # deque correspond to since_line..current.
        total = ap._line_count
        buf_len = len(ap.output_lines)
        first_available = total - buf_len  # earliest line still in buffer

        if since_line < first_available:
            # Caller missed some lines (buffer rolled over)
            since_line = first_available

        if since_line >= total:
            return {"lines": [], "total": total, "status": ap.status}

        # Index into deque
        start_idx = since_line - first_available
        new_lines = list(ap.output_lines)[start_idx:]

        return {"lines": new_lines, "total": total, "status": ap.status}

    def get_status(self, project_root: str) -> dict:
        """Return status info for an agent process."""
        with self._lock:
            ap = self._processes.get(project_root)
        if not ap:
            return {"status": "none"}

        cpu_percent = 0.0
        memory_mb = 0.0
        try:
            import psutil

            if ap.process and ap.status == "running":
                p = psutil.Process(ap.process.pid)
                # psutil cpu_percent requires a brief interval to calculate over time.
                # Since we poll, calling it once with interval=None returns the value since last call,
                # which is perfect for polling.
                cpu_percent = p.cpu_percent(interval=None)
                memory_mb = p.memory_info().rss / (1024 * 1024)
        except OSError:
            pass

        return {
            "status": ap.status,
            "engine": ap.engine.name,
            "engine_display": ap.engine.display_name,
            "instruction": ap.instruction[:200],
            "started_at": ap.started_at.isoformat(),
            "elapsed": ap.elapsed_seconds(),
            "exit_code": ap.exit_code,
            "total_lines": ap._line_count,
            "pid": ap.process.pid if ap.process else None,
            "cpu_percent": round(cpu_percent, 1),
            "memory_mb": round(memory_mb, 1),
        }

    def list_running(self) -> list[dict]:
        """Return status dicts for all tracked agent processes."""
        with self._lock:
            roots = list(self._processes.keys())
        return [{**self.get_status(r), "root": r} for r in roots]

    def stop_all(self) -> None:
        """Kill all running agents.  Called on app shutdown."""
        self.watcher.stop()
        with self._lock:
            roots = [r for r, ap in self._processes.items() if ap.status == "running"]
        for root in roots:
            self.kill(root)

    def _read_output(self, ap: AgentProcess) -> None:
        """Background thread: read stdout line by line, store + publish."""
        try:
            for raw_line in ap.process.stdout:
                line = raw_line.rstrip("\n\r")
                ap.output_lines.append(line)
                ap._line_count += 1
                # The deque is a 5000-line rolling window; this is the copy
                # that survives the window rolling over AND the app closing.
                if ap.run_id:
                    self.sessions.append(ap.run_id, line)

                # Try structured parsing via engine
                event = ap.engine.parse_event(line)

                event_bus.publish(
                    "agent.output",
                    {
                        "root": ap.project_root,
                        "engine": ap.engine.name,
                        "line": line,
                        "line_num": ap._line_count,
                        "event": {
                            "kind": event.kind,
                            "text": event.text,
                        }
                        if event
                        else None,
                    },
                )

                # Small yield to prevent this thread from starving others
                # when agent produces extremely fast output
                if ap._line_count % 100 == 0:
                    time.sleep(0.001)

        except OSError as exc:
            print(f"SAIPENVIEW: output reader error: {exc}", file=sys.stderr)

        # Process finished -- wait for exit code
        try:
            ap.process.wait(timeout=5)
        except OSError:
            pass

        ap.exit_code = ap.process.returncode
        ap.finished_at = datetime.now(timezone.utc)
        # Do not overwrite an explicit kill. terminate() makes stdout hit EOF,
        # so this thread wakes up right after kill() has already recorded
        # "killed" -- and a terminated process exits non-zero, so the old
        # unconditional assignment relabelled every deliberate stop as
        # "failed", which reads as the agent having crashed.
        if ap.status != "killed":
            ap.status = "done" if ap.exit_code == 0 else "failed"
        if ap.run_id:
            self.sessions.finish(ap.run_id, ap.status, ap.exit_code)

        event_bus.publish(
            "agent.finished",
            {
                "root": ap.project_root,
                "engine": ap.engine.name,
                "status": ap.status,
                "exit_code": ap.exit_code,
                "elapsed": ap.elapsed_seconds(),
            },
        )

        self.watcher.unwatch(ap.project_root)
