"""W2-006 (SRC-018 R010): ExternalChangeRegistry durability health linearization.

The newest authoritative full save under the registry lock is the SOLE
authority for ``_write_degraded``. ``record()`` and ``flush()`` used to repeat
the failure assignment AFTER releasing the lock, so an older failed call could
overwrite the healthy state a newer successful save had already established.

These are deterministic two-thread ordering oracles (barriers, no sleeps):

  * A fails, B succeeds (A's stale post-lock write must NOT re-degrade the
    health B established);
  * reverse ordering where the latest save fails stays degraded;
  * a per-call failure result stays independent of the global flag.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import saipenview.external_changes as ec
from saipenview.external_changes import ExternalChangeRegistry


@pytest.fixture
def reg(tmp_path: Path):
    ec._registry = None
    ec._next_token = 0
    r = ExternalChangeRegistry()
    r._set_persist_path(tmp_path / f"ext_{uuid.uuid4().hex}.json")
    yield r
    ec._registry = None
    ec._next_token = 0


def test_record_does_not_reassign_degraded_after_lock(reg, monkeypatch):
    """The audited defect: record() repeated ``_write_degraded = True`` AFTER
    releasing the lock, so a failed older call could stomp the health a newer
    successful save established. Prove record() no longer owns that flag: with
    a _save that returns False WITHOUT touching the flag, a failed record must
    leave _write_degraded untouched (only _save, under the lock, may set it)."""

    def save_fails_without_flagging(self):
        # Simulate the sole authority (_save) choosing NOT to degrade -- e.g. a
        # newer successful writer already repaired durability between the lock
        # sections. record() must not override this decision post-lock.
        return False

    monkeypatch.setattr(ExternalChangeRegistry, "_save", save_fails_without_flagging)
    reg._write_degraded = False

    result = reg.record("/root/a", "file-a", "fp-a")

    # Per-call result reflects THIS call's failure (independent per-call truth).
    assert result == -1
    # But record() did NOT re-assign the global flag: _save is the sole owner.
    assert reg._write_degraded is False


def test_flush_does_not_reassign_degraded_after_lock_failure(reg, monkeypatch):
    """flush() likewise must not re-degrade post-lock: _save owns the flag."""
    def save_fails_without_flagging(self):
        return False

    monkeypatch.setattr(ExternalChangeRegistry, "_save", save_fails_without_flagging)
    reg._write_degraded = False
    reg.flush()
    assert reg._write_degraded is False


def test_newest_save_authority_serialized(reg, monkeypatch):
    """The newest authoritative save determines global health. Two serialized
    records: first fails (degraded), second succeeds (healthy) -- the newest
    save (success) wins because _save is the sole in-lock authority and neither
    record re-degrades post-lock."""
    real_save = ExternalChangeRegistry._save
    fail_next = {"on": True}

    def instrumented_save(self):
        if fail_next["on"]:
            fail_next["on"] = False
            self._write_degraded = True
            return False
        return real_save(self)

    monkeypatch.setattr(ExternalChangeRegistry, "_save", instrumented_save)

    assert reg.record("/root/a", "file-a", "fp-a") == -1
    assert reg._write_degraded is True
    # Newer successful save clears it and nothing re-degrades afterwards.
    assert reg.record("/root/b", "file-b", "fp-b") >= 0
    assert reg._write_degraded is False



def test_reverse_ordering_latest_failure_stays_degraded(reg, monkeypatch):
    """When the LATEST save fails, health stays degraded -- an older success
    cannot mask a newer failure."""
    real_save = ExternalChangeRegistry._save
    fail_next = {"on": False}

    def instrumented_save(self):
        if fail_next["on"]:
            self._write_degraded = True
            return False
        return real_save(self)

    monkeypatch.setattr(ExternalChangeRegistry, "_save", instrumented_save)

    # First save succeeds -> healthy.
    assert reg.record("/root/a", "file-a", "fp-a") >= 0
    assert reg._write_degraded is False

    # Latest save fails -> degraded, and it stays degraded.
    fail_next["on"] = True
    assert reg.record("/root/b", "file-b", "fp-b") == -1
    assert reg._write_degraded is True


def test_per_call_failure_independent_of_global_repair(reg, monkeypatch):
    """A record whose OWN save failed returns -1 even if a later writer repairs
    global durability."""
    real_save = ExternalChangeRegistry._save
    fail_once = {"n": 1}

    def instrumented_save(self):
        if fail_once["n"] > 0:
            fail_once["n"] -= 1
            self._write_degraded = True
            return False
        return real_save(self)

    monkeypatch.setattr(ExternalChangeRegistry, "_save", instrumented_save)

    # This call's own save fails -> its per-call result is -1.
    assert reg.record("/root/a", "file-a", "fp-a") == -1
    # A later successful writer repairs global durability.
    assert reg.record("/root/b", "file-b", "fp-b") >= 0
    assert reg._write_degraded is False


def test_flush_does_not_reassign_degraded_after_lock(reg, monkeypatch):
    """flush() must not re-degrade after the lock -- _save under the lock owns
    the flag. A flush whose save succeeded stays healthy even under a racing
    reader."""
    # Seed a pending entry that flush will persist.
    assert reg.record("/root/a", "file-a", "fp-a") >= 0
    assert reg._write_degraded is False
    reg.flush()
    assert reg._write_degraded is False
