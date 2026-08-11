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

import threading
from pathlib import Path

from saipenview.paths import canonical_key


class AgentOwnershipError(Exception):
    """A protocol mutation was refused because an agent owns the project."""


class RootOwnership:
    def __init__(self) -> None:
        self._locks: dict[str, threading.RLock] = {}
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
        and a launch can never interleave their check-then-act."""
        key = canonical_key(root)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = threading.RLock()
            return lock

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
