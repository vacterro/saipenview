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
_TERMINAL_SESSION_STATUSES = frozenset({"done", "failed", "killed"})

# PERF-003: extract the project key from a metadata filename stem. A run_id is
# ``<stamp>[-<suffix>]-<key>-<engine>`` where ``<stamp>`` is a 19-char
# ``%Y%m%dT%H%M%S%f`` string, ``<key>`` is the 10-hex project_key and
# ``<engine>`` is the remaining name. Anchoring on the stamp and the 10-hex key
# avoids a brittle greedy split.
_META_KEY_RE = re.compile(r"^\d{8}T\d{6}\d{6}(?:-\d+)?-(?P<key>[0-9a-f]{10})-")

# PERF-004 (SRC-018 R014): capture the creation stamp from a metadata FILENAME
# without decoding the file. The stamp is the same instant started_at carries,
# so lexical name order is chronological order (same-stamp collisions add a
# numeric ``-<suffix>`` between stamp and key, preserving it).
_META_STAMP_RE = re.compile(r"^(?P<stamp>\d{8}T\d{6}\d{6})(?:-\d+)?-[0-9a-f]{10}-")


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
        if not isinstance(d, dict):
            raise ValueError("session metadata must be an object")

        def string(name: str, default: str = "") -> str:
            value = d.get(name, default)
            if not isinstance(value, str):
                raise ValueError(f"session metadata {name} must be a string")
            return value

        def optional_string(name: str) -> str | None:
            value = d.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"session metadata {name} must be a string or null")
            return value

        def optional_int(name: str) -> int | None:
            value = d.get(name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise ValueError(f"session metadata {name} must be an integer or null")
            return value

        line_count = d.get("line_count", 0)
        if (
            isinstance(line_count, bool)
            or not isinstance(line_count, int)
            or line_count < 0
        ):
            raise ValueError(
                "session metadata line_count must be a non-negative integer"
            )
        truncated = d.get("truncated", False)
        if not isinstance(truncated, bool):
            raise ValueError("session metadata truncated must be boolean")
        return SessionRecord(
            run_id=string("run_id"),
            root=string("root"),
            project=string("project"),
            engine=string("engine"),
            engine_display=string("engine_display", string("engine")),
            instruction=string("instruction"),
            started_at=string("started_at"),
            status=string("status", "running"),
            finished_at=optional_string("finished_at"),
            exit_code=optional_int("exit_code"),
            line_count=line_count,
            truncated=truncated,
            pid=optional_int("pid"),
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

    _MAX_PENDING_FINAL = 100  # W2-004: cap for retry queue

    def __init__(self, base_dir: Path | None = None) -> None:
        self._dir = Path(base_dir) if base_dir else sessions_dir()
        self._open: dict[str, _OpenTranscript] = {}
        self._lock = threading.Lock()
        # CORE-003: a bounded retry cache for terminal records whose canonical
        # metadata write failed. The matching per-run sidecar under
        # `.pending-final/<project-key>/` is the durable replay authority; this
        # dict only avoids rereading the sidecar in the current process.
        self._pending_final: dict[str, SessionRecord] = {}
        self._pending_final_lock = threading.Lock()
        # True when durable fallback persistence failed or the bounded retry
        # cache had to evict an entry to its per-run durable sidecar.
        self._pending_degraded = False
        # PERF-003 (SRC-004:R005): rebuildable process-local index. The
        # sessions dir is one flat directory for EVERY project, so the old
        # `_meta_files()` glob re-walked unrelated projects' files on every
        # per-project history/prune lookup, and an idle agent panel decoded the
        # same 50 target metadata files twice (last_run + history). These caches
        # are disposable: they are keyed by a directory signature (mtime), are
        # cleared on our own writes/prunes AND whenever the directory changes
        # out of process, and carry no authority a rebuild cannot restore from
        # the individual metadata files.
        self._meta_index: dict[str, list[Path]] = {}
        self._history_cache: dict[str, tuple[tuple, list]] = {}
        self._meta_read_cache: dict[str, tuple[tuple, SessionRecord]] = {}
        self._meta_cache_sig: tuple | None = None
        self._meta_cache_lock = threading.Lock()

    # ---- PERF-003 index --------------------------------------------------

    def _dir_sig(self) -> tuple:
        """A cheap directory identity that changes on add/remove/rename.

        ``st_mtime_ns`` advances whenever an entry is created or removed in the
        sessions dir -- exactly the events that make the filename index stale.
        A pure content rewrite of an existing metadata file is covered
        separately because history() re-reads via ``_read_meta`` on a cache
        miss; the index only answers WHICH files belong to a project.
        """
        try:
            return (self._dir.stat().st_mtime_ns,)
        except OSError:
            return (0,)

    def _invalidate_meta_cache(self) -> None:
        """Drop the index + decode cache. Called after every self-write/prune."""
        with self._meta_cache_lock:
            self._meta_index = {}
            self._history_cache = {}
            self._meta_read_cache = {}
            self._meta_cache_sig = None

    # ---- writing ---------------------------------------------------------

    def _pending_final_path(self, run_id: str, key: str) -> Path:
        safe_run_id = _RUN_ID_SAFE.sub("-", run_id)
        return self._dir / ".pending-final" / key / f"{safe_run_id}.json"

    def _write_pending_final(self, record: SessionRecord) -> bool:
        """Atomically persist one replayable terminal fact beside session data."""
        if (
            record.status not in _TERMINAL_SESSION_STATUSES
            or not record.finished_at
        ):
            return False
        key = project_key(record.root)
        path = self._pending_final_path(record.run_id, key)
        tmp_path = path.with_suffix(".json.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(record.to_dict(), indent=2),
                encoding="utf-8",
                newline="\n",
            )
            tmp_path.replace(path)
            return True
        except OSError as exc:
            print(
                f"SAIPENVIEW: cannot persist pending terminal {record.run_id}: {exc}",
                file=sys.stderr,
            )
            return False
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_pending_final_path(
        self, path: Path, expected_root: str | None = None
    ) -> SessionRecord | None:
        """Read one isolated fallback record; corruption costs only this run."""
        try:
            record = SessionRecord.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            print(
                f"SAIPENVIEW: pending terminal evidence unreadable for "
                f"{path.stem}: {exc}",
                file=sys.stderr,
            )
            return None
        if (
            record.run_id != path.stem
            or _RUN_ID_SAFE.sub("-", record.run_id) != record.run_id
            or record.status not in _TERMINAL_SESSION_STATUSES
            or not record.finished_at
            or path.parent.name != project_key(record.root)
            or (expected_root is not None and project_key(record.root) != project_key(expected_root))
        ):
            print(
                f"SAIPENVIEW: pending terminal evidence invalid for {path.stem}",
                file=sys.stderr,
            )
            return None
        return record

    def _read_pending_final(
        self, run_id: str, root: str
    ) -> SessionRecord | None:
        path = self._pending_final_path(run_id, project_key(root))
        return self._read_pending_final_path(path, expected_root=root)

    def _retire_pending_final(self, record: SessionRecord) -> None:
        """Remove replay evidence only after its canonical record is durable."""
        path = self._pending_final_path(record.run_id, project_key(record.root))
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(
                f"SAIPENVIEW: cannot retire pending terminal {record.run_id}: {exc}",
                file=sys.stderr,
            )
            return
        for directory in (path.parent, path.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                break

    def _retry_pending_final(self, root: str | None = None) -> None:
        """Reconcile cached and durable terminal facts into canonical metadata."""
        with self._pending_final_lock:
            pending = dict(self._pending_final)
        if root is not None:
            key = project_key(root)
            fallback_dirs = [self._dir / ".pending-final" / key]
        else:
            try:
                fallback_dirs = [
                    path
                    for path in (self._dir / ".pending-final").iterdir()
                    if path.is_dir()
                ]
            except OSError:
                fallback_dirs = []
        for fallback_dir in fallback_dirs:
            try:
                paths = list(fallback_dir.glob("*.json"))
            except OSError:
                continue
            for path in paths:
                record = self._read_pending_final_path(path, expected_root=root)
                if record is not None:
                    pending.setdefault(record.run_id, record)
        for run_id, record in pending.items():
            if self._write_meta(record):
                self._retire_pending_final(record)
                with self._pending_final_lock:
                    current = self._pending_final.get(run_id)
                    if current is not None and current.to_dict() == record.to_dict():
                        self._pending_final.pop(run_id, None)
            else:
                with self._pending_final_lock:
                    if (
                        run_id not in self._pending_final
                        and len(self._pending_final) < self._MAX_PENDING_FINAL
                    ):
                        self._pending_final[run_id] = record

    def start(
        self,
        root: str,
        engine: str,
        engine_display: str,
        instruction: str,
        pid: int | None = None,
    ) -> SessionRecord | None:
        """Open a transcript for a new run. Returns None if the disk says no."""
        # CORE-003: reconcile this project's replayable terminal records before
        # admitting another run after storage recovers.
        self._retry_pending_final(root=root)
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
        entry = _OpenTranscript(record=record, handle=handle)
        with self._lock:
            self._open[run_id] = entry
        if not self._write_meta(record):
            with self._lock:
                self._open.pop(run_id, None)
            with entry.lock:
                try:
                    handle.close()
                except OSError:
                    pass
            try:
                (self._dir / f"{run_id}.log").unlink(missing_ok=True)
            except OSError:
                pass
            return None
        self._prune(key)
        return record

    def append(self, run_id: str, line: str) -> None:
        with self._lock:
            entry = self._open.get(run_id)
        if entry is None or entry.handle is None:
            return
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
            raw_bytes = line.encode("utf-8", errors="replace")
            if len(raw_bytes) > MAX_OUTPUT_LINE_BYTES:
                truncated = raw_bytes[:MAX_OUTPUT_LINE_BYTES].decode(
                    "utf-8", errors="ignore"
                )
                line = truncated + " [... truncated]"
                raw_bytes = line.encode("utf-8", errors="replace")
            payload_len = len(raw_bytes) + 1
            try:
                entry.handle.write(line + "\n")
            except (OSError, ValueError):
                return
            entry.bytes_written += payload_len
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
            entry = self._open.get(run_id)
        if entry is None:
            return
        with entry.lock:
            if entry.handle is not None:
                try:
                    entry.handle.flush()
                except OSError:
                    pass
            record = SessionRecord.from_dict(entry.record.to_dict())
            record.status = status
            record.exit_code = exit_code
            record.finished_at = datetime.now(timezone.utc).isoformat()
            # CORE-003: close handle and remove from _open BEFORE metadata
            # write. A transient disk failure must not leave a dead process
            # represented as live, leak the transcript handle, or accept
            # the run as locally open.
            if entry.handle is not None:
                try:
                    entry.handle.close()
                except OSError:
                    pass
                entry.handle = None
            entry.record = record
            with self._lock:
                if self._open.get(run_id) is entry:
                    self._open.pop(run_id, None)
        # Best-effort metadata write after lifecycle cleanup — never gate on it.
        # CORE-003: a failed canonical write gets a per-run atomic sidecar before
        # the bounded in-memory retry cache admits or evicts any record.
        persisted = self._write_meta(record)
        if not persisted:
            # Retry older facts first so recovered writes free bounded-cache
            # capacity before the newest completion is admitted.
            self._retry_pending_final(root=record.root)
            persisted = self._write_meta(record)
        if persisted:
            self._retire_pending_final(record)
            with self._pending_final_lock:
                self._pending_final.pop(run_id, None)
        else:
            fallback_saved = self._write_pending_final(record)
            with self._pending_final_lock:
                if run_id in self._pending_final or len(self._pending_final) < self._MAX_PENDING_FINAL:
                    self._pending_final[run_id] = record
                else:
                    # The durable per-run sidecar is also the eviction record;
                    # no separate append-only overflow log has to be replayed.
                    oldest_id, oldest = next(iter(self._pending_final.items()))
                    old_record = self._read_pending_final(
                        oldest.run_id, oldest.root
                    )
                    if old_record is None or old_record.to_dict() != oldest.to_dict():
                        if not self._write_pending_final(oldest):
                            self._pending_degraded = True
                    self._pending_final.pop(oldest_id, None)
                    self._pending_final[run_id] = record
                    self._pending_degraded = True
            if not fallback_saved:
                self._pending_degraded = True
        # Retry current-project disk fallbacks opportunistically after each
        # finish. Persistent failures remain in their own sidecars.
        self._retry_pending_final(root=record.root)

    # ---- reading ---------------------------------------------------------

    def history(self, root: str, limit: int = 20) -> list[dict]:
        """Runs for one project, newest first.

        A record still saying `running` that this process does not have open
        belongs to a SAIPENVIEW that died -- report it as `interrupted` rather
        than as an agent that has been working since Tuesday.

        CORE-003: a terminal sidecar is replayed over stale `running` metadata,
        including after a process restart. When the canonical write succeeds,
        its sidecar is retired. A running record with neither a live owner nor
        valid terminal evidence remains an interrupted crash.

        PERF-004 (SRC-018 R014 / T-865): metadata filenames carry a fixed-width
        ``%Y%m%dT%H%M%S%f`` stamp, so ``_meta_files`` name order IS chronological
        and records sharing one ``started_at`` are contiguous. history(limit=N)
        therefore reads only enough NEWEST candidates to obtain N valid records
        plus the full same-clock tie group of the Nth (so mtime tie-breaking
        stays correct), rather than decoding, re-stat'ing and sorting the whole
        project history. ``last_run`` (limit=1) is thus proportional to the
        newest candidate/tie group, not O(H). No duplicate stat: the mtime used
        for tie-breaking comes from the SAME stat ``_read_meta`` already took.
        """
        if limit is not None and limit <= 0:
            return []
        key = project_key(root)
        with self._lock:
            live = set(self._open)
        with self._pending_final_lock:
            pending = dict(self._pending_final)
        metas = self._meta_files(key)  # name-sorted, oldest first
        collected: list[tuple[tuple[str, int], dict]] = []
        # started_at of the newest tie-group boundary we must fully consume
        # before we may stop early. None until we have `limit` valid records.
        boundary_started: str | None = None
        for meta in reversed(metas):
            started_hint = self._meta_started_at_hint(meta)
            # PERF-004: once we have enough valid records, we may stop as soon
            # as a candidate is STRICTLY older than the boundary tie group.
            # The name stamp equals started_at, so this test needs no decode
            # for records clearly past the boundary.
            if (
                limit is not None
                and boundary_started is not None
                and started_hint is not None
                and started_hint < boundary_started
            ):
                break
            rec, mtime = self._read_meta_with_mtime(meta)
            if rec is None:
                continue
            rec = self._overlay_history_record(rec, live, pending)
            started = rec.started_at or ""
            collected.append(((started, mtime), rec.to_dict()))
            if limit is not None and boundary_started is None and len(collected) >= limit:
                # The boundary is the smallest started_at currently kept.
                # Because we read newest-first (chronological), that is the
                # started_at of the most recently appended record.
                boundary_started = min(k[0] for k, _ in collected)
        collected.sort(key=lambda pair: pair[0], reverse=True)
        result = [d for _, d in collected]
        return result[:limit] if limit is not None else result

    def _overlay_history_record(
        self,
        rec: SessionRecord,
        live: set[str],
        pending: dict[str, SessionRecord],
    ) -> SessionRecord:
        """PERF-004: the pending-terminal overlay + interrupted-crash decision,
        extracted so ``history`` can apply it per candidate as it reads them
        newest-first. Semantics are byte-identical to the previous inline body.
        """
        if rec.status == "running":
            pending_rec = pending.get(rec.run_id)
            if (
                pending_rec is not None
                and project_key(pending_rec.root) != project_key(rec.root)
            ):
                pending_rec = None
            if pending_rec is None:
                pending_rec = self._read_pending_final(rec.run_id, rec.root)
            if pending_rec is not None:
                rec = pending_rec
                if self._write_meta(pending_rec):
                    self._retire_pending_final(pending_rec)
                    with self._pending_final_lock:
                        current = self._pending_final.get(rec.run_id)
                        if (
                            current is not None
                            and current.to_dict() == pending_rec.to_dict()
                        ):
                            self._pending_final.pop(rec.run_id, None)
                else:
                    with self._pending_final_lock:
                        if (
                            rec.run_id not in self._pending_final
                            and len(self._pending_final) < self._MAX_PENDING_FINAL
                        ):
                            self._pending_final[rec.run_id] = pending_rec
            elif rec.run_id not in live:
                rec.status = "interrupted"
        elif rec.status in _TERMINAL_SESSION_STATUSES:
            # A crash after the metadata replace but before sidecar unlink
            # leaves redundant replay evidence. The canonical terminal
            # record is already durable, so retire that exact run's copy.
            self._retire_pending_final(rec)
            with self._pending_final_lock:
                self._pending_final.pop(rec.run_id, None)
        return rec

    def _meta_started_at_hint(self, path: Path) -> str | None:
        """PERF-004 (SRC-018 R014): the started_at ISO string implied by a
        metadata filename's stamp, WITHOUT decoding the file. Used only to
        decide when the reverse scan may stop; the authoritative started_at
        still comes from the decoded record. Returns None when the name has no
        parseable stamp (a legacy or oddly-named file), which conservatively
        disables the early stop for it.
        """
        m = _META_STAMP_RE.match(path.name)
        if m is None:
            return None
        s = m.group("stamp")
        # The stamp is strftime("%Y%m%dT%H%M%S%f"); started_at is the same
        # instant as datetime.isoformat(). Index map: [0:4]=year [4:6]=month
        # [6:8]=day [8]='T' [9:11]=HH [11:13]=MM [13:15]=SS [15:21]=micros.
        # The hint must be BYTE-IDENTICAL to the started_at it stands in for,
        # offset included: a hint without the offset is a strict PREFIX of the
        # real value, so a record in the same microsecond as the boundary
        # compares as strictly older and the tie group the scan promises to
        # consume is cut off at exactly the first twin.
        return (
            f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
            f"T{s[9:11]}:{s[11:13]}:{s[13:15]}.{s[15:21]}+00:00"
        )


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
        """Metadata files for one project, name-sorted (oldest first).

        PERF-003 (SRC-004:R005): served from a rebuildable process-local index
        keyed by project, so a steady-state per-project lookup no longer globs
        the whole flat sessions directory (which grows with UNRELATED projects'
        histories). The index is rebuilt whenever the directory signature moves
        -- including changes made by another SAIPENVIEW process -- so it can
        never serve a stale view indefinitely, and it holds no authority a
        rebuild from the individual files cannot restore.
        """
        sig = self._dir_sig()
        with self._meta_cache_lock:
            if self._meta_cache_sig != sig or not self._meta_index:
                index: dict[str, list[Path]] = {}
                try:
                    all_metas = list(self._dir.glob("*-*.json"))
                except OSError:
                    all_metas = []
                for meta in all_metas:
                    m = _META_KEY_RE.match(meta.name[:-5])
                    if m is not None:
                        index.setdefault(m.group("key"), []).append(meta)
                for metas in index.values():
                    metas.sort()
                self._meta_index = index
                self._meta_cache_sig = sig
            return list(self._meta_index.get(key, []))

    def _read_meta(self, path: Path) -> SessionRecord | None:
        """Read one metadata record, cached by (mtime_ns, size).

        PERF-003 (SRC-004:R005): an idle agent panel calls last_run() and then
        history() for the same project; both decoded the same ~50 metadata
        files. The cache is keyed on the file's own identity, so a rewritten
        record is re-read, and it is cleared wholesale on any directory
        change/self-write (``_invalidate_meta_cache``).
        """
        record, _mtime = self._read_meta_with_mtime(path)
        return record

    def _read_meta_with_mtime(self, path: Path) -> tuple[SessionRecord | None, int]:
        """PERF-004 (SRC-018 R014): read one metadata record AND its mtime_ns
        from ONE stat call. ``history`` needs the mtime only as the same-clock
        tie-breaker; re-stat'ing every file (the old ``meta.stat()`` in the
        loop) doubled the metadata stat work per lookup. A decode hit in the
        cache still needs the mtime, so the stat is taken first and the decode
        cache reuses the (mtime_ns, size) signature it already derives from it.
        """
        try:
            st = path.stat()
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            return None, 0
        mtime = st.st_mtime_ns
        with self._meta_cache_lock:
            hit = self._meta_read_cache.get(str(path))
            if hit is not None and hit[0] == sig:
                return hit[1], mtime
        try:
            record = SessionRecord.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError):
            # One unreadable run, not a lost history -- that is the whole
            # reason there is no shared index file.
            return None, mtime
        with self._meta_cache_lock:
            self._meta_read_cache[str(path)] = (sig, record)
        return record, mtime

    def _write_meta(self, record: SessionRecord) -> bool:
        path = self._dir / f"{record.run_id}.json"
        tmp_path = path.with_suffix(".json.tmp")
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            # Atomic write: write to temp file first, then replace. A crash
            # during write leaves either the old valid record or no file --
            # never a truncated/corrupt JSON that would drop history count.
            tmp_path.write_text(
                json.dumps(record.to_dict(), indent=2), encoding="utf-8", newline="\n"
            )
            tmp_path.replace(path)
            # PERF-003: our own write creates/replaces an entry -- drop the
            # index + decode cache so the next lookup sees it.
            self._invalidate_meta_cache()
            return True
        except OSError as exc:
            print(
                f"SAIPENVIEW: cannot write session meta {path}: {exc}", file=sys.stderr
            )
        finally:
            # Clean up temp file on failure so it does not accumulate.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False

    def _prune(self, key: str) -> None:
        metas = self._meta_files(key)
        if len(metas) <= MAX_RUNS_PER_PROJECT:
            return
        removed = False
        for meta in metas[: len(metas) - MAX_RUNS_PER_PROJECT]:
            try:
                meta.unlink(missing_ok=True)
                meta_removed = not meta.exists()
                removed |= meta_removed
            except OSError:
                meta_removed = False
            try:
                meta.with_suffix(".log").unlink(missing_ok=True)
                removed = True
            except OSError:
                pass
            if meta_removed:
                try:
                    self._pending_final_path(meta.stem, key).unlink(missing_ok=True)
                except OSError:
                    pass
                with self._pending_final_lock:
                    self._pending_final.pop(meta.stem, None)
        if removed:
            self._invalidate_meta_cache()
