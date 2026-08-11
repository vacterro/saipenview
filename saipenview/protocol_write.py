"""Per-project write coordinator for `.saipen/` protocol files.

Every mutation of a project's `.saipen/` STATE/BOARD/LOG/OUTBOX/docs goes
through THIS coordinator, which commits through the CANONICAL SAIPEN writer
pipeline (`saipenview/saio.py`): OS writer lock, recovery preflight, immutable
PREPARED journal, ordered targets, byte + semantic verification, COMMITTED.
The viewer is a CLIENT of the canonical authority -- it never builds a second
transaction engine, and a mutation whose canonical commit fails is reported
as that failure (WRITER_BUSY / STALE_STATE / RECOVERY_REQUIRED / CONFLICT),
never as success.

Decisions are bound to the exact snapshot they were made from: the plan's
preconditions are the raw hashes of the snapshot reads, revalidated by the
canonical journal under the writer lock immediately before commit. A
STALE_STATE result means the decision's world moved; the coordinator re-runs
the decision ONCE against a fresh snapshot (a fresh decision, never a blind
retry of stale bytes), then applies.

Two app-level guarantees still live here:

1. **Serialization per root** (app threads): all writers for one project hold
   the same per-root RLock, so two app threads cannot interleave
   read-decide-apply cycles.
2. **App-vs-agent ownership** (ownership.py): an app mutation refuses while a
   Core agent the app launched owns the project. Cross-process writers are
   excluded by the canonical OS lock, not by this process-local state.
"""

from __future__ import annotations

import contextlib
import re
import threading
import time as _time
from collections.abc import Callable
from pathlib import Path

from saipenview import saio
from saipenview.ownership import AgentOwnershipError, RootOwnership

_EVENT_ID_RE = re.compile(r"\[E-(\d+)\]")
_TICKET_ID_RE = re.compile(r"\bT-(\d+)\b")

# One coordinator per process; its per-root ownership is process-local, which
# is exactly what serializes two of the app's own threads. Cross-process
# writers are excluded by the canonical OS lock (saipen_engine.lock).
_coordinator: WriteCoordinator | None = None


def get_coordinator() -> WriteCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = WriteCoordinator()
    return _coordinator


class ConflictError(Exception):
    """DEPRECATED legacy exception: the canonical path reports staleness as a
    structured STALE_STATE result, not an exception. Kept only for callers
    that predate the result contract."""


class MutationRejected(Exception):
    """DEPRECATED legacy exception: see ConflictError."""


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


# The canonical checkpoint set: every protocol mutation's decision world. An
# external change to any of them between decide and commit aborts (STALE_STATE).
_CANONICAL_DOCS = (
    ".saipen/STATE.md",
    ".saipen/BOARD.md",
    ".saipen/LOG.md",
)


def _role_for(rel: str) -> str:
    name = Path(rel).name.lower()
    if name.startswith("log"):
        return "log"
    if name.startswith("board"):
        return "board"
    if name.startswith("state"):
        return "state"
    return "generic"


def _canonical_read_deps(root: Path, written: set[str]) -> dict[str, str]:
    """STATE/BOARD/LOG hashes (current snapshot) as read-only dependencies,
    minus any file this mutation writes (its write precondition covers it)."""
    docs = saio.snapshot(root, list(_CANONICAL_DOCS))
    return {rel: docs[rel].raw_hash for rel in _CANONICAL_DOCS if rel not in written}


