"""Backend-persistent external-change tracking (repair mission P0/P1).

The frontend once stored ONE `unrecordedChangeRoot` in JS: an external change
was only "seen" while that root was the selected project, so a change to a
hidden or background project could vanish from the safety state entirely. This
registry lives in the backend, keyed by (canonical root, normalized relative
path), and records every external write the watcher reports -- regardless of
which project is on screen. Switching projects cannot clear it; only an
explicit acknowledge (or a collect boundary check passing) does.

Semantics (P1 #8): SelfWriteRegistry owns CAUSAL self-write attribution (the
watcher reports origin=self for the app's own writes). This registry stores
UNRESOLVED EXTERNAL evidence only -- a later app write that happens to produce
matching bytes does NOT clear an external violation; only an explicit
acknowledge or a verified protocol resolution does.
"""

from __future__ import annotations

import re
import threading
import time as _time
from dataclasses import dataclass

from saipenview.paths import canonical_key


def normalize_rel(rel_path: str) -> str:
    """The ONE relative-path spelling for registry keys: forward slashes,
    no `./`, no absolute paths, no `..` escape. Raises ValueError on any
    traversal/absolute form (fail closed, never key authority by a path that
    could alias outside the project)."""
    text = str(rel_path or "")
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        raise ValueError(f"rel_path must be project-relative, got {rel_path!r}")
    text = text.replace("\\", "/").strip("/")
    if not text:
        raise ValueError(f"rel_path must be project-relative, got {rel_path!r}")
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"rel_path must be canonical, got {rel_path!r}")
    return "/".join(parts)


_next_token = 0

def _gen_token() -> int:
    global _next_token
    _next_token += 1
    return _next_token


@dataclass
class PendingChange:
    root: str
    rel_path: str
    fingerprint: str
    observed_at: float
    token: int  # W2-003: monotonic generation for conditional acknowledgement
    status: str = "unresolved"  # unresolved | acknowledged

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "path": self.rel_path,
            "status": self.status,
            "observed_at": self.observed_at,
            "token": self.token,
        }


class ExternalChangeRegistry:
    """Per-(canonical-root, normalized-rel-path) unresolved external writes."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], PendingChange] = {}
        self._lock = threading.Lock()

    def record(self, root: str, rel_path: str, fingerprint: str) -> int:
        """Record an external write under canonicalized keys. The watcher only
        calls this for origin=external (the app's own writes were attributed
        self by SelfWriteRegistry and never reach here).

        W2-003 / T-33: token generation happens UNDER the registry lock so
        concurrent same-path records receive distinct tokens. A stale token
        from an earlier record cannot acknowledge a newer entry.
        """
        key_root = canonical_key(root)
        key_rel = normalize_rel(rel_path)
        now = _time.monotonic()
        with self._lock:
            token = _gen_token()
            self._entries[(key_root, key_rel)] = PendingChange(
                key_root, key_rel, fingerprint, now, token
            )
        return token

    def acknowledge(self, root: str, rel_path: str, token: int | None = None) -> bool:
        """Explicit user acknowledge: clears one pending change.

        W2-003: when token is provided, the acknowledgement is conditional --
        only succeeds if the entry's token matches (same change the user saw).
        A newer write must remain pending."""
        key_root = canonical_key(root)
        key_rel = normalize_rel(rel_path)
        with self._lock:
            entry = self._entries.get((key_root, key_rel))
            if entry is None:
                return False
            if token is not None and entry.token != token:
                return False  # stale acknowledgement -- newer write exists
            self._entries.pop((key_root, key_rel), None)
            return True

    def pending(self, root: str | None = None) -> list[PendingChange]:
        with self._lock:
            items = [
                c
                for c in self._entries.values()
                if root is None or c.root == canonical_key(root)
            ]
            return sorted(items, key=lambda c: (c.root, c.rel_path))

    def unresolved(self, root: str) -> list[PendingChange]:
        """Unacknowledged boundary-relevant changes for one project.

        Collect refuses when any exist: an external write to ANY of the
        project's files (source or .saipen) that the app cannot attribute is
        exactly the "unexplained external write" the boundary check exists for.
        """
        return [c for c in self.pending(root) if c.status == "unresolved"]


_registry: ExternalChangeRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ExternalChangeRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ExternalChangeRegistry()
        return _registry
