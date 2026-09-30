"""Per-root single-writer ownership between app mutations and agent launches.

The write coordinator's per-root RLock serializes the app's OWN threads, but
the single-writer invariant spans two actors: SAIPENVIEW's protocol mutations
and the Core agent it launches. Two process-local locks cannot serialise each
other, so both sides share ONE registry and ONE per-root lock here.

The mutual exclusion is a reservation pair:

* ``try_begin_app_tx`` -- the coordinator marks an app protocol transaction.
  It refuses while an agent owns the root (launch reserved or running).
* ``reserve_agent`` -- ProcessManager marks a launch. It refuses while an app
  transaction is active.

Both decisions happen under the SAME per-root lock, so check-then-act is
atomic: an app mutation that passed its guard cannot have a launch slip in
between (the launch would take the lock and either wait or refuse), and a
launch that reserved the root cannot be followed by a mutation the guard
already passed (the mutation re-checks under the lock).
"""

from __future__ import annotations

import contextlib
import threading
import weakref
from pathlib import Path

from saipenview.paths import canonical_key


class AgentOwnershipError(Exception):
    """A protocol mutation was refused because an agent owns the project."""


class RootOwnership:
    def __init__(self) -> None:
        # PERF-005 (SRC-018 R015): idle per-root locks are retained WEAKLY, so
        # touching thousands of transient roots cannot grow the registry
        # forever. The value stays alive exactly as long as SOME caller holds
        # it (a live reference on a thread's frame/with-expression), which is
        # precisely the definition of "held or awaited":
        #   * a lock being held or blocked-on is referenced by its holder, so
        #     the weak entry can never die while the lock is in use -- no
        #     concurrent caller can be handed a different object;
        #   * once every holder releases and drops the reference, the entry is
        #     reclaimed and the next caller mints a fresh lock -- but at that
        #     instant nobody holds or awaits the old one, so same-root
        #     serialization is never split across two objects.
        # The _locks_guard makes the get-or-create decision atomic, so two
        # concurrent lock() calls for one root can never mint two objects
        # while both are live.
        self._locks: weakref.WeakValueDictionary[str, threading.RLock] = (
            weakref.WeakValueDictionary()
        )
        self._locks_guard = threading.Lock()
        # Roots whose agent launch is in-flight (reservation held) or whose
        # process is live. Set by reserve_agent, cleared at finalize.
        self._agent_owned: set[str] = set()
        # Roots with an app protocol transaction active (depth counter:
        # nested mutate_doc calls under one coord.locked() context are one tx).
        self._app_tx: dict[str, int] = {}

    def lock(self, root: Path) -> threading.RLock:
        """The one per-root lock every ownership decision and every mutation
        holds. The coordinator reuses exactly this lock, so an app mutation
        and a launch can never interleave their check-then-act.

        PERF-005 (SRC-018 R015): the returned object is kept alive by the
        CALLER's reference for exactly as long as it is held or awaited, so
        concurrent same-root callers always receive the same live object while
        an idle lock is reclaimable by GC. The guard serializes get-or-create:
        two concurrent callers can never mint two live locks for one root.
        """
        key = canonical_key(root)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
            # Keep a strong reference until the caller receives the object so
            # the weak entry cannot die between the get-or-create and the
            # return (the caller's frame then holds it).
            ref = lock
        return ref

    def agent_owns(self, root: Path) -> bool:
        """True when a Core agent has the root reserved (launching) or live.
        Callers may read this without the lock for a UX pre-check; the
        authoritative guard re-checks under the lock at mutation time."""
        return canonical_key(root) in self._agent_owned

    def reserve_agent(self, root: Path) -> bool:
        """Reserve the root for an agent launch. Refuses while an app protocol
        transaction is active or another launch already owns the root. Must be
        called while holding ``lock(root)`` so the check and the mark are one
        atomic decision -- the reservation IS the mutual exclusion, so it must
        be exclusive."""
        key = canonical_key(root)
        with self.lock(root):
            if self._app_tx.get(key, 0):
                return False
            if key in self._agent_owned:
                return False
            self._agent_owned.add(key)
            return True

    def release_agent(self, root: Path) -> None:
        with self.lock(root):
            self._agent_owned.discard(canonical_key(root))

    def begin_app_tx(self, root: Path) -> bool:
        """Mark an app protocol transaction. Refuses while an agent owns the
        root. Called under ``lock(root)`` (the coordinator holds it for the
        whole mutation), so the check and the mark are atomic."""
        key = canonical_key(root)
        with self.lock(root):
            if key in self._agent_owned:
                return False
            self._app_tx[key] = self._app_tx.get(key, 0) + 1
            return True

    def end_app_tx(self, root: Path) -> None:
        with self.lock(root):
            key = canonical_key(root)
            depth = self._app_tx.get(key, 0) - 1
            if depth <= 0:
                self._app_tx.pop(key, None)
            else:
                self._app_tx[key] = depth

    @contextlib.contextmanager
    def app_transaction(self, root: Path):
        """A SERIALIZED app transaction: the per-root lock is held throughout.

        W2-003 (SRC-004:R011): `begin_app_tx` marks activity and returns, so it
        releases `lock(root)` on the way out. That is correct for the write
        coordinator, which takes the lock itself and holds it around the whole
        mutation -- but a caller that only calls `begin_app_tx` gets no mutual
        exclusion at all: the depth counter happily goes to 2 and both app
        writers proceed. Two `git commit`/`reset`/`clean` operations on one root
        could therefore verify the same fingerprint and then interleave their
        index and worktree work.

        The two verbs are deliberately distinct so a caller cannot confuse them:
        `begin_app_tx` MARKS app activity, this MARKS AND SERIALIZES. Yields
        True when the transaction is owned, False when an agent owns the root
        (the caller refuses); the lock is released either way on exit.

        Reentrant by construction -- the lock is an RLock, so a coordinator
        mutation nested inside this context on the same thread still works.
        """
        lock = self.lock(root)
        lock.acquire()
        owned = False
        try:
            owned = self.begin_app_tx(root)
            yield owned
        finally:
            if owned:
                self.end_app_tx(root)
            lock.release()
