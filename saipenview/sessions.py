"""On-disk record of every agent run.

Before this, an agent's output lived in a `deque(maxlen=5000)` on the
`AgentProcess` object and nowhere else, so closing SAIPENVIEW -- or crashing,
or just letting the machine reboot -- erased both the transcript and the fact
that a run had ever happened. A tool that forgets the session is a terminal
with extra steps.

Layout, one directory per install::

    _data/sessions/
        <run_id>.json     metadata: root, engine, instruction, timings, status
        <run_id>.log      raw transcript, one output line per line

One pair of files per run, no shared index. That is deliberate: an index is a
single file every concurrent run must write, which is exactly the thing that
gets half-written when the power goes out. Listing history means reading the
metadata files, which is cheap at the scale this keeps (`MAX_RUNS_PER_PROJECT`)
and cannot be corrupted by a run that died mid-write -- a broken record is one
unreadable run, not a lost history.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from saipenview.config import config_path
from saipenview.tailio import tail_raw_lines

# Transcripts are kept per project, oldest pruned past this. 50 runs is enough
# to answer "what did it do last night" without turning _data/ into a landfill.
MAX_RUNS_PER_PROJECT = 50

# A runaway agent can print faster than anyone will ever read. Past this the
# transcript stops growing and says so, rather than filling the disk quietly.
MAX_TRANSCRIPT_BYTES = 5 * 1024 * 1024

# W2-010: one logical output record is capped at this many UTF-8 bytes.
# A child emitting a no-newline megabyte record creates one unbounded
# Python string/deque item; this truncates the record and emits a marker.
MAX_OUTPUT_LINE_BYTES = 64 * 1024

# Lines are buffered by the OS and flushed every this many, plus once at
# finish. Flushing every line costs a syscall per line for output nobody is
# reading yet; the exposure is the tail of a transcript if the process is
# killed, which the "interrupted" status already tells the reader about.
_FLUSH_EVERY = 20

_RUN_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def project_key(root: str) -> str:
    """Stable short key for a project root.

    Case- and separator-insensitive, because the same project reached as
    `V:\\proj` and `v:/proj` is one project and must not grow two histories.
    """
    norm = os.path.normcase(os.path.normpath(os.path.abspath(root)))
    # Not a security boundary -- this only has to map one path to one stable
    # directory name, so a short non-cryptographic digest is the right tool.
    return hashlib.sha1(  # noqa: S324
        norm.encode("utf-8", "replace"), usedforsecurity=False
    ).hexdigest()[:10]


def sessions_dir() -> Path:
    """Where transcripts live -- beside config.json, so the app stays portable."""
    return config_path().parent / "sessions"


@dataclass
class SessionRecord:
    """One agent run, as it is stored on disk."""

    run_id: str
    root: str
    project: str
    engine: str
    engine_display: str
    instruction: str
    started_at: str
    status: str = "running"
    finished_at: str | None = None
    exit_code: int | None = None
    line_count: int = 0
    truncated: bool = False
    pid: int | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "root": self.root,
            "project": self.project,
            "engine": self.engine,
            "engine_display": self.engine_display,
            "instruction": self.instruction,
            "started_at": self.started_at,
            "status": self.status,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "line_count": self.line_count,
            "truncated": self.truncated,
            "pid": self.pid,
        }

    @staticmethod
    def from_dict(d: dict) -> SessionRecord:
        return SessionRecord(
            run_id=d.get("run_id", ""),
            root=d.get("root", ""),
            project=d.get("project", ""),
            engine=d.get("engine", ""),
            engine_display=d.get("engine_display", d.get("engine", "")),
            instruction=d.get("instruction", ""),
            started_at=d.get("started_at", ""),
            status=d.get("status", "running"),
            finished_at=d.get("finished_at"),
            exit_code=d.get("exit_code"),
            line_count=int(d.get("line_count") or 0),
            truncated=bool(d.get("truncated")),
            pid=d.get("pid"),
        )


@dataclass
class _OpenTranscript:
    record: SessionRecord
    handle: object | None = None
    bytes_written: int = 0
    since_flush: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    """Append-only transcripts plus a metadata file per run.

    Every public method swallows OSError and keeps going: losing the ability
    to WRITE history must never take down the agent run it is recording.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = Path(base_dir) if base_dir else sessions_dir()
        self._open: dict[str, _OpenTranscript] = {}
        self._lock = threading.Lock()

    # ---- writing ---------------------------------------------------------

    def start(
        self,
        root: str,
        engine: str,
        engine_display: str,
        instruction: str,
        pid: int | None = None,
    ) -> SessionRecord | None:
        """Open a transcript for a new run. Returns None if the disk says no."""
        now = datetime.now(timezone.utc)
        key = project_key(root)
        # Microseconds, not seconds. At one-second resolution two runs started
        # in the same second got the same run_id and silently overwrote each
        # other's metadata and transcript -- which a goal-mode chain launching
        # back-to-back agents hits immediately. Still lexically sortable, which
        # is what history() and _prune() order by.
        stamp = now.strftime("%Y%m%dT%H%M%S%f")
        run_id = _RUN_ID_SAFE.sub("-", f"{stamp}-{key}-{engine}")
        # Microseconds make a collision unlikely, not impossible: two threads
        # can read the same clock tick. Cheap to rule out entirely.
        suffix = 0
        while (self._dir / f"{run_id}.json").exists():
            suffix += 1
            run_id = _RUN_ID_SAFE.sub("-", f"{stamp}-{suffix}-{key}-{engine}")
        record = SessionRecord(
            run_id=run_id,
            root=root,
            project=key,
            engine=engine,
            engine_display=engine_display,
            instruction=instruction,
            started_at=now.isoformat(),
            pid=pid,
        )
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            handle = (self._dir / f"{run_id}.log").open(
                "a", encoding="utf-8", errors="replace", newline="\n"
            )
        except OSError as exc:
            print(
                f"SAIPENVIEW: cannot open transcript for {run_id}: {exc}",
                file=sys.stderr,
            )
            return None
        with self._lock:
            self._open[run_id] = _OpenTranscript(record=record, handle=handle)
        self._write_meta(record)
        self._prune(key)
        return record

    def append(self, run_id: str, line: str) -> None:
        with self._lock:
            entry = self._open.get(run_id)
        if entry is None or entry.handle is None:
            return
        # W2-010: truncate one logical record to MAX_OUTPUT_LINE_BYTES.
        raw_bytes = line.encode("utf-8", errors="replace")
        if len(raw_bytes) > MAX_OUTPUT_LINE_BYTES:
            # Write as much as fits, plus a truncation marker.
            truncated = raw_bytes[:MAX_OUTPUT_LINE_BYTES].decode("utf-8", errors="ignore")
            line = truncated + " [... truncated]"
        with entry.lock:
            if entry.bytes_written >= MAX_TRANSCRIPT_BYTES:
                if not entry.record.truncated:
                    entry.record.truncated = True
                    try:
                        entry.handle.write(
                            f"\n[SAIPENVIEW] transcript capped at "
                            f"{MAX_TRANSCRIPT_BYTES} bytes; later output is not stored\n"
                        )
                        entry.handle.flush()
                    except OSError:
                        pass
                    self._write_meta(entry.record)
                return
            try:
                entry.handle.write(line + "\n")
            except (OSError, ValueError):
                return
            entry.bytes_written += len(line.encode("utf-8", "replace")) + 1
            entry.record.line_count += 1
            entry.since_flush += 1
            if entry.since_flush >= _FLUSH_EVERY:
                entry.since_flush = 0
                try:
                    entry.handle.flush()
                except OSError:
                    pass

    def finish(self, run_id: str, status: str, exit_code: int | None) -> None:
        with self._lock:
            entry = self._open.pop(run_id, None)
        if entry is None:
            return
        with entry.lock:
            if entry.handle is not None:
                try:
                    entry.handle.flush()
                    entry.handle.close()
                except OSError:
                    pass
                entry.handle = None
            entry.record.status = status
            entry.record.exit_code = exit_code
            entry.record.finished_at = datetime.now(timezone.utc).isoformat()
        self._write_meta(entry.record)

    # ---- reading ---------------------------------------------------------

    def history(self, root: str, limit: int = 20) -> list[dict]:
        """Runs for one project, newest first.

        A record still saying `running` that this process does not have open
        belongs to a SAIPENVIEW that died -- report it as `interrupted` rather
        than as an agent that has been working since Tuesday.
        """
        key = project_key(root)
        with self._lock:
            live = set(self._open)
        out = []
        for meta in self._meta_files(key):
            rec = self._read_meta(meta)
            if rec is None:
                continue
            if rec.status == "running" and rec.run_id not in live:
                rec.status = "interrupted"
            # started_at alone can tie: two runs started in the same clock
            # tick (datetime.now() resolution under load) then sort back to
            # the stable _meta_files order, which is alphabetical by run_id --
            # aider before gemini regardless of which came second, and the
            # newer run loses last_run. Break the tie by file mtime (creation
            # order): the second run's meta file was written after the first's.
            try:
                mtime = meta.stat().st_mtime_ns
            except OSError:
                mtime = 0
            out.append(((rec.started_at or "", mtime), rec.to_dict()))
        out.sort(key=lambda pair: pair[0], reverse=True)
        return [d for _, d in out][:limit]

    def transcript(self, run_id: str, max_lines: int = 2000) -> dict:
        """The last ``max_lines`` lines of one run's transcript."""
        path = self._dir / f"{_RUN_ID_SAFE.sub('-', run_id)}.log"
        try:
            size = path.stat().st_size
        except OSError:
            return {"lines": [], "total": 0, "found": False}
        # PERF-007: bounded backward tail for UTF-8 transcripts. A finished
        # run's metadata line_count is the authoritative total; without it the
        # exact total is only known when the backward walk reached the start
        # of the file. Everything else falls back to the legacy whole-file
        # read, so results stay byte-identical in every corner case.
        meta = self._read_meta(self._dir / f"{_RUN_ID_SAFE.sub('-', run_id)}.json")
        authoritative_total = (
            meta.line_count if meta is not None and meta.finished_at else None
        )
        if size > 0:
            tail = tail_raw_lines(path, max_lines)
            if tail is not None:
                lines, reached_bof = tail
                if reached_bof and len(lines) < max_lines:
                    # The whole file fit in the window.
                    return {"lines": lines, "total": len(lines), "found": True}
                if authoritative_total is not None and authoritative_total >= len(
                    lines
                ):
                    return {
                        "lines": lines,
                        "total": authoritative_total,
                        "found": True,
                    }
        elif authoritative_total is None:
            # Empty log, no trusted counter -- identical to the legacy result.
            return {"lines": [], "total": 0, "found": True}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"lines": [], "total": 0, "found": False}
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        total = len(lines)
        return {"lines": lines[-max_lines:], "total": total, "found": True}

    def last_run(self, root: str) -> dict | None:
        runs = self.history(root, limit=1)
        return runs[0] if runs else None

    # ---- internals -------------------------------------------------------

    def _meta_files(self, key: str) -> list[Path]:
        try:
            return sorted(self._dir.glob(f"*-{key}-*.json"))
        except OSError:
            return []

    def _read_meta(self, path: Path) -> SessionRecord | None:
        try:
            return SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            # One unreadable run, not a lost history -- that is the whole
            # reason there is no shared index file.
            return None

    def _write_meta(self, record: SessionRecord) -> None:
        path = self._dir / f"{record.run_id}.json"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(record.to_dict(), indent=2), encoding="utf-8", newline="\n"
            )
        except OSError as exc:
            print(
                f"SAIPENVIEW: cannot write session meta {path}: {exc}", file=sys.stderr
            )

    def _prune(self, key: str) -> None:
        metas = self._meta_files(key)
        if len(metas) <= MAX_RUNS_PER_PROJECT:
            return
        for meta in metas[: len(metas) - MAX_RUNS_PER_PROJECT]:
            for path in (meta, meta.with_suffix(".log")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
