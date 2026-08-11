"""Backend-persistent external-change tracking (repair mission P0).

The frontend once stored ONE `unrecordedChangeRoot` in JS: an external change
was only "seen" while that root was the selected project, so a change to a
hidden or background project could vanish from the safety state entirely. This
registry lives in the backend, keyed by (root, relative_path), and records
every external write the watcher reports -- regardless of which project is on
screen. Switching projects cannot clear it; only an explicit record/
acknowledge or a verified resolution (a self-write consuming the exact
fingerprint, or a collect boundary check passing) does.

Collect consults it: an unresolved boundary-relevant external change refuses
the collect with zero writes (the whole-tree boundary check).
"""

from __future__ import annotations

import hashlib
import threading
import time as _time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PendingChange:
    root: str
    rel_path: str
    fingerprint: str
    observed_at: float
    status: str = "unresolved"  # unresolved | acknowledged

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "path": self.rel_path,
            "status": self.status,
            "observed_at": self.observed_at,
        }


class ExternalChangeRegistry:
    """Per-(root, relative-path) record of unacknowledged external writes."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], PendingChange] = {}
        self._lock = threading.Lock()

    def record(self, root: str, rel_path: str, fingerprint: str) -> None:
        """Record an external write. A self-write (matching fingerprint
        consumed via `consume_self_write`) is the only non-recording event."""
        now = _time.monotonic()
        with self._lock:
            self._entries[(root, rel_path)] = PendingChange(
                root, rel_path, fingerprint, now
            )

    def consume_self_write(self, root: str, rel_path: str, fingerprint: str) -> bool:
        """True when *fingerprint* matches a recorded external change exactly
        and the change is removed (the app's own write resolved it).

        A self write followed immediately by a REAL external edit yields a
        DIFFERENT fingerprint, so the external edit is never consumed away."""
        with self._lock:
            key = (root, rel_path)
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.fingerprint != fingerprint:
                return False  # a real external edit landed after ours
            self._entries.pop(key, None)
            return True

    def acknowledge(self, root: str, rel_path: str) -> bool:
        """Explicit user acknowledge: clears one pending change."""
        with self._lock:
            return self._entries.pop((root, rel_path), None) is not None

    def acknowledge_root(self, root: str) -> int:
        """Clear every pending change for one project (explicit user action)."""
        with self._lock:
            keys = [k for k in self._entries if k[0] == root]
            for k in keys:
                self._entries.pop(k, None)
            return len(keys)

    def pending(self, root: str | None = None) -> list[PendingChange]:
        with self._lock:
            items = [
                c for c in self._entries.values() if root is None or c.root == root
            ]
            return sorted(items, key=lambda c: (c.root, c.rel_path))

    def unresolved(self, root: str) -> list[PendingChange]:
        """Unacknowledged boundary-relevant changes for one project.

        Collect refuses when any exist: an external write to ANY of the
        project's files (source or .saipen) that the app cannot attribute is
        exactly the "unexplained external write" the boundary check exists for.
        """
        return [c for c in self.pending(root) if c.status == "unresolved"]

    def fingerprint_file(self, path: Path) -> str:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            return "MISSING"
        return "FILE\0" + hashlib.sha256(raw).hexdigest()


_registry: ExternalChangeRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ExternalChangeRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ExternalChangeRegistry()
        return _registry
