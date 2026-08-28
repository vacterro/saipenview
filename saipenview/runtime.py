"""Agent process manager.

Manages the lifecycle of agent subprocesses: launch, monitor stdout,
kill, send stdin.  Enforces SAIPEN §1.4's one-agent-per-project rule.

The manager captures agent output in a rolling buffer and publishes
events to the event bus for real-time UI updates.
"""

from __future__ import annotations

import codecs
import itertools
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

def _close_saipen_job_handle(proc) -> None:
    """W2-033: close the Job Object handle stashed on *proc*, if any.

    Platform-safe: on non-Windows _saipen_job_handle is never set, so this
    is a no-op. On Windows we use the same ctypes kernel32 path as
    _assign_job_object; if kernel32 is unavailable we silently ignore —
    the OS reclaims all handles on process exit anyway.
    """
    job_handle = getattr(proc, "_saipen_job_handle", None)
    if job_handle is None:
        return
    try:
        delattr(proc, "_saipen_job_handle")
    except AttributeError:
        pass
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        HANDLE = wintypes.HANDLE
        kernel32.CloseHandle(HANDLE(job_handle))
    except (OSError, ValueError, AttributeError):
        pass


def _assign_job_object(proc: subprocess.Popen) -> None:
    """Assign *proc* to a kill-on-close Job Object (Windows only).

    Called from launch() so the child cannot outlive the parent on forced
    exit (Task Manager, Ctrl+C, etc.). On non-Windows, this is a no-op.

    CORE-002: ``AssignProcessToJobObject`` takes a process *HANDLE*, not a
    process *ID*. The previous code passed ``int(proc.pid)``, which is
    silently wrong on 64-bit Windows (the low bits of a HANDLE rarely equal
    a PID, so the API failed and the crash-containment never engaged). We
    now declare the real kernel32 signatures, pass the child's actual
    HANDLE (``Popen._handle``), verify every call, and keep the Job handle
    alive on the process object for the parent's lifetime.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # Declare real signatures so pointer-sized arguments are marshalled
        # correctly on 64-bit Windows (untyped calls default every arg/retval
        # to a 32-bit int, which silently corrupts HANDLE values).
        HANDLE = wintypes.HANDLE
        BOOL = wintypes.BOOL
        DWORD = wintypes.DWORD
        LPVOID = wintypes.LPVOID
        kernel32.CreateJobObjectW.restype = HANDLE
        kernel32.CreateJobObjectW.argtypes = [LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = BOOL
        kernel32.SetInformationJobObject.argtypes = [HANDLE, DWORD, LPVOID, DWORD]
        kernel32.AssignProcessToJobObject.restype = BOOL
        kernel32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
        kernel32.CloseHandle.restype = BOOL
        kernel32.CloseHandle.argtypes = [HANDLE]
        kernel32.GetLastError.restype = DWORD

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
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            # IO_COUNTERS is six ULONGLONGs; BasicLimitInformation carries
            # LimitFlags. KILL_ON_JOB_CLOSE lives in LimitFlags.
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", ctypes.c_int64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return
        # Use JobObjectExtendedLimitInformation (class 9): on current Windows
        # the basic-limit class (2) is rejected with ERROR_INVALID_PARAMETER,
        # which silently dropped KILL_ON_JOB_CLOSE and left children orphaned
        # after a forced parent exit (T-562, CORE-004).
        limit_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limit_info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            h_job, 9, ctypes.byref(limit_info), ctypes.sizeof(limit_info)
        ):
            # Setup failed -- close the Job handle rather than leaking a
            # half-configured object.
            kernel32.CloseHandle(h_job)
            return
        # Pass the child's REAL process HANDLE, not its PID. Popen keeps the
        # raw Win32 handle in ``_handle``; fall back to an OpenProcess handle
        # only if that attribute is somehow unavailable.
        handle_attr = getattr(proc, "_handle", None)
        open_proc_handle = None  # W2-033: tracks OpenProcess-created HANDLE
        if handle_attr is None:
            kernel32.OpenProcess.restype = HANDLE
            kernel32.OpenProcess.argtypes = [DWORD, BOOL, wintypes.DWORD]
            open_proc_handle = kernel32.OpenProcess(0x1F0FFF, False, int(proc.pid))
        if open_proc_handle is not None:
            proc_handle = HANDLE(open_proc_handle)
        else:
            proc_handle = HANDLE(int(handle_attr))
        if not kernel32.AssignProcessToJobObject(h_job, proc_handle):
            kernel32.CloseHandle(h_job)
            if open_proc_handle:
                kernel32.CloseHandle(open_proc_handle)
            return
        # W2-033: AssignProcessToJobObject steals a reference to proc_handle;
        # our OpenProcess-created copy is no longer needed -- close it now so
        # the only surviving handles are h_job (kept on proc) and the OS-owned
        # one inside the job.
        if open_proc_handle:
            kernel32.CloseHandle(open_proc_handle)
            open_proc_handle = None
        # Keep the Job handle alive for the parent's lifetime: closing it would
        # kill the child. Stash it on the process object so a future explicit
        # teardown can release it deliberately.
        try:
            proc._saipen_job_handle = h_job  # type: ignore[attr-defined]
        except Exception:
            # If assignment is impossible, the handle simply lives until the
            # process exits (KILL_ON_JOB_CLOSE still engaged).
            pass
    except (OSError, AttributeError, ImportError, ValueError):
        pass

from saipenview.engines.base import AgentEngine
from saipenview.events import event_bus
from saipenview.paths import canonical_key
from saipenview.sessions import SessionStore

# Maximum lines to keep in the per-process output buffer.
DEFAULT_OUTPUT_BUFFER_SIZE = 5000

# T-597 / PERF-008: one logical stdout record is capped while it is being
# READ, not after an unbounded string already exists -- a child that emits a
# multi-megabyte record without a newline must not spike the reader's memory.
OUTPUT_RECORD_MAX_CHARS = 65536
_OUTPUT_TRUNCATION_MARKER = " [... truncated]"
# One os.read syscall worth of bytes per iteration; short reads preserve
# latency (the reader never waits for a full chunk before emitting a line).
_OUTPUT_READ_CHUNK_BYTES = 8192
# Decoding happens in slices no larger than this so a large read never
# materializes as one huge decoded string (PERF-008's whole point).
_OUTPUT_DECODE_SLICE_BYTES = 4096


def _bounded_output_lines(
    stream,
    *,
    limit: int = OUTPUT_RECORD_MAX_CHARS,
    chunk_bytes: int = _OUTPUT_READ_CHUNK_BYTES,
):
    """Yield newline-framed logical records from a binary stdout stream.

    Records are capped at *limit* characters DURING accumulation: an oversized
    record yields exactly one truncated line plus one `` [... truncated]``
    marker, and its remaining bytes are discarded until the next newline.
    Peak memory is bounded by chunk size + limit regardless of record length.

    Decoding uses an incremental UTF-8 decoder with ``errors="replace"``,
    matching the previous TextIOWrapper(encoding="utf-8", errors="replace")
    contract, including multibyte sequences split across chunk boundaries and
    a trailing record with no final newline. Trailing ``\\r`` characters are
    stripped per record (CRLF output reads exactly as before).
    """
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    parts: list[str] = []
    length = 0
    overflow = False
    # Completed records waiting to be handed to the caller by the read loop.
    ready: deque[str] = deque()

    def _emit() -> str:
        nonlocal parts, length, overflow
        line = "".join(parts).rstrip("\r")
        if overflow:
            line += _OUTPUT_TRUNCATION_MARKER
        parts = []
        length = 0
        overflow = False
        return line

    def _consume(text: str) -> None:
        nonlocal length, overflow
        if overflow:
            return
        room = limit - length
        if room > 0:
            take = text[:room]
            parts.append(take)
            length += len(take)
        if len(text) > room:
            overflow = True

    def _frame(text: str) -> None:
        start = 0
        while start < len(text):
            nl = text.find("\n", start)
            if nl == -1:
                _consume(text[start:])
                break
            _consume(text[start:nl])
            ready.append(_emit())
            start = nl + 1

    while True:
        chunk = stream.read(chunk_bytes)
        if not chunk:
            break
        for i in range(0, len(chunk), _OUTPUT_DECODE_SLICE_BYTES):
            text = decoder.decode(chunk[i : i + _OUTPUT_DECODE_SLICE_BYTES])
            if text:
                _frame(text)
            while ready:
                yield ready.popleft()
    # EOF: flush any pending partially-decoded bytes, then emit a trailing
    # record that lacked its final newline (old TextIOWrapper behavior).
    tail = decoder.decode(b"", final=True)
    if tail:
        _frame(tail)
    while ready:
        yield ready.popleft()
    if parts or overflow:
        yield _emit()

# PERF-009: live-output arrival is announced through at most one coalesced
# "agent.output_available" event per root per interval -- never one event per
# stdout line. The default production path publishes nothing at all: with no
# subscribers the reader thread builds no payloads, and the UI follows its own
# single-flight cursor poll instead.
OUTPUT_NOTIFY_INTERVAL_SECONDS = 0.25


class _OutputNotifier:
    """Coalesces output arrivals into bounded-cadence root notifications.

    ``touch(root)`` is called per line by the reader thread; at most one
    daemon timer per root is alive at any moment, so a burst of thousands of
    lines collapses into <= 4 notifications per second for that root. When
    nothing listens to the coalesced (or legacy per-line) event, ``touch``
    allocates nothing.
    """

    def __init__(
        self,
        bus=event_bus,
        interval: float = OUTPUT_NOTIFY_INTERVAL_SECONDS,
    ) -> None:
        self._bus = bus
        self._interval = interval
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def touch(self, root: str) -> None:
        if not self._bus.has_subscribers("agent.output_available"):
            return
        with self._lock:
            if root in self._timers:
                return
            t = threading.Timer(self._interval, self._fire, args=(root,))
            t.daemon = True
            self._timers[root] = t
            t.start()

    def _fire(self, root: str) -> None:
        with self._lock:
            self._timers.pop(root, None)
        if self._bus.has_subscribers("agent.output_available"):
            self._bus.publish("agent.output_available", {"root": root})

    def cancel(self, root: str | None = None) -> None:
        """Cancel the pending timer for *root* (or all roots)."""
        with self._lock:
            keys = [root] if root is not None else list(self._timers)
            timers = [self._timers.pop(k, None) for k in keys]
        for t in timers:
            if t is not None:
                t.cancel()


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
    # CORE-002: prevents double-reaper scheduling when two concurrent
    # _finalize calls both see exit_code=None.
    _reaper_scheduled: bool = False

    def elapsed_seconds(self) -> float:
        """Return seconds since launch (or total if finished)."""
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()



def _schedule_reaper(registry, ap, status):
    """Background reaper: prove death BEFORE releasing ownership.

    CORE-002: returns None (unproven death) must never trigger
    ownership release or session finish until proc.returncode is non-None.
    """
    reaper_key = registry._key(ap.project_root)

    def _delayed_reaper(proc=ap.process, root=ap.project_root, rkey=reaper_key,
                        kill_intent=ap._kill_intent,
                        interval=0.5, max_wait=120.0):
        elapsed = 0.0
        while elapsed < max_wait:
            try:
                proc.wait(timeout=interval)
            except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass
            if proc.returncode is None:
                continue  # still waiting
            # CORE-002: Death proven. Route back through _finalize for the
            # single terminal commit (exit_code, finished_at, session finish,
            # ownership release, agent.finished event). Never manually release
            # ownership here -- _finalize owns that path.
            registry._finalize(ap)
            return
            # Still alive. CORE-004: only force-kill when there was an
            # explicit kill/shutdown intent. An output-EOF with no kill
            # intent must NOT trigger a kill -- the agent is simply
            # still working. Without intent we keep waiting for natural
            # death and retain ownership so a live agent is never handed
            # to a second writer.
            if kill_intent:
                try:
                    proc.kill()
                except (OSError, subprocess.SubprocessError):
                    # Kill failed -- cannot prove death. Keep ownership
                    # and mark stuck; keep polling on the next iter.
                    with registry._lock:
                        registry._stuck_agents.add(rkey)
            else:
                # No kill intent: do not release ownership of a process
                # we cannot prove is dead. Keep it flagged so a later
                # launch/write for this root is refused until it dies.
                with registry._lock:
                    registry._stuck_agents.add(rkey)
            elapsed += interval
        # Exceeded max_wait without proven death: keep the reservation
        # and leave the stuck flag set rather than releasing a live agent.
        with registry._lock:
            registry._stuck_agents.add(rkey)

    with ap._finalize_lock:
        if ap._reaper_scheduled:
            return  # CORE-002: prevent double-reaper
        ap._reaper_scheduled = True
    threading.Thread(target=_delayed_reaper, daemon=True,
                     name="reaper-" + ap.engine.name).start()


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
        # CORE-002: roots whose agent process could not be reaped. The
        # reservation is deliberately retained (never released while liveness is
        # unresolved) so a second writer cannot claim a possibly-live project.
        self._stuck_agents: set[str] = set()
        # PERF-009: coalesced output-availability notifications (no-op unless
        # something subscribes to "agent.output_available").
        self._output_notifier = _OutputNotifier()

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

        proc = None
        try:
            try:
                cmd = engine.build_command(project_root, instruction)
            except Exception as exc:
                # CORE-003: build_command (or any pre-spawn prep) may raise any
                # exception, not just ValueError. A pre-spawn failure must
                # release the reservation and return the structured error -- it
                # must never leak ownership or mask the original cause.
                self.ownership.release_agent(Path(project_root))
                return {"ok": False, "error": f"engine build failed: {exc}"}

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
                    # PERF-008: stdout is read as bounded binary chunks with an
                    # incremental decoder (see _bounded_output_lines) so an
                    # oversized record can never materialize in full.
                    bufsize=0,
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

            # CORE-004: a dedicated process-exit monitor owns process-lifecycle
            # finalization. It waits for the REAL OS exit (not output EOF), so a
            # child that closes its output handles but keeps running is never
            # marked finished or force-killed. kill() and reader-EOF no longer
            # finalize -- this monitor does, exactly once (idempotent).
            monitor = threading.Thread(
                target=self._exit_monitor,
                args=(ap,),
                daemon=True,
                name=f"agent-exit-{engine.name}",
            )
            monitor.start()

            event_bus.publish(
                "agent.started",
                {
                    "root": project_root,
                    "engine": engine.name,
                    "instruction": instruction,
                },
            )

            return {"ok": True, "engine": engine.name, "pid": proc.pid, "run_id": ap.run_id}
        except Exception:  # noqa: BLE001 - reservation must not leak on any path
            # CORE-003: a post-spawn setup failure (e.g. sessions.start) left a
            # live child. Reap it BEFORE releasing ownership. If reaping fails
            # (death unproven, CORE-002), RETAIN the reservation -- a possibly
            # live agent must not lose exclusive ownership to a second writer.
            try:
                if proc is not None and proc.poll() is None:  # still alive
                    proc.kill()
                    proc.wait(timeout=5)
            except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                raise
            # W2-012: if we got far enough to insert ap into _processes but then
            # hit a post-spawn failure (reader/monitor Thread.start, event publish),
            # the dict still holds a running-entry that blocks every later launch.
            # Remove it now that death is proven so the next launch sees a clean slate.
            with self._lock:
                self._processes.pop(key, None)
            self.ownership.release_agent(Path(project_root))
            raise

    def is_stuck(self, project_root: str) -> bool:
        """CORE-002: True when a launched agent could not be reaped and its
        reservation is being retained (rather than released) to avoid handing a
        possibly-live project to a second writer."""
        with self._lock:
            return self._key(project_root) in self._stuck_agents

    def kill(self, project_root: str, expected_run_id: str | None = None) -> dict:
        """Kill a running agent process.

        W2-026: if *expected_run_id* is provided, reject the kill when the
        active process has a different run_id (delayed stop for old run R1
        must not kill new run R2 on the same root).
        """
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
        if not ap:
            return {"ok": False, "error": "No agent process found"}
        if ap.status != "running":
            return {"ok": False, "error": f"Agent is not running (status={ap.status})"}
        # W2-026: run-aware target identity
        if expected_run_id is not None and ap.run_id != expected_run_id:
            return {
                "ok": False,
                "code": "RUN_STALE",
                "error": f"expected run_id={expected_run_id}, active={ap.run_id}",
            }

        # Record the INTENT before terminating, not after. terminate() makes
        # stdout hit EOF, so the reader thread's tail can run and reach the
        # finalizer before this method does -- and it must still label the run
        # "killed", never "failed" (T-166).
        # CORE-002: only set _kill_intent here. The terminal "killed" status
        # is derived in _finalize after proven death, so a still-live
        # slow-to-die process remains visible to list_running/stop_all.
        with ap._io_lock:
            ap._kill_intent = True
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
            # Do NOT mark finalized until process death is proven below.
            # Setting _finalized here lets kill() and _exit_monitor() race
            # into a double-finalize; the guard below re-checks after proven
            # death so only the winning path actually flips the flag.

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

        if exit_code is None:
            # CORE-002: Death unproven. Do NOT set _finalized=True here --
            # the reaper will route back through _finalize when it proves
            # death, and _exit_monitor may also reach here on retry. Setting
            # _finalized now would permanently consume the exactly-once token
            # before finalization occurs.
            _schedule_reaper(self, ap, status)
            return

        # Proven death: commit the terminal transition.
        with ap._finalize_lock:
            if ap._finalized:
                return
            ap._finalized = True

        with ap._io_lock:
            ap.exit_code = exit_code
            ap.finished_at = datetime.now(timezone.utc)
            ap.status = status
            ap._psutil_proc = None  # PERF-009: release cached handle

        # Drain the output reader before closing the transcript: the reader
        # thread may still be appending the tail of stdout when the OS-exit
        # monitor (or kill()) reaches finalize, and sessions.finish() pops the
        # transcript entry -- lines not yet appended would be lost from disk
        # while already present in the live buffer. T-562's verify surfaced this
        # race once the child entered a Job Object and shifted the timing.
        rt = ap._reader_thread
        if rt is not None and rt is not threading.current_thread() and rt.is_alive():
            rt.join(timeout=10)

        if ap.run_id:
            self.sessions.finish(ap.run_id, status, exit_code)

        # PERF-009: a pending availability timer for a finalized run is stale
        # -- cancel it so a dead root never fires a notification afterwards.
        self._output_notifier.cancel(ap.project_root)

        # W2-033: close the Job Object handle exactly once during finalization.
        # KILL_ON_JOB_CLOSE means the child dies when the last handle closes,
        # but by this point the child is already dead (returncode is non-None),
        # so closing here prevents the handle from leaking for the lifetime of
        # the Popen object (which may outlive this ProcessManager).
        _close_saipen_job_handle(ap.process)

        # CORE-004: only release ownership when process death is PROVEN.
        # If returncode is None the OS hasn't reaped the child yet -- we
        # must not release ownership because the agent is still alive and
        # could still be writing protocol files.
        if exit_code is not None:
            self.ownership.release_agent(Path(ap.project_root))
        else:
            # CORE-002: the process is still alive (returncode None). Spin a
            # background reaper that proves death BEFORE releasing ownership.
            # It must never release while liveness is unresolved: if the kill
            # fails, ownership is retained and the root flagged stuck so a
            # later launch/write for it is refused until it truly dies.
            _schedule_reaper(self, ap, status)

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

        # PERF-007: compact the terminal entry to release the output deque
        # (~2-4 MiB), Popen handles, and thread reference.  History is
        # already persisted in SessionStore.
        self._compact_terminal(ap)


    def _compact_terminal(self, ap: AgentProcess) -> None:
        """PERF-007: release heavyweight resources from a finalized process.

        After proven terminalization the output deque, Popen handle, reader
        thread, and psutil cache are no longer needed -- history lives in
        SessionStore and the process is confirmed dead.  The entry stays in
        _processes so get_status() and get_output() still resolve (returning
        cached totals and empty line lists), but the ~2-4 MiB per-process
        memory footprint drops to near zero.
        """
        with ap._io_lock:
            ap.output_lines.clear()
            ap._psutil_proc = None
        ap._reader_thread = None
        # Release the Popen object so its file descriptors and OS handles
        # are reclaimed promptly rather than waiting for GC.
        ap.process = None  # type: ignore[assignment]

    def send_input(self, project_root: str, text: str, expected_run_id: str | None = None) -> dict:
        """Send text to a running agent's stdin."""
        key = self._key(project_root)
        with self._lock:
            ap = self._processes.get(key)
        if not ap:
            return {"ok": False, "error": "No agent process found"}
        if ap.status != "running":
            return {"ok": False, "error": f"Agent is not running (status={ap.status})"}
        # W2-026: run-aware target identity
        if expected_run_id is not None and ap.run_id != expected_run_id:
            return {
                "ok": False,
                "code": "RUN_STALE",
                "error": f"expected run_id={expected_run_id}, active={ap.run_id}",
            }
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
            # PERF-008: stdin is a binary pipe now (unbuffered, matching the
            # bounded stdout reader); the wire contract stays UTF-8 + "\n".
            ap.process.stdin.write((text + "\n").encode("utf-8"))
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
            run_id = ap.run_id
            # PERF-006: check if there's new data before copying anything.
            first_available = total - buf_len
            if since_line >= total:
                return {
                    "lines": [],
                    "total": total,
                    "status": status,
                    "run_id": run_id,
                    "first_available": first_available,
                    "next_since": total,
                    "dropped_count": max(0, first_available - since_line),
                }
            # Only copy the suffix we need, not the whole buffer.
            start = max(since_line, first_available)
            offset = start - first_available
            lines = list(itertools.islice(ap.output_lines, offset, None))
            dropped = max(0, first_available - since_line)

        return {
            "lines": lines,
            "total": total,
            "status": status,
            "run_id": run_id,
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
            "run_id": ap.run_id,
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

    def _exit_monitor(self, ap: AgentProcess) -> None:
        """Wait for the process's real OS exit, then finalize exactly once.

        CORE-004: this thread -- not the output reader -- owns lifecycle
        completion. Output-EOF only ends the reader; process death is proven
        here by blocking on ``proc.wait()``. The exit may take hours for a
        long-lived agent; that is fine for a daemon thread. kill() and the
        reader reaching EOF never finalize, so a child that closed its output
        handles but is still alive is neither marked finished nor force-killed.
        """
        try:
            ap.process.wait()
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass
        self._finalize(ap)

    def _read_output(self, ap: AgentProcess) -> None:
        """Background thread: read stdout in bounded records, store + publish."""
        try:
            for line in _bounded_output_lines(ap.process.stdout):
                with ap._io_lock:
                    ap.output_lines.append(line)
                    ap._line_count += 1
                # The deque is a 5000-line rolling window; this is the copy
                # that survives the window rolling over AND the app closing.
                if ap.run_id:
                    self.sessions.append(ap.run_id, line)

                # PERF-009: event work only for real listeners. The default
                # production path has no "agent.output" subscriber -- the
                # engine parse + payload dict per line was pure waste there,
                # and the UI follows its own single-flight cursor poll. A
                # legacy subscriber still gets the exact per-line payload;
                # a coalesced listener gets bounded-cadence root notices.
                if event_bus.has_subscribers("agent.output"):
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
                else:
                    self._output_notifier.touch(ap.project_root)

                # Small yield to prevent this thread from starving others
                # when agent produces extremely fast output
                if ap._line_count % 100 == 0:
                    time.sleep(0.001)

        except OSError as exc:
            print(f"SAIPENVIEW: output reader error: {exc}", file=sys.stderr)

        # CORE-004: reaching EOF on the captured output stream is NOT process
        # termination. A valid long-lived agent may close its stdout/stderr and
        # keep running -- finalizing here would mark it finished and (via the
        # reaper) force-kill it. Process-lifecycle completion is owned solely by
        # the exit monitor started in launch() (which waits for real OS exit),
        # so EOF only ends the reader, never the process.
