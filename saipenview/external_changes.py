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

T-37 / W2-027: persistence. The registry is backed by a JSON file in the
_data/ directory. On every mutation (record/acknowledge) the file is atomically
rewritten. On construction the file is loaded so unresolved evidence survives
restart.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time as _time
from dataclasses import dataclass
from pathlib import Path

from saipenview.config import config_path
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
_token_lock = threading.Lock()


def _gen_token() -> int:
    global _next_token
    with _token_lock:
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
            "fingerprint": self.fingerprint,
            "status": self.status,
            "observed_at": self.observed_at,
            "token": self.token,
        }


class ExternalChangeRegistry:
    """Per-(canonical-root, normalized-rel-path) unresolved external writes."""

    _PERSIST_FILE = "external_changes.json"

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], PendingChange] = {}
        self._lock = threading.Lock()
        self._persist_path: Path | None = None
        self._degraded: bool = False
        self._load()

    def _set_persist_path(self, path: Path) -> None:
        """Override the default persist path (for tests)."""
        self._persist_path = path
        self._entries.clear()
        self._degraded = False
        self._load()

    def _persist_file(self) -> Path:
        if self._persist_path is not None:
            return self._persist_path
        return config_path().parent / self._PERSIST_FILE

    def _load(self) -> None:
        """Load persisted entries and generation counter from disk.

        W2-001: distinguish "valid empty registry" from "registry
        unreadable/corrupt". A corrupt existing evidence file puts the
        registry into a degraded/unknown state that callers must treat as
        boundary-blocking. The full record set is kept in memory; only the
        boolean degraded flag is exposed to gate collect().
        """
        global _next_token
        path = self._persist_file()
        if not path.exists():
            self._degraded = False
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                items = data.get("entries", [])
                saved_token = data.get("next_token", 0)
            else:
                items = data
                saved_token = 0
            if not isinstance(items, list):
                self._degraded = True
                return
            loaded_max = int(saved_token) if isinstance(saved_token, int) else 0
            for item in items:
                try:
                    pc = PendingChange(
                        root=item["root"],
                        rel_path=item["path"],
                        fingerprint=item["fingerprint"],
                        observed_at=item["observed_at"],
                        token=item["token"],
                        status=item.get("status", "unresolved"),
                    )
                    self._entries[(pc.root, pc.rel_path)] = pc
                    loaded_max = max(loaded_max, pc.token)
                except (KeyError, TypeError, ValueError):
                    # W2-001: a malformed row poisons the whole file -- we
                    # cannot prove the registry's persisted content. Refuse
                    # to pretend it's empty.
                    self._degraded = True
                    return
            with _token_lock:
                _next_token = max(_next_token, loaded_max)
            self._degraded = False
        except (OSError, json.JSONDecodeError, ValueError):
            self._degraded = True

    def _save(self) -> bool:
        """Atomically write entries and generation counter to disk.

        W2-001: returns True only when the durable commit succeeded. A
        caller holding the registry lock can rely on the return value to
        decide whether to report success or surface a degraded/durability
        failure to the boundary.
        """
        path = self._persist_file()
        tmp: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / (
                path.name
                + f".tmp.{os.getpid()}.{threading.get_ident()}.{_time.monotonic_ns()}"
            )
            with _token_lock:
                next_token = _next_token
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "next_token": next_token,
                        "entries": [c.to_dict() for c in self._entries.values()],
                    },
                    f,
                    indent=2,
                )
            tmp.replace(path)
            return True
        except OSError as exc:
            print(
                f"SAIPENVIEW: external_changes persistence write failed: {exc}",
                file=sys.stderr,
            )
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    def flush(self) -> None:
        """W2-008 + W2-001: synchronous flush -- ensure on-disk state matches memory.

        Called by api.stop() so shutdown never loses the last batch of
        mutations to a background write. Returns the durability result so
        shutdown/error reporting can surface persistent failure.
        """
        with self._lock:
            ok = self._save()
        self._degraded = self._degraded or not ok

    def record(self, root: str, rel_path: str, fingerprint: str) -> int:
        """Record an external write under canonicalized keys.

        W2-001: returns -1 when the durable persistence commit failed.
        A failed record remains in memory as boundary evidence (so the
        caller still gets protection) but the caller must not consider the
        change durably persisted. W2-003 / T-33: token generation happens
        UNDER the registry lock so concurrent same-path records receive
        distinct tokens.
        """
        key_root = canonical_key(root)
        key_rel = normalize_rel(rel_path)
        now = _time.monotonic()
        with self._lock:
            token = _gen_token()
            self._entries[(key_root, key_rel)] = PendingChange(
                key_root, key_rel, fingerprint, now, token
            )
            ok = self._save()
        if not ok:
            self._degraded = True
            return -1
        return token

    def acknowledge(self, root: str, rel_path: str, token: int | None = None) -> bool:
        """Explicit user acknowledge: clears one pending change.

        W2-001: if persistence fails after we already removed the entry from
        memory, the caller must NOT see True. Restore the entry so the
        registry reflects what is actually on disk, and surface failure.
        W2-003: when token is provided, the acknowledgement is conditional --
        only succeeds if the entry's token matches (same change the user saw).
        A newer write must remain pending.
        """
        key_root = canonical_key(root)
        key_rel = normalize_rel(rel_path)
        with self._lock:
            entry = self._entries.get((key_root, key_rel))
            if entry is None:
                return False
            if token is not None and entry.token != token:
                return False  # stale acknowledgement -- newer write exists
            removed = self._entries.pop((key_root, key_rel), None)
            if not self._save():
                # W2-001: persistence failed -- the in-memory removal is
                # not durable. Restore the entry and report failure so the
                # boundary keeps blocking collect.
                if removed is not None:
                    self._entries[(key_root, key_rel)] = removed
                self._degraded = True
                return False
            return True

    def is_degraded(self) -> bool:
        """W2-001: True when the on-disk registry is unreadable/corrupt or
        the last persistence write failed. While degraded, collect boundaries
        must fail closed -- the registry cannot be trusted to enumerate
        unresolved external changes."""
        return self._degraded

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
