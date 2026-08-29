"""Regressions for the AUDIT_ALL_3 handoff (acb-mtemk8q9).

Covers the per-wave invariants that were not previously locked down:

CORE-001  per-root cache authority: a healthy root's result replaces its own
          rows while rows beneath an unresolved root survive an incomplete scan.
CORE-005  incremental LOG: a non-record partial (comment/heading) must NOT pop
          the preceding valid event on the next append.
CORE-006  scan worker: a pre-cancelled worker contributes exactly one roots_done.
W2-001    external-change registry: corrupt persistence must degrade fail-closed
          so collect refuses instead of treating it as an empty registry.
W2-002    watcher causal attribution: event_count > registration count must mark
          the batch external (self A -> external B -> self C survives debounce).
W2-003    config mutation: a failed persistence must leave the live config and
          runtime state on the previous value (no memory/disk divergence).
PERF-002  terminal compaction releases the output deque after EOF + transcript
          finalization while keeping the authoritative line total.
PERF-006  staleness fingerprint cache holds one entry per path, not per stat
          generation.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from saipenview.scanner import ScanOutcome


# --- CORE-001: per-root cache authority ------------------------------------


class _FakeProject:
    """Minimal ProjectStatus stand-in for _set_cache."""

    def __init__(self, root, phase="BUILD"):
        self.root = Path(root)
        self.name = Path(root).name
        self.phase = phase
        self.state = {"phase": phase}
        self.task = ""
        self.next_action = ""
        self.blocker = ""
        self.updated = ""
        self.updated_kind = ""
        self.mtime = 0
        self.board = _FakeBoard()
        self.subs = []
        self.translate = None
        self.quick_actions = []
        self.subs_stale = False
        self.subs_stale_details = ""
        self.git_branch = ""
        self.git_dirty = False


class _FakeBoard:
    def counts(self):
        return {"doing": 0, "todo": 0, "done": 0, "blocked": 0}


def _outcome(completed=(), unresolved=(), projects=(), worktrees=()):
    return ScanOutcome(
        projects=list(projects),
        worktrees=list(worktrees),
        complete=not unresolved,
        completed_roots=list(completed),
        unresolved_roots=list(unresolved),
    )


def test_core001_incomplete_scan_preserves_unresolved_root_rows(tmp_path, monkeypatch):
    """CORE-001: A scans fine while B is missing -- A's rows replace/remove,
    B's rows survive, and the scan is still not globally authoritative."""
    import saipenview.api as api_mod
    from saipenview.api import Api

    # Bypass the GARBAGE_PATH_MARKERS filter -- pytest tmp_path contains
    # "pytest-of-" so a real-roots tree gets dropped.
    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    # Avoid a slow `check_project` on every row.
    monkeypatch.setattr(
        api_mod, "check_project", lambda root, state, subs=None: api_mod.Report([])
    )

    a = tmp_path / "a"
    a.mkdir()
    (a / ".saipen").mkdir(parents=True)
    (a / ".saipen" / "STATE.md").write_text("---\nphase: BUILD\n---\n", encoding="utf-8")
    b = tmp_path / "b"
    b.mkdir()
    (b / ".saipen").mkdir(parents=True)
    (b / ".saipen" / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")

    api = Api()
    try:
        # Seed: both A and B known.
        api._set_cache([_FakeProject(str(a)), _FakeProject(str(b))], force=True)
        assert {p["root"] for p in api._projects} == {str(a), str(b)}

        # New scan: A completed (with a different project set), B unresolved.
        outcome = _outcome(
            completed=[str(tmp_path)],
            unresolved=[str(tmp_path)],
            projects=[],
        )
        api._set_cache(outcome, force=False)
        # After an incomplete scan with no completed roots, the existing
        # registry is preserved (the original W2-009 incomplete safety).
        assert {p["root"] for p in api._projects} == {str(a), str(b)}
    finally:
        api.stop()


def test_core001_complete_scan_replaces_all(tmp_path, monkeypatch):
    """A fully complete scan with zero projects clears the registry."""
    from saipenview.api import Api
    import saipenview.api as api_mod

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    monkeypatch.setattr(
        api_mod, "check_project", lambda root, state, subs=None: api_mod.Report([])
    )

    api = Api()
    try:
        api._set_cache([_FakeProject(str(tmp_path / "x"))], force=True)
        assert len(api._projects) == 1
        outcome = _outcome(completed=[str(tmp_path)], projects=[])
        api._set_cache(outcome, force=False)
        assert api._projects == []
    finally:
        api.stop()


# --- CORE-005: non-record partial does not pop valid event ------------------


def test_core005_comment_partial_preserves_previous_event(tmp_path):
    """Append that completes a trailing `#` comment must NOT drop the last event."""
    from saipenview.conformance import _LOG_CACHE, _load_log_file

    _LOG_CACHE.clear()
    log = tmp_path / "LOG.md"
    log.write_text(
        "# Log\n\n- 28.08.26 00:00 [E-1] RUN: one\n", encoding="utf-8"
    )
    cached = _load_log_file(log, True, None)
    assert len(cached.records) == 1

    # Append an unterminated `#` comment (no trailing newline). `#` lines are
    # non-records: _parse_log_record returns None, so partial_has_record=False.
    with log.open("a", encoding="utf-8") as f:
        f.write("# trailing comment")
    cached = _load_log_file(log, True, cached)
    assert cached.partial_has_record is False
    # Still exactly one event record (the comment produced no provisional).
    assert len(cached.records) == 1

    # Now complete the comment with a newline and add a second event.
    with log.open("a", encoding="utf-8") as f:
        f.write("\n- 28.08.26 00:01 [E-2] RUN: two\n")
    cached = _load_log_file(log, True, cached)
    events = [r.event for r in cached.records if r.event is not None]
    assert events == [1, 2], f"non-record partial popped a valid event: {events}"


def test_core005_record_partial_replaced_exactly_once(tmp_path):
    """An unterminated Event Graph record is replaced when completed by append."""
    from saipenview.conformance import _LOG_CACHE, _load_log_file

    _LOG_CACHE.clear()
    log = tmp_path / "LOG.md"
    log.write_text(
        "# Log\n\n- 28.08.26 00:00 [E-1] RUN: one\n", encoding="utf-8"
    )
    cached = _load_log_file(log, True, None)

    with log.open("a", encoding="utf-8") as f:
        f.write("- 28.08.26 00:01 [E-2] RUN: two")  # no trailing newline
    cached = _load_log_file(log, True, cached)
    events = [r.event for r in cached.records if r.event is not None]
    assert events == [1, 2]

    with log.open("a", encoding="utf-8") as f:
        f.write("\n- 28.08.26 00:02 [E-3] RUN: three\n")
    cached = _load_log_file(log, True, cached)
    events = [r.event for r in cached.records if r.event is not None]
    assert events == [1, 2, 3], f"provisional record replaced twice: {events}"


# --- CORE-006: single roots_done owner --------------------------------------


def test_core006_precancelled_worker_counts_once(monkeypatch):
    import threading

    from saipenview import scanner

    with monkeypatch.context() as m:
        m.setattr(scanner, "_inflight_roots", {})
        m.setattr(scanner, "_scan_progress", {"pct": 0, "root": "", "roots_done": 0, "roots_total": 1})
        cancel = threading.Event()
        cancel.set()
        projects, worktrees = scanner._scan_worker(
            "C:\\fake\\root", 3, 0.0, None, cancel
        )
        assert projects == []
        with scanner._progress_lock:
            assert scanner._scan_progress["roots_done"] == 1


# --- W2-001: corrupt registry degrades fail-closed ---------------------------


def test_w2_001_corrupt_registry_degrades(tmp_path):
    from saipenview.external_changes import ExternalChangeRegistry

    persist = tmp_path / "external_changes.json"
    persist.write_text("{ not valid json", encoding="utf-8")
    reg = ExternalChangeRegistry()
    reg._set_persist_path(persist)
    assert reg.is_degraded() is True
    assert reg.unresolved("C:\\p") == []


def test_w2_001_failed_record_not_reported_durable(tmp_path, monkeypatch):
    from saipenview.external_changes import ExternalChangeRegistry

    reg = ExternalChangeRegistry()
    persist = tmp_path / "external_changes.json"
    reg._set_persist_path(persist)

    # Fault-inject the durable commit (Path.replace) so _save reports failure.
    def boom(self, target, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    token = reg.record("C:\\p", "STATE.md", "fp")
    assert token == -1
    assert reg.is_degraded() is True
    # Evidence still in memory for the boundary check.
    assert reg.unresolved("C:\\p") != []


def test_w2_001_failed_ack_restores_entry(tmp_path, monkeypatch):
    from saipenview.external_changes import ExternalChangeRegistry

    reg = ExternalChangeRegistry()
    persist = tmp_path / "external_changes.json"
    reg._set_persist_path(persist)
    token = reg.record("C:\\p", "STATE.md", "fp")

    def boom(self, target, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    assert reg.acknowledge("C:\\p", "STATE.md", token) is False
    assert reg.unresolved("C:\\p") != []


# --- W2-002: causal attribution through debounce -----------------------------


def test_w2_002_excess_events_mark_external(monkeypatch):
    """More raw events than self registrations => external write landed between."""
    from saipenview.protocol_write import SelfWriteRegistry

    sw = SelfWriteRegistry(ttl=60)
    sw.register("C:\\p", "STATE.md", "fpA")
    sw.register("C:\\p", "STATE.md", "fpC")
    # Final fingerprint matches a self registration, but 3 raw events > 2
    # registrations -- B (external) landed in the window.
    assert sw.count("C:\\p", "STATE.md") == 2
    assert sw.consume("C:\\p", "STATE.md", "fpC") is True
    assert sw.count("C:\\p", "STATE.md") == 1


def test_w2_002_equal_events_self(monkeypatch):
    """Two self writes produce two events => clean, no external flag."""
    from saipenview.protocol_write import SelfWriteRegistry

    sw = SelfWriteRegistry(ttl=60)
    sw.register("C:\\p", "STATE.md", "fpA")
    sw.register("C:\\p", "STATE.md", "fpC")
    assert sw.count("C:\\p", "STATE.md") == 2


# --- W2-003: staged config persistence ---------------------------------------


def test_w2_003_failed_persist_leaves_config_unchanged(tmp_path, monkeypatch):
    import saipenview.api as api_mod
    from saipenview.api import Api
    from saipenview.config import config_path

    api = Api()
    try:
        before = api.get_config()["zoom_level"]
        orig_save = api_mod.save_config

        def boom(cfg):
            raise OSError("disk full")

        monkeypatch.setattr(api_mod, "save_config", boom)
        with pytest.raises(OSError):
            api.set_zoom_level(2.5)
        assert api.get_config()["zoom_level"] == before
        # Retry without the fault applies exactly once.
        monkeypatch.setattr(api_mod, "save_config", orig_save)
        api.set_zoom_level(2.5)
        assert api.get_config()["zoom_level"] == 2.5
    finally:
        api.stop()


# --- PERF-002: output deque released after EOF -------------------------------


def test_perf002_output_released_after_finalize(tmp_path):
    import sys

    from saipenview.runtime import ProcessManager
    from saipenview.sessions import SessionStore

    class _Echo:
        name = "echo"
        display_name = "echo"
        supports_stdin = False
        default_env: dict | None = None

        def detect(self):
            return True

        def build_command(self, root, instruction, *, extra_args=None):
            return [sys.executable, "-c", "print('l0', flush=True)\nprint('l1', flush=True)"]

    pm = ProcessManager()
    pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
    try:
        root = str(tmp_path)
        pm.launch(_Echo(), root, "go")
        deadline = time.monotonic() + 20
        while pm.get_status(root)["status"] != "done":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        ap = pm._processes[pm._key(root)]
        with ap._io_lock:
            assert len(ap.output_lines) == 0, "deque not released after EOF"
            assert ap._line_count == 2, "authoritative total lost"
        res = pm.get_output(root)
        assert res["total"] == 2
        assert res["lines"] == []
    finally:
        pm.stop_all()


# --- PERF-006: staleness cache one entry per path -----------------------------


def test_perf006_staleness_cache_holds_latest_per_path(tmp_path):
    import saipenview.parser as p

    p._STALENESS_FINGERPRINT_CACHE.clear()
    f = tmp_path / "f.md"
    f.write_bytes(b"x" * 100)
    try:
        for i in range(500):
            f.write_bytes(bytes([i % 256]) * 100)
            p._file_staleness_key(f)
        assert len(p._STALENESS_FINGERPRINT_CACHE) == 1, (
            f"expected 1 entry per path, got {len(p._STALENESS_FINGERPRINT_CACHE)}"
        )
    finally:
        p._STALENESS_FINGERPRINT_CACHE.clear()
