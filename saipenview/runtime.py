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
from pathlib import Path
from typing import Literal

# ── Windows Job Object containment (CORE-004) ──────────────────────────────
# On Windows, agents spawned by the app must die when the parent exits.
# A Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ensures the OS
# terminates all processes in the job when the last handle closes.

def _assign_job_object(proc: subprocess.Popen) -> None:
    """Assign *proc* to a kill-on-close Job Object (Windows only).

    Called from launch() so the child cannot outlive the parent on forced
    exit (Task Manager, Ctrl+C, etc.). On non-Windows, this is a no-op.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        # JobObjectInfoClass = 2 (JobObjectBasicLimitInformation)
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return
        limit_info = JOBOBJECT_BASIC_LIMIT_INFORMATION()
        limit_info.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            h_job, 2, ctypes.byref(limit_info),
            ctypes.sizeof(limit_info),
        )
        kernel32.AssignProcessToJobObject(h_job, int(proc.pid))
        # Leak the handle intentionally: closing it would kill the child.
        # The handle lives for the process lifetime.
    except (OSError, AttributeError, ImportError):
        pass

from saipenview.engines.base import AgentEngine
from saipenview.events import event_bus
from saipenview.paths import canonical_key
from saipenview.sessions import SessionStore

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
    # Per-process output lock (T-166): the reader thread appends while
    # get_output/get_status read, and _line_count must never be torn.
    _io_lock: threading.Lock = field(default_factory=threading.Lock)
    # Exactly-once finalization guard (T-166): kill() and the reader thread's
    # EOF tail both reach the finalizer; only the first call may act.
    _finalize_lock: threading.Lock = field(default_factory=threading.Lock)
    _finalized: bool = False
    # Set by kill() before terminate() so the finalizer labels a deliberate
    # stop as "killed" even when the reader thread's EOF tail gets there first.
    _kill_intent: bool = False
    # PERF-009: cached psutil.Process for CPU/memory metrics.
    _psutil_proc: object | None = None  # psutil.Process or None

    def elapsed_seconds(self) -> float:
        """Return seconds since launch (or total if finished)."""
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()


class ProcessManager:
    """Manages agent subprocesses across all projects.

    Enforces one agent per project (SAIPEN §1.4).  Captures stdout/stderr
    in a rolling deque and publishes events for real-time UI.

    Single-writer ownership (T-183 + the repair mission): the launch
    reservation lives in the SAME per-root lock the write coordinator
    mutates under. A launch that reserved the root blocks every app protocol
    mutation; an app transaction that is mid-flight refuses the launch. The
    reservation is held from the launch decision until the process finalizes.
    """

    def __init__(
        self,
        buffer_size: int = DEFAULT_OUTPUT_BUFFER_SIZE,
        ownership=None,
    ) -> None:
        self._lock = threading.Lock()
        # Keyed by canonical_key(project_root) so one project -- however its
        # path is spelled -- maps to exactly one process (T-166).
        self._processes: dict[str, AgentProcess] = {}
        self._buffer_size = buffer_size
        self.sessions = SessionStore()
        if ownership is None:
            from saipenview.protocol_write import get_coordinator

            ownership = get_coordinator().ownership
        self.ownership = ownership

    def _key(self, project_root: str) -> str:
        return canonical_key(project_root)

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
        key = self._key(project_root)
        with self._lock:
            existing = self._processes.get(key)
            if existing and existing.status == "running":
                return {
                    "ok": False,
                    "error": f"Agent already running on {project_root} "
                    f"(engine={existing.engine.name}, "
                    f"elapsed={existing.elapsed_seconds():.0f}s)",
                }
        # Reservation is the ATOMIC ownership decision: checked and marked
        # under the same per-root lock the write coordinator mutates under.
        # A UI mutation in flight makes this refuse; a successful reservation
        # makes every later mutation refuse. Refusal also covers a second
        # launch for the same root (one reservation per root, ever).
        if not self.ownership.reserve_agent(Path(project_root)):
            return {
                "ok": False,
                "error": (
                    f"Agent already running/launching on {project_root}, or an "
                    f"app protocol transaction is active on it; launch refused "
                    f"-- retry when the write finishes"
                ),
            }

        try:
            try:
                cmd = engine.build_command(project_root, instruction)
            except ValueError as exc:
                # T-168: an engine rejects an empty/invalid command with a
                # clear error instead of launching garbage.
                self.ownership.release_agent(Path(project_root))
                return {"ok": False, "error": str(exc)}

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
                    stdin=subprocess.PIPE
                    if engine.supports_stdin
                    else subprocess.DEVNULL,
                    env=env,
                    text=True,
                    bufsize=1,  # line-buffered
                    encoding="utf-8",
                    errors="replace",
                )
            except (OSError, subprocess.SubprocessError) as exc:
                print(
                    f"SAIPENVIEW: failed to launch {engine.name}: {exc}",
                    file=sys.stderr,
                )
                self.ownership.release_agent(Path(project_root))
                return {"ok": False, "error": str(exc)}

            # CORE-004: Windows Job Object containment -- child dies when
            # the parent exits, no matter how (Task Manager, Ctrl+C, etc.).
            _assign_job_object(proc)

            ap = AgentProcess(
                engine=engine,
                project_root=project_root,
                instruction=instruction,
                process=proc,
                output_lines=deque(maxlen=self._buffer_size),
            )

            record = self.sessions.start(
                project_root,
                engine.name,
                engine.display_name,
                instruction,
                pid=proc.pid,
            )
            if record is not None:
                ap.run_id = record.run_id

            with self._lock:
                self._processes[key] = ap

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

            return {"ok": True, "engine": engine.name, "pid": proc.pid}
        except Exception:  # noqa: BLE001 - reservation must not leak on any path
            # CORE-004: if the child was already spawned (e.g. sessions.start
            # failed), we MUST kill/reap it before releasing ownership --
            # otherwise the original agent process is still alive while a
            # second writer could now claim the project.
            try:
                if proc.poll() is None:  # still alive
                    proc.kill()
                    proc.wait(timeout=5)
            except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass
            self.ownership.release_agent(Path(project_root))
            raise

    def kill(self, project_root: str) -> dict:
        """Kill a running agent process."""
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
        if not ap:
            return {"ok": False, "error": "No agent process found"}
        if ap.status != "running":
            return {"ok": False, "error": f"Agent is not running (status={ap.status})"}

        # Record the INTENT before terminating, not after. terminate() makes
        # stdout hit EOF, so the reader thread's tail can run and reach the
        # finalizer before this method does -- and it must still label the run
        # "killed", never "failed" (T-166).
        with ap._io_lock:
            ap._kill_intent = True
            ap.status = "killed"
        try:
            ap.process.terminate()
            # Give it 3s to die gracefully, then force kill.
            try:
                ap.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ap.process.kill()
                try:
                    ap.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Killed but the OS has not reaped it yet. That is not a
                    # failed kill -- it is a slow reap -- so do not roll the
                    # status back to running; the finalizer still runs and the
                    # wait above never leaks out of a "raises nothing" method.
                    print(
                        f"SAIPENVIEW: process {ap.process.pid} slow to reap after kill",
                        file=sys.stderr,
                    )
        except (OSError, subprocess.SubprocessError) as exc:
            with ap._io_lock:
                ap._kill_intent = False
                ap.status = "running"  # still alive; the kill is what failed
            print(f"SAIPENVIEW: kill agent failed: {exc}", file=sys.stderr)
            return {"ok": False, "error": str(exc)}

        self._finalize(ap, requested_status="killed")
        return {"ok": True}

    def _finalize(self, ap: AgentProcess, requested_status: str | None = None) -> None:
        """Exactly-once completion: exit_code, finished_at, transcript close,
        one agent.finished publish, reservation cleared (T-166).

        Idempotent and guarded: kill() and the reader thread's EOF tail both
        reach it, and whichever wins, the other is a no-op. Never touches the
        project watcher -- that ownership moves to the Api registry (T-124).

        CORE-004: terminal status and ownership release require proven OS
        process death (poll/wait returning non-None returncode). If the
        process is still alive after the wait window, a background reaper
        thread handles the delayed release so that ownership is never
        released while the agent is still running.
        """
        with ap._finalize_lock:
            if ap._finalized:
                return
            ap._finalized = True

        # Wait for proven death. Give it a reasonable window, but do NOT
        # give up if it takes longer -- instead schedule a background reaper.
        try:
            ap.process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        exit_code = ap.process.returncode
        if requested_status is not None:
            status = requested_status
        elif ap._kill_intent:
            status = "killed"
        else:
            status = "done" if exit_code == 0 else "failed"

        with ap._io_lock:
            ap.exit_code = exit_code
            ap.finished_at = datetime.now(timezone.utc)
            ap.status = status
            ap._psutil_proc = None  # PERF-009: release cached handle

        if ap.run_id:
            self.sessions.finish(ap.run_id, status, exit_code)

        # CORE-004: only release ownership when process death is PROVEN.
        # If returncode is None the OS hasn't reaped the child yet -- we
        # must not release ownership because the agent is still alive and
        # could still be writing protocol files.
        if exit_code is not None:
            self.ownership.release_agent(Path(ap.project_root))
        else:
            # Schedule a background reaper: poll periodically until the
            # process is truly dead, then release ownership.
            def _delayed_reaper(proc=ap.process, root=ap.project_root,
                               interval=0.5, max_wait=30.0):
                elapsed = 0.0
                while elapsed < max_wait:
                    try:
                        proc.wait(timeout=interval)
                    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                        pass
                    if proc.returncode is not None:
                        self.ownership.release_agent(Path(root))
                        return
                    elapsed += interval
                # Last resort: force kill and release.
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                    pass
                self.ownership.release_agent(Path(root))

            threading.Thread(target=_delayed_reaper, daemon=True,
                            name="reaper-" + ap.engine.name).start()

        event_bus.publish(
            "agent.finished",
            {
                "root": ap.project_root,
                "engine": ap.engine.name,
                "status": status,
                "exit_code": exit_code,
                "elapsed": ap.elapsed_seconds(),
            },
        )

    def send_input(self, project_root: str, text: str) -> dict:
        """Send text to a running agent's stdin."""
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
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
            # Single framing owner (T-167): the backend strips trailing CR/LF
            # and adds exactly one \n, so the frontend sends clean text and the
            # wire always carries one final newline. Multiline input keeps its
            # internal newlines. Empty input is refused.
            text = text.rstrip("\r\n")
            if not text.strip():
                return {"ok": False, "error": "input is empty"}
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
            Dict with 'lines', 'total' (cumulative line count), 'status',
            'first_available' (earliest line still buffered), 'next_since'
            (the cursor the caller MUST store for the next poll -- never
            old_since + len(lines), which breaks on buffer rollover), and
            'dropped_count' (lines skipped because the rolling window had
            already evicted them).
        """
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
        if not ap:
            return {
                "lines": [],
                "total": 0,
                "status": "none",
                "first_available": 0,
                "next_since": 0,
                "dropped_count": 0,
            }

        with ap._io_lock:
            total = ap._line_count
            buf_len = len(ap.output_lines)
            status = ap.status
            # PERF-006: check if there's new data before copying anything.
            first_available = total - buf_len
            if since_line >= total:
                return {
                    "lines": [],
                    "total": total,
                    "status": status,
                    "first_available": first_available,
                    "next_since": total,
                    "dropped_count": max(0, first_available - since_line),
                }
            # Only copy the suffix we need, not the whole buffer.
            start = max(since_line, first_available)
            offset = start - first_available
            lines = list(ap.output_lines)[offset:]

        first_available = total - buf_len
        dropped = max(0, first_available - since_line)

        return {
            "lines": lines,
            "total": total,
            "status": status,
            "first_available": first_available,
            "next_since": total,
            "dropped_count": dropped,
        }

    def get_status(self, project_root: str) -> dict:
        """Return status info for an agent process."""
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
        if not ap:
            return {"status": "none"}

        cpu_percent = 0.0
        memory_mb = 0.0
        try:
            import psutil

            if ap.process and ap.status == "running":
                # PERF-009: reuse cached psutil.Process to avoid resetting
                # CPU metric on every poll; create/prime once, then reuse.
                p = ap._psutil_proc
                if p is None:
                    p = psutil.Process(ap.process.pid)
                    p.cpu_percent(interval=None)  # prime
                    ap._psutil_proc = p
                cpu_percent = p.cpu_percent(interval=None)
                memory_mb = p.memory_info().rss / (1024 * 1024)
        except Exception:
            # W2-014: catch psutil.NoSuchProcess/AccessDenied (psutil.Error) and
            # OSError alike. Degrade only CPU/RAM to 0.0; never let a metrics
            # race determine lifecycle status.
            cpu_percent = 0.0
            memory_mb = 0.0
            ap._psutil_proc = None

        with ap._io_lock:
            total_lines = ap._line_count

        return {
            "status": ap.status,
            "engine": ap.engine.name,
            "engine_display": ap.engine.display_name,
            "instruction": ap.instruction[:200],
            "started_at": ap.started_at.isoformat(),
            "elapsed": ap.elapsed_seconds(),
            "exit_code": ap.exit_code,
            "total_lines": total_lines,
            "pid": ap.process.pid if ap.process else None,
            "cpu_percent": round(cpu_percent, 1),
            "memory_mb": round(memory_mb, 1),
        }

    def list_running(self) -> list[dict]:
        """Return status dicts for only live/stopping agent processes.

        W2-009: finalized done/failed/killed records are excluded so the
        running count does not grow over a session. Their history remains
        accessible via get_status and SessionStore.
        """
        with self._lock:
            roots = [
                r for r, ap in self._processes.items()
                if ap.status in ("running",)
            ]
        return [{**self.get_status(r), "root": r} for r in roots]

    def is_running(self, project_root: str) -> bool:
        """True when a Core agent process is live (or launching) for *root*.

        The write coordinator refuses direct protocol mutation for a project
        an agent owns (T-183): SAIPENVIEW must never become writer #2 while
        the agent it launched is mutating the same `.saipen/` files. The
        reservation lives in the shared RootOwnership, so this reads the same
        state the coordinator's authoritative guard enforces."""
        return self.ownership.agent_owns(Path(project_root))

    def stop_all(self) -> None:
        """Kill all running agents.  Called on app shutdown."""
        with self._lock:
            roots = [r for r, ap in self._processes.items() if ap.status == "running"]
        for root in roots:
            self.kill(root)

    def _read_output(self, ap: AgentProcess) -> None:
        """Background thread: read stdout line by line, store + publish."""
        try:
            for raw_line in ap.process.stdout:
                line = raw_line.rstrip("\n\r")
                # W2-010: bound one logical output record in live memory.
                if len(line) > 65536:
                    line = line[:65536] + " [... truncated]"
                with ap._io_lock:
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

        self._finalize(ap)
