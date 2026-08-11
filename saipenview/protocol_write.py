"""Per-project write coordinator for `.saipen/` protocol files (T-183).

Every mutation of a project's `.saipen/` STATE/BOARD/LOG/OUTBOX/docs goes
through THIS coordinator and nothing else. It delivers three invariants the
old code violated:

1. **Serialization per root.** All writers for one project hold the same
   per-root lock, so two app threads can no longer interleave read-modify-
   write cycles on the same file and both commit.
2. **Optimistic CAS / fingerprint.** The file is fingerprinted before the
   transform and re-checked immediately before commit. A write by an external
   actor (a Core agent, a hand edit, another tool) between our read and our
   write aborts as a `ConflictError` instead of being silently overwritten --
   the lost-update the split-brain defects came from.
3. **Centralized id allocation.** `next_event_id` / `next_ticket_id` live here,
   run under the root lock, and are the only allocation a mutator may use.
   Every line a writer appends was allocated by exactly one code path.

`write_doc` (textio.py) already does the atomic temp+replace; this layer
guarantees the read->modify->write cycle around it is safe.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import threading
import time as _time
from collections.abc import Callable
from pathlib import Path

from saipenview.ownership import AgentOwnershipError, RootOwnership
from saipenview.textio import read_doc_meta, write_doc

_EVENT_ID_RE = re.compile(r"\[E-(\d+)\]")
_TICKET_ID_RE = re.compile(r"\bT-(\d+)\b")

# One coordinator per process; its per-root ownership is process-local, which
# is exactly what serializes two of the app's own threads. Out-of-process
# writers are caught by the fingerprint, not by the lock.
_coordinator: WriteCoordinator | None = None


def get_coordinator() -> WriteCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = WriteCoordinator()
    return _coordinator


class ConflictError(Exception):
    """A `.saipen/` file changed on disk between our read and our commit."""


class MutationRejected(Exception):
    """The transform declined to apply (invalid op); no write happens."""


def next_event_id(text: str) -> int:
    """Highest E-### in a LOG text + 1; 1 when the log carries none.

    The ONLY event-id allocation in the codebase. Must be called under the
    per-root lock (via a coordinator mutation) so two writers cannot derive
    the same next id from the same stale read.
    """
    return max((int(m.group(1)) for m in _EVENT_ID_RE.finditer(text)), default=0) + 1


def next_ticket_id(text: str) -> int:
    """Highest T-### in a BOARD text + 1; 1 when the board carries none.

    The ONLY ticket-id allocation in the codebase. Same lock discipline as
    `next_event_id`.
    """
    return max((int(m.group(1)) for m in _TICKET_ID_RE.finditer(text)), default=0) + 1


def escape_pipe(text: str) -> str:
    """Escape a literal `|` for the closed BOARD/LOG field grammar (RFC 1.2).

    A pipe inside a ticket description or a LOG line would be read as a
    `| field:` separator or break the line. The canonical escape is `\\|`.
    """
    return text.replace("|", "\\|")


class SelfWriteRegistry:
    """Per-(root, file) record of the app's own successful protocol writes.

    The frontend once tracked self-writes with a boolean Set of roots (T-127),
    which was an unsafe causal model: a failed write left the marker armed, one
    token consumed only one of several watcher notifications, and a global
    frontend debounce could collapse events across projects. This registry is
    the backend replacement (T-190): the coordinator registers the post-write
    fingerprint of exactly the (root, file) it changed, and the watcher handler
    consumes a registration only when the file's CURRENT fingerprint matches --
    so a real external edit after our write is still reported as external, and
    a failed write never registers anything.
    """

    def __init__(self, ttl: float = 5.0) -> None:
        self._entries: dict[tuple[str, str], tuple[str, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def register(self, root: str, file_name: str, fingerprint: str) -> None:
        now = _time.monotonic()
        with self._lock:
            self._entries[(root, file_name)] = (fingerprint, now + self._ttl)

    def consume(self, root: str, file_name: str, fingerprint: str) -> bool:
        """True when *fingerprint* matches our own post-write record for
        (root, file) and the record is consumed."""
        now = _time.monotonic()
        with self._lock:
            self._purge_locked(now)
            key = (root, file_name)
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry[1] < now:
                self._entries.pop(key, None)
                return False
            if entry[0] != fingerprint:
                return False  # external writer landed after ours: report external
            self._entries.pop(key, None)
            return True

    def _purge_locked(self, now: float) -> None:
        stale = [k for k, (_, exp) in self._entries.items() if exp < now]
        for k in stale:
            self._entries.pop(k, None)


class WriteCoordinator:
    """Per-root serialization + optimistic CAS for `.saipen/` documents."""

    def __init__(self) -> None:
        self.ownership = RootOwnership()
        self.self_writes = SelfWriteRegistry()

    def _lock(self, root: Path) -> threading.RLock:
        return self.ownership.lock(root)

    @staticmethod
    def root_for(path: Path) -> Path:
        """The project root that owns *path* (walk up to the `.saipen/` dir)."""
        p = Path(path).resolve()
        for part in p.parents:
            if part.name == ".saipen":
                return part.parent
        raise ValueError(f"{path} is not under a .saipen/ directory")

    @staticmethod
    def is_protocol_file(path: Path) -> bool:
        """True when *path* lives under some `<root>/.saipen/` directory."""
        try:
            WriteCoordinator.root_for(path)
            return True
        except ValueError:
            return False

    @staticmethod
    def fingerprint(path: Path) -> str:
        """SHA-1 of the file's raw bytes; of the empty string when missing.

        A missing file hashes like an empty one so a caller's CAS baseline for
        a to-be-created file (e.g. a first `_shared/inbox.md`) matches what
        `mutate_doc` computes for the absent target.
        """
        try:
            return hashlib.blake2b(Path(path).read_bytes()).hexdigest()
        except OSError:
            return hashlib.blake2b(b"").hexdigest()

    @contextlib.contextmanager
    def locked(self, root: Path):
        """Hold the per-root lock across several coordinator mutations."""
        with self._lock(root):
            yield

    def _begin_tx(self, root: Path) -> None:
        """Under the per-root lock: mark an app transaction, refusing while an
        agent owns the root. This is the authoritative single-writer gate --
        the Api's `_guard_protocol_write` is only the cheap pre-check."""
        if not self.ownership.begin_app_tx(root):
            raise AgentOwnershipError(
                f"Core agent is running for {root}; direct .saipen mutation refused"
            )

    def _end_tx(self, root: Path) -> None:
        self.ownership.end_app_tx(root)

    def transaction(
        self,
        root: Path,
        targets: dict[Path, Callable[[str], str | None]],
        deps: list[Path] | None = None,
    ) -> None:
        """Atomic multi-file mutation with cross-document conflict detection.

        ``targets`` maps each file to its transform. ``deps`` names every
        canonical input whose truth the operation's DECISION depended on --
        files read but not written. Both targets and deps are fingerprinted
        from the read the caller reasoned over, and ALL fingerprints are
        re-validated immediately before the first commit. An external change
        to any of them (target OR dependency) aborts the whole transaction
        with ``ConflictError`` -- never a silent composition of two realities.

        Guard + reservation + mutation are one atomic ownership decision: the
        agent-ownership check and the app-transaction mark happen under the
        same per-root lock the launch path reserves, so a launch cannot slip
        between a passed guard and its write.

        Raises ``ConflictError`` (external drift), ``AgentOwnershipError``
        (agent owns the root) or ``MutationRejected`` (a transform declined).
        """
        root = Path(root)
        with self._lock(root):
            self._begin_tx(root)
            try:
                dep_paths = [Path(p) for p in (deps or [])]
                baseline: dict[Path, str] = {p: self.fingerprint(p) for p in dep_paths}
                prepared: list[tuple[Path, str, str, str]] = []
                for path, transform in targets.items():
                    path = Path(path)
                    if path not in baseline:
                        baseline[path] = self.fingerprint(path)
                    text, enc, newline = read_doc_meta(path)
                    new_text = transform(text)
                    if new_text is None or new_text == text:
                        continue
                    prepared.append((path, new_text, enc, newline))
                if not prepared:
                    return
                # Revalidate EVERY canonical input (deps + targets) before the
                # first commit. A non-target dependency that moved since our
                # read aborts the operation, not just the file it touched.
                for path, fp in baseline.items():
                    if self.fingerprint(path) != fp:
                        raise ConflictError(str(path))
                for path, new_text, enc, newline in prepared:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    write_doc(path, new_text, enc, newline)
                    self.self_writes.register(
                        str(root), path.name, self.fingerprint(path)
                    )
            finally:
                self._end_tx(root)

    def mutate_doc(
        self,
        path: Path,
        transform: Callable[[str], str | None],
        *,
        expected_fingerprint: str | None = None,
    ) -> str | None:
        """Read->transform->CAS-check->write one `.saipen/` document.

        `transform(text) -> new_text` (or None to decline without writing).
        Returns the new fingerprint, or None when the transform declined.
        Raises `ConflictError` when the file changed on disk between our read
        and our commit (external writer -- never overwritten),
        `AgentOwnershipError` when an agent owns the project (single-writer
        gate), and `OSError` when the file is unreadable/absent.
        """
        path = Path(path)
        root = self.root_for(path)
        with self._lock(root):
            self._begin_tx(root)
            try:
                try:
                    raw = path.read_bytes()
                except OSError:
                    # Missing target: mutate from an empty base (the transform may
                    # create the file, e.g. a first _shared/inbox.md). An existing
                    # empty file and a missing file both fingerprint the same; the
                    # transform decides which is meaningful.
                    raw = b""
                fp = hashlib.blake2b(raw).hexdigest()
                if expected_fingerprint is not None and fp != expected_fingerprint:
                    raise ConflictError(str(path))
                text, enc, newline = read_doc_meta(path)
                new_text = transform(text)
                if new_text is None or new_text == text:
                    return fp if new_text is not None else None
                try:
                    raw_now = path.read_bytes()
                except OSError:
                    raw_now = b""
                if hashlib.blake2b(raw_now).hexdigest() != fp:
                    raise ConflictError(str(path))
                path.parent.mkdir(parents=True, exist_ok=True)
                write_doc(path, new_text, enc, newline)
                new_fp = self.fingerprint(path)
                # T-190: register OUR successful write so the watcher can tell a
                # self-change from an external one. Registered only now, after the
                # write landed -- a failed write never marks anything.
                self.self_writes.register(str(root), path.name, new_fp)
                return new_fp
            finally:
                self._end_tx(root)