class WriteCoordinator:
    """Canonical commits + app-level serialization and ownership."""

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
        """Typed file identity: `MISSING` for an absent file, `FILE\\0<hash>`
        for an existing one. A missing file never equals an empty file."""
        return saio.fingerprint_file(path)

    @contextlib.contextmanager
    def locked(self, root: Path):
        """Hold the per-root app lock across several coordinator mutations."""
        with self._lock(root):
            yield

    def _begin_tx(self, root: Path) -> None:
        """Under the per-root lock: mark an app transaction, refusing while an
        agent owns the root (the app-level policy; the OS writer lock is the
        canonical cross-process exclusion)."""
        if not self.ownership.begin_app_tx(root):
            raise AgentOwnershipError(
                f"Core agent is running for {root}; direct .saipen mutation refused"
            )

    def _end_tx(self, root: Path) -> None:
        self.ownership.end_app_tx(root)

    def mutate(self, root: Path, op_fn: Callable[[Path, int], object]) -> dict:
        """Commit one decision through the canonical pipeline.

        `op_fn(root, attempt)` must build an immutable OperationPlan from a
        fresh canonical snapshot (via saio.plan) -- or return a refusal dict
        {ok: False, code, message}. It is called at most twice: once, and once
        more with attempt=1 when the first apply returned STALE_STATE (the
        decision's world moved; the SECOND call is a fresh decision on the new
        snapshot, never a replay of stale bytes).

        Returns the normalized result contract. Self-writes are registered for
        every changed file so the watcher attributes them to the app.
        """
        root = Path(root)
        with self._lock(root):
            self._begin_tx(root)
            try:
                for attempt in range(2):
                    planned = op_fn(root, attempt)
                    if isinstance(planned, dict):
                        return planned
                    result = saio.apply(root, planned)
                    if result["code"] == "STALE_STATE" and attempt == 0:
                        continue
                    for rel in result.get("changed_files", []):
                        path = root / rel
                        self.self_writes.register(
                            str(root), path.name, saio.fingerprint_file(path)
                        )
                    return result
                return {
                    "ok": False,
                    "code": "STALE_STATE",
                    "message": "state moved repeatedly; re-read the project and retry",
                    "changed_files": [],
                    "retryable": True,
                    "recovery_required": False,
                    "op_id": None,
                }
            finally:
                self._end_tx(root)

    def mutate_doc(
        self,
        path: Path,
        transform: Callable[[str], str | None],
        *,
        expected_fingerprint: str | None = None,
        verification_policy: str = "core_fast",
    ) -> dict:
        """Single-file canonical mutation (text transform -> exact bytes).

        `transform(text_norm) -> new_text` (None declines without writing).
        Returns the normalized result contract. `expected_fingerprint` is the
        legacy CAS baseline: when it does not match the live bytes, the
        mutation refuses STALE_STATE without writing.

        `verification_policy`: core_fast (default) for structural ops;
        `none` for a raw hand-edit (file editor), which byte-verifies only so
        the user can repair a non-conformant project through the editor.

        A `.saipen/` file must be a codec-preserving read; non-protocol files
        are written directly (outside the canonical journal).
        """
        path = Path(path)
        root = self.root_for(path)
        rel = str(path.relative_to(root)).replace("\\", "/")
        role = _role_for(rel)

        def op_fn(r: Path, attempt: int):
            docs = saio.snapshot(r, [rel])
            doc = docs[rel]
            if (
                expected_fingerprint is not None
                and expected_fingerprint != "MISSING"
                and doc.raw_hash != expected_fingerprint
            ):
                return {
                    "ok": False,
                    "code": "STALE_STATE",
                    "message": f"{rel} changed since the read (CAS baseline)",
                    "changed_files": [],
                    "retryable": True,
                    "recovery_required": False,
                    "op_id": None,
                }
            if expected_fingerprint == "MISSING" and doc.raw_hash:
                return {
                    "ok": False,
                    "code": "STALE_STATE",
                    "message": f"{rel} was created since the read",
                    "changed_files": [],
                    "retryable": True,
                    "recovery_required": False,
                    "op_id": None,
                }
            new_text = transform(doc.text_norm)
            if new_text is None or new_text == doc.text_norm:
                return {
                    "ok": True,
                    "code": "NOOP",
                    "message": "no change",
                    "changed_files": [],
                    "retryable": False,
                    "recovery_required": False,
                    "op_id": None,
                }
            written = {rel}
            missing = [rel] if not (r / rel).exists() else None
            operation_plan = saio.plan(
                r,
                f"viewer-{role}",
                {"operation": f"viewer-{role}"},
                [(rel, role, new_text, doc)],
                {rel: doc.raw_hash},
                read_deps=_canonical_read_deps(r, written),
                missing_paths=missing,
            )
            return operation_plan, verification_policy

        def runner(root: Path, attempt: int):
            planned = op_fn(root, attempt)
            if isinstance(planned, tuple):
                operation_plan, policy = planned
                return saio.apply_with_precheck(
                    root, operation_plan, verification_policy=policy
                )
            return planned

        return self.mutate(root, runner)

    def recovery_status(self, root: Path) -> dict:
        """Unresolved canonical operations / conflicts blocking new mutation."""
        root = Path(root)
        try:
            return saio.recovery_status(root)
        except saio.SaioUnavailable as exc:
            return {
                "ok": False,
                "code": saio.SAIO_UNAVAILABLE,
                "message": str(exc),
                "conflicts": [],
                "pending": [],
                "blocked": False,
            }

    def recover(self, root: Path, op_id: str | None = None) -> dict:
        """Roll-forward recovery of pending canonical operations."""
        root = Path(root)
        try:
            with self._lock(root):
                return saio.recover(root, op_id)
        except saio.SaioUnavailable as exc:
            return {
                "ok": False,
                "code": saio.SAIO_UNAVAILABLE,
                "message": str(exc),
                "changed_files": [],
                "retryable": False,
                "recovery_required": False,
            }
