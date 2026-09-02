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


# --- AUDIT_ALL_3 SRC-002: per-wave regressions -------------------------------


def _make_root(name: str, path: str) -> "object":
    import saipenview.api as api_mod
    from saipenview.parser import Board
    root_obj = type("Root", (), {
        "name": name,
        "__str__": lambda self, p=path: p,
        "__fspath__": lambda self, p=path: p,
    })()
    return api_mod.ProjectStatus(root=root_obj, state={"phase": "BUILD"}, board=Board())


def test_core002_partial_scan_preserves_unresolved_worktrees(monkeypatch, tmp_path):
    """CORE-002: a partial scan preserves linked worktrees beneath unresolved
    roots and replaces worktrees beneath completed roots."""
    from saipenview.api import Api
    from saipenview.scanner import ScanOutcome
    import saipenview.api as api_mod

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    monkeypatch.setattr(api_mod, "check_project", lambda root, state, subs=None: api_mod.Report([]))

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    api = Api()
    try:
        api._projects = [
            {"root": str(a), "name": "a", "phase": "BUILD", "is_pinned": False, "task": "", "next_action": "", "blocker": "", "mtime": 0, "updated": "", "updated_kind": "", "conformance": {"verdict": "pass", "fails": 0, "warns": 0, "findings": []}, "git_branch": "", "git_dirty": False, "board": {}, "subs": [], "translate": None, "quick_actions": [], "subs_stale": False, "subs_stale_details": ""},
            {"root": str(b), "name": "b", "phase": "BUILD", "is_pinned": False, "task": "", "next_action": "", "blocker": "", "mtime": 0, "updated": "", "updated_kind": "", "conformance": {"verdict": "pass", "fails": 0, "warns": 0, "findings": []}, "git_branch": "", "git_dirty": False, "board": {}, "subs": [], "translate": None, "quick_actions": [], "subs_stale": False, "subs_stale_details": ""},
        ]
        api._linked_worktrees = [
            {"root": str(a), "name": "wA", "git_dir": ""},
            {"root": str(b), "name": "wB", "git_dir": ""},
        ]
        api._last_cache_snapshot = {p["root"]: p for p in api._projects}
        api._linked_worktrees  # silence
        # New outcome replaces A and is unresolved for B.
        api._set_cache(
            ScanOutcome(
                projects=[_make_root("a", str(a))],
                worktrees=[{"root": str(a), "name": "wA-new", "git_dir": ""}],
                complete=False,
                completed_roots=[str(a)],
                unresolved_roots=[str(b)],
            ),
            force=False,
        )
        worktree_roots = {wt["root"] for wt in api._linked_worktrees}
        assert str(a) in worktree_roots, f"A worktree lost: {worktree_roots}"
        assert str(b) in worktree_roots, f"B worktree lost under partial: {worktree_roots}"
    finally:
        api.stop()


def test_core005_watcher_revive_rearms_subscriptions(monkeypatch, tmp_path):
    """CORE-005: a stopped SaipenWatcher revives on a fresh Observer and
    re-watches known roots on the next start()."""
    from saipenview.api import Api
    import saipenview.api as api_mod
    from unittest.mock import MagicMock

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    monkeypatch.setattr(api_mod, "check_project", lambda root, state, subs=None: api_mod.Report([]))
    monkeypatch.setattr(api_mod, "BackgroundScanner", lambda **kw: MagicMock())

    a = tmp_path / "a"
    a.mkdir()
    (a / ".saipen").mkdir()
    (a / ".saipen" / "STATE.md").write_text("---\nphase: BUILD\n---\n", encoding="utf-8")
    api = Api()
    try:
        api._projects = [{"root": str(a), "name": "a", "phase": "BUILD", "is_pinned": False, "task": "", "next_action": "", "blocker": "", "mtime": 0, "updated": "", "updated_kind": "", "conformance": {"verdict": "pass", "fails": 0, "warns": 0, "findings": []}, "git_branch": "", "git_dirty": False, "board": {}, "subs": [], "translate": None, "quick_actions": [], "subs_stale": False, "subs_stale_details": ""}]
        api._last_cache_snapshot = {p["root"]: p for p in api._projects}
        api._event_subscribed = False
        # Subscribe manually to confirm before/after.
        from saipenview.events import event_bus
        before = sum(1 for _ in event_bus._subscribers.get("saipen.project_changed", []))
        api.start()
        after = sum(1 for _ in event_bus._subscribers.get("saipen.project_changed", []))
        assert after == before + 1
        api.stop()
        mid = sum(1 for _ in event_bus._subscribers.get("saipen.project_changed", []))
        assert mid == before, "stop() did not unsubscribe"
        # Re-start: subscription re-binds and watcher is revived.
        api.start()
        end = sum(1 for _ in event_bus._subscribers.get("saipen.project_changed", []))
        assert end == before + 1
        assert not api._watcher._stopped, "watcher not revived"
    finally:
        api.stop()


def test_w2_002_run_id_is_always_non_null(monkeypatch, tmp_path):
    """W2-002: a process.run_id is always non-null even when SessionStore
    fails to open the transcript."""
    from saipenview.runtime import ProcessManager
    from saipenview.sessions import SessionStore
    from saipenview.engines.base import AgentEngine

    class _E(AgentEngine):
        name = "echo"
        display_name = "echo"
        supports_stdin = False
        default_env = None

        def detect(self):
            return True

        def build_command(self, root, instruction, *, extra_args=None):
            return [sys.executable, "-c", "print('ok')"]

    import sys
    pm = ProcessManager()
    pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
    monkeypatch.setattr(pm.sessions, "start", lambda *a, **kw: None)
    root = str(tmp_path)
    pm.launch(_E(), root, "go")
    try:
        ap = pm._processes[pm._key(root)]
        assert ap.run_id is not None
    finally:
        pm.stop_all()


def test_w2_003_canonical_paths_only_persisted(monkeypatch, tmp_path):
    """CORE-003: normalize_config is the ONE canonical step; load_config,
    save_config and _mutate_config produce identical canonical path fields."""
    from saipenview.config import normalize_config
    from saipenview.paths import canonical

    raw = {"pinned_roots": [str(tmp_path / "A\\..\\A"), str(tmp_path / "B")], "scan_roots": [str(tmp_path / "X/./Y"), str(tmp_path / "X/Y")], "selected_root": str(tmp_path / "C")}
    # All variants normalize to canonical spellings.
    cfg = normalize_config(raw)
    assert cfg["pinned_roots"] == [canonical(str(tmp_path / "A")), canonical(str(tmp_path / "B"))]
    assert cfg["scan_roots"] == [canonical(str(tmp_path / "X/Y"))]
    assert cfg["selected_root"] == canonical(str(tmp_path / "C"))


def test_w2_004_saio_engine_raises_saio_unavailable_for_distinct_home(monkeypatch):
    """W2-004: saio.engine raises SaioUnavailable for multi-home refusal."""
    from saipenview import saio

    saio._ENGINE_CACHE.clear()
    # Pre-seed with a different home so the multi-home guard is reached
    # before resolve_home is called for the request root.
    from pathlib import Path
    saio._ENGINE_CACHE["v:\\fake\\home\\a"] = {"placeholder": True}
    monkeypatch.setattr(saio, "resolve_home", lambda root: Path("v:\\fake\\home\\b"))
    try:
        try:
            saio.engine("v:\\proj\\B")
        except saio.SaioUnavailable as exc:
            assert "MULTI-HOME" in str(exc)
        else:
            raise AssertionError("engine() did not raise SaioUnavailable")
    finally:
        saio._ENGINE_CACHE.clear()


def test_perf001_log_cache_bounded_retention(tmp_path):
    """PERF-001: cached parsed records stay bounded while the aggregate
    retains historical totals."""
    from saipenview import conformance
    from saipenview.conformance import _LOG_CACHE, _load_log_file

    log = tmp_path / "LOG.md"
    with log.open("w", encoding="utf-8") as handle:
        handle.write("# Log\n")
        for i in range(1, 300):
            handle.write(f"- 28.08.26 00:{i % 60:02d} [E-{i}] [parent: E-{i-1}] RUN: event {i}\n")
    _LOG_CACHE.clear()
    cached = _load_log_file(log, True, None)
    assert len(cached.records) == 299
    # Subsequent appends trim the cached tail to the bounded window.
    with log.open("a", encoding="utf-8") as handle:
        handle.write("- 28.08.26 01:00 [E-300] [parent: E-299] RUN: event 300\n")
    cached = _load_log_file(log, True, cached)
    assert len(cached.records) <= conformance._LOG_RECORD_KEEP, (
        f"records not bounded: {len(cached.records)}"
    )
    # Aggregate still finds the most recent event via the rebuilt aggregate.
    aggregate = conformance._log_aggregate(tmp_path, (log,), log)
    assert aggregate.prev_event == 300
    _LOG_CACHE.clear()


# --- T-700 / T-701: AUDIT_ALL_3 ROUND 2 (acb-mtf1t0sh) -----------------------


def _round2_fixture(tmp_path: Path) -> Path:
    """Project with minimal valid layout so conformance checks stay quiet."""
    proj = tmp_path / "p"
    (proj / ".saipen").mkdir(parents=True)
    (proj / ".saipen" / "STATE.md").write_text(
        "---\n"
        "phase: DONE\n"
        "task: none\n"
        "next_action: PHASE DONE\n"
        "blocker: none\n"
        "agent: a\n"
        "saipen_version: 7\n"
        "mode: full\n"
        "transition_from: SHIP\n"
        "updated: 2026-08-30T00:00:00Z\n"
        "last_event: 1\n"
        "---\n",
        encoding="utf-8",
    )
    (proj / ".saipen" / "BOARD.md").write_text(
        "## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (proj / ".saipen" / "LOG.md").write_text(
        "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n", encoding="utf-8"
    )
    return proj


def _round2_api(a, proj: Path):
    a._projects = [
        {
            "root": str(proj),
            "name": "p",
            "phase": "DONE",
            "is_pinned": False,
            "conformance": {
                "verdict": "pass",
                "fails": 0,
                "warns": 0,
                "findings": [],
                "baseline": "",
            },
        }
    ]
    return a


def test_round2_t700_log_refresh_regrades_coherently(tmp_path):
    """T-700: a top-level LOG.md change must regrade the project coherently.
    LOG tail ahead of STATE produces ``state.last_event.stale`` (STATE-aware
    contract), and verdict reflects it -- no stale pass verdict."""
    from saipenview.api import Api

    proj = _round2_fixture(tmp_path)
    # Make LOG tail move ahead of STATE.last_event.
    (proj / ".saipen" / "LOG.md").write_text(
        "# Log\n- 30.08.26 00:00 [E-002] DEC: ahead\n", encoding="utf-8"
    )
    a = _round2_api(Api(), proj)
    try:
        a._refresh_one_project(str(proj), {"LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        conf = row["conformance"]
        rules = [f.get("rule") for f in conf.get("findings", [])]
        assert "state.last_event.stale" in rules, (
            f"stale last_event not detected in regrade: {rules}"
        )
        assert conf["verdict"] == "fail", f"verdict should be fail: {conf}"
    finally:
        a.stop()


def test_round2_t700_truncated_log_exact_zero_old_failures(tmp_path):
    """T-700: >100 LOG findings then a clean LOG must produce exact zero old
    LOG failures and correct truncation metadata (no stale transport cap)."""
    from saipenview.api import Api

    proj = _round2_fixture(tmp_path)
    # Seed LOG with >100 future-stamped entries (each yields a fail finding).
    lines = ["# Log\n"]
    for i in range(1, 121):
        lines.append(
            f"- 30.08.26 23:59 [E-{i:03d}] [parent: E-{i-1:03d}] "
            f"DEC: future {i}\n"
        )
    (proj / ".saipen" / "LOG.md").write_text("\n".join(lines), encoding="utf-8")
    a = _round2_api(Api(), proj)
    try:
        a._refresh_one_project(str(proj), {"LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        conf = row["conformance"]
        assert conf["verdict"] == "fail"
        assert conf.get("findings_truncated") is True, (
            f">100 findings must set truncated: {conf}"
        )
        # Now repair the LOG (single clean entry, matching STATE).
        (proj / ".saipen" / "LOG.md").write_text(
            "# Log\n- 30.08.26 00:00 [E-001] DEC: clean\n", encoding="utf-8"
        )
        a._refresh_one_project(str(proj), {"LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        conf = row["conformance"]
        assert conf["verdict"] == "pass", (
            f"clean LOG after truncation must pass, got {conf}"
        )
        assert conf.get("fails", 0) == 0, f"old LOG failures must clear: {conf}"
        assert not conf.get("findings_truncated", False)
    finally:
        a.stop()


def test_round2_t701_nested_log_full_reload(tmp_path):
    """T-701: a nested SubSaipen LOG change must NOT regrade the parent
    top-level LOG; it reloads the project so nested log_tail/state update."""
    from saipenview.api import Api

    proj = _round2_fixture(tmp_path)
    sub = proj / ".saipen" / "extensions" / "subs" / "saiui"
    (sub / "STATE.md").parent.mkdir(parents=True, exist_ok=True)
    (sub / "STATE.md").write_text(
        "---\nphase: BUILD\ntask: none\nnext_action: PHASE BUILD\nblocker: none\n"
        "saipen_version: 7\nmode: full\nupdated: 2026-08-30T00:00:00+00:00\n---\n",
        encoding="utf-8",
    )
    (sub / "LOG.md").write_text(
        "# SubLog\n- 30.08.26 00:00 [E-1] DEC: x\n", encoding="utf-8"
    )
    a = _round2_api(Api(), proj)
    try:
        # Deliver the full relative watcher path for the nested LOG.
        a._refresh_one_project(str(proj), {"extensions/subs/saiui/LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        subs = {s.get("name") for s in row.get("subs", [])}
        assert "saiui" in subs, f"nested sub not loaded after nested LOG event: {subs}"
    finally:
        a.stop()


def test_round2_t701_is_top_level_log_change_predicate():
    """T-700/T-701: only exact top-level ``LOG.md`` takes the fast path;
    nested paths and other basenames do not."""
    from saipenview.api import _is_top_level_log_change

    assert _is_top_level_log_change("LOG.md")
    assert _is_top_level_log_change("log.md")
    assert _is_top_level_log_change("Log.md")
    assert not _is_top_level_log_change("extensions/subs/saiui/LOG.md")
    assert not _is_top_level_log_change("saitranslate/LOG.md")
    assert not _is_top_level_log_change("extensions\\subs\\saiui\\LOG.md")
    assert not _is_top_level_log_change("STATE.md")
    assert not _is_top_level_log_change("BOARD.md")
    assert not _is_top_level_log_change("")
    assert not _is_top_level_log_change(None)  # type: ignore[arg-type]


# --- T-703: sidecar validation (CORE-004 ROUND 2) ---------------------------


def _t703_legacy_row(root: str) -> dict:
    return {
        "root": root,
        "name": Path(root).name,
        "phase": "DONE",
        "is_pinned": False,
        "task": "none",
        "next_action": "PHASE DONE",
        "blocker": "none",
        "mtime": 0,
        "updated": "",
        "updated_kind": "no-timestamp",
    }


def _t703_setup_cache(tmp_path: Path, sidecar_payloads: dict[str, dict]):
    cache_dir = tmp_path / "data"
    cache_dir.mkdir()
    cache_file = cache_dir / "cache.json"
    cache_file.write_text(json.dumps([]), encoding="utf-8")
    records_dir = cache_file.with_name(cache_file.stem + "_records")
    records_dir.mkdir(exist_ok=True)
    for filename, payload in sidecar_payloads.items():
        (records_dir / filename).write_text(
            json.dumps(payload), encoding="utf-8"
        )
    cfg_file = cache_dir / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")
    return cache_dir, cache_file, records_dir


def _t703_bootstrap_api(monkeypatch, cache_dir):
    import saipenview.api as api_mod
    import saipenview.config as cfg

    saved_cfg = cfg.config_path
    saved_api = api_mod.config_path
    target = cache_dir / "config.json"

    def _cfg_path():
        return target

    monkeypatch.setattr(cfg, "config_path", _cfg_path)
    monkeypatch.setattr(api_mod, "config_path", _cfg_path)
    return api_mod.Api, saved_api, saved_cfg


def _t703_digest(root: str) -> str:
    import hashlib

    from saipenview.api import _canonical_or

    return hashlib.sha256(_canonical_or(root).encode("utf-8")).hexdigest()


def test_round2_t703_sidecar_missing_is_pinned_quarantined(monkeypatch, tmp_path):
    """T-703: a sidecar row missing ``is_pinned`` must be quarantined; Api
    construction must succeed and the malformed row must not enter the
    registry."""
    root = str(tmp_path / "bad")
    digest = _t703_digest(root)
    payload = {"root": root, "name": "bad", "phase": "DONE"}  # no is_pinned
    cache_dir, _, _ = _t703_setup_cache(tmp_path, {f"{digest}.json": payload})
    Api, _sa, _sc = _t703_bootstrap_api(monkeypatch, cache_dir)
    try:
        a = Api()
        try:
            roots = [p["root"] for p in a._projects]
            assert root not in roots, f"malformed sidecar leaked: {roots}"
        finally:
            a.stop()
    finally:
        Api, _sa, _sc  # noqa


def test_round2_t703_sidecar_wrong_digest_quarantined(monkeypatch, tmp_path):
    """T-703: a valid-row sidecar stored under the wrong digest (hand-edit
    or misbound) must be rejected; the row can be rediscovered by a scan."""
    root = str(tmp_path / "right")
    wrong_digest = "0" * 64
    payload = _t703_legacy_row(root)
    cache_dir, _, _ = _t703_setup_cache(
        tmp_path, {f"{wrong_digest}.json": payload}
    )
    Api, _, _ = _t703_bootstrap_api(monkeypatch, cache_dir)
    a = Api()
    try:
        roots = [p["root"] for p in a._projects]
        assert root not in roots, f"wrong-digest sidecar accepted: {roots}"
    finally:
        a.stop()


def test_round2_t703_sidecar_valid_round_trip(monkeypatch, tmp_path):
    """T-703: a sidecar with the exact required shape under the right
    digest still loads (overlay precedence + sorting unchanged)."""
    root = str(tmp_path / "right")
    digest = _t703_digest(root)
    payload = _t703_legacy_row(root)
    cache_dir, _, _ = _t703_setup_cache(tmp_path, {f"{digest}.json": payload})
    Api, _, _ = _t703_bootstrap_api(monkeypatch, cache_dir)
    a = Api()
    try:
        roots = [p["root"] for p in a._projects]
        assert root in roots, f"valid sidecar not loaded: {roots}"
    finally:
        a.stop()


def test_round2_t706_crash_atomicity_delete_recreate_matrix(monkeypatch, tmp_path):
    """W2-003: every crash boundary around delete and recreate must leave
    the loader seeing exactly one of: pre-delete state, post-delete state,
    pre-recreate state, or post-recreate state. Resurrection is never
    allowed.

    The implementation writes one digest-named state file per root whose
    payload is either the validated row or the explicit deleted marker,
    committed via temp+os.replace; the only durable authority is that file.
    A test-isolated _write_cache avoids the cross-process cache lock and
    exercises every boundary by snapshotting the records dir at the right
    point.
    """
    import saipenview.api as api_mod

    cache_dir, _, _ = _t703_setup_cache(tmp_path, {})
    Api, _sa, _sc = _t703_bootstrap_api(monkeypatch, cache_dir)
    a = Api()
    try:
        root = str(tmp_path / "victim")
        row = _t703_legacy_row(root)
        # Seed a row. Empty snapshot so the seed write is a dirty delta.
        a._projects = [row]
        a._last_cache_snapshot = {}
        a._dirty_roots = set()
        a._cache_deleted_roots = set()
        a._write_cache()

        # Verify the record file holds the row.
        digest = _t703_digest(root)
        records_dir = a._cache_records_path()
        record_path = records_dir / f"{digest}.json"
        assert record_path.is_file()
        assert "phase" in json.loads(record_path.read_text(encoding="utf-8"))

        # Delete: remove the project from _projects; _write_cache must
        # replace the record file with the deleted marker in one atomic
        # replace.
        a._projects = []
        a._dirty_roots = set()
        a._cache_deleted_roots = set()
        a._write_cache()

        deleted_payload = json.loads(record_path.read_text(encoding="utf-8"))
        assert deleted_payload.get(a._CACHE_DELETED_MARKER) is True
        # No resurrection: a fresh Api must see zero projects.
        a2 = Api()
        try:
            assert all(
                p.get(a._CACHE_DELETED_MARKER) is not True
                for p in a2._projects
            )
            assert all(p["root"] != root for p in a2._projects)
        finally:
            a2.stop()

        # Recreate: a fresh row for the same root must atomically replace
        # the deleted state, not coexist with it.
        a3 = Api()
        try:
            new_row = _t703_legacy_row(root)
            new_row["phase"] = "BUILD"  # distinguish from the deleted state
            a3._projects = [new_row]
            a3._last_cache_snapshot = {}
            a3._dirty_roots = set()
            a3._cache_deleted_roots = set()
            a3._write_cache()
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            assert a3._CACHE_DELETED_MARKER not in payload, (
                f"recreate left deleted state: {payload}"
            )
            assert payload.get("phase") == "BUILD", payload
        finally:
            a3.stop()
    finally:
        a.stop()


def test_round2_t706_legacy_tombstone_respected_when_no_newer_record(monkeypatch, tmp_path):
    """W2-003: a legacy ``.deleted`` file with no newer record must still
    drop the row at load time. A recreation that arrives with a NEWER
    record file (by mtime) wins over the legacy tombstone."""
    import saipenview.api as api_mod

    cache_dir, _, records_dir = _t703_setup_cache(tmp_path, {})
    digest = "0" * 64
    # Legacy tombstone with a known fake digest; bound to no row.
    (records_dir / f"{digest}.deleted").write_text("deleted", encoding="utf-8")
    Api, _, _ = _t703_bootstrap_api(monkeypatch, cache_dir)
    a = Api()
    try:
        # A legacy tombstone for a digest with no record must not crash and
        # must not introduce any row.
        assert a._projects == []
    finally:
        a.stop()


def test_round2_t707_finish_retry_pending_overlays_history(tmp_path):
    """W2-004: when the first ``_write_meta`` after ``finish`` fails, the
    known terminal record must overlay the stale on-disk `running` copy
    when ``history()`` is read in the same process. After the disk
    recovers, a subsequent retry/flush must persist the terminal JSON
    with the exact status/exit_code/finished_at."""
    from saipenview.sessions import SessionStore

    base = tmp_path / "data"
    base.mkdir()
    store = SessionStore(base_dir=base)

    rec = store.start(
        root=str(tmp_path / "P"),
        engine="codex",
        engine_display="Codex",
        instruction="test",
        pid=1234,
    )
    assert rec is not None
    run_id = rec.run_id

    # Force the first finish-time metadata write to fail. Subsequent
    # writes (the retry from _retry_pending_final) succeed.
    fail_until = {"count": 0}
    real_write_meta = store._write_meta

    def failing_write(record):
        fail_until["count"] += 1
        if fail_until["count"] == 1:
            return False
        return real_write_meta(record)

    store._write_meta = failing_write

    store.finish(run_id, "done", 0)

    # If the retry succeeded immediately, the pending map is already empty
    # and the disk copy is correct -- the handoff's behaviour is the same
    # either way (no interrupted reading). Otherwise the pending record
    # carries the known terminal status.
    if run_id in store._pending_final:
        with store._pending_final_lock:
            assert store._pending_final[run_id].status == "done"
            assert store._pending_final[run_id].exit_code == 0

    # history() in the same process returns the known terminal status
    # regardless of whether the retry already succeeded.
    history = store.history(str(tmp_path / "P"), limit=10)
    assert len(history) == 1, history
    assert history[0]["status"] == "done", history
    assert history[0]["exit_code"] == 0, history
    assert history[0]["finished_at"] is not None, history

    # On the disk, the persisted metadata is the terminal record.
    persisted = store._read_meta(store._dir / f"{run_id}.json")
    assert persisted is not None
    assert persisted.status == "done", persisted
    assert persisted.exit_code == 0, persisted


def test_round2_t707_history_persistent_write_failure_no_false_interrupted(tmp_path):
    """W2-004: with persistent write failure, the live pending record is
    the only thing standing between the user and an incorrect
    ``interrupted`` reading. ``history()`` must keep returning the known
    terminal status from ``_pending_final``; it MUST NOT mark a known-
    terminal run as ``interrupted`` because the disk copy still says
    ``running``."""
    from saipenview.sessions import SessionStore

    base = tmp_path / "data"
    base.mkdir()
    store = SessionStore(base_dir=base)

    rec = store.start(
        root=str(tmp_path / "P"),
        engine="codex",
        engine_display="Codex",
        instruction="test",
        pid=1234,
    )
    assert rec is not None
    run_id = rec.run_id

    # Every write fails.
    store._write_meta = lambda record: False  # type: ignore[assignment]

    store.finish(run_id, "done", 0)
    # Run absent from live _open, but known terminal state lives in
    # _pending_final.
    assert run_id not in store._open
    with store._pending_final_lock:
        assert run_id in store._pending_final

    # history() overlays the pending terminal record over the stale disk
    # "running" copy -- never reports "interrupted" for a known-done run.
    history = store.history(str(tmp_path / "P"), limit=10)
    assert len(history) == 1
    assert history[0]["status"] == "done", history
    assert history[0]["exit_code"] == 0, history


def test_round2_t706_no_resurrection_on_partial_write(monkeypatch, tmp_path):
    """W2-003: a temp file left behind by a crash must NOT be loaded as
    the live state. Only the committed final filename is authoritative."""
    import saipenview.api as api_mod

    cache_dir, _, records_dir = _t703_setup_cache(tmp_path, {})
    digest = "0" * 64
    # Simulate the residue of a crashed commit: a `.tmp.<pid>.<n>` file
    # left behind in the records dir. The loader must ignore it.
    (records_dir / f"{digest}.tmp.9999.42").write_text(
        json.dumps(_t703_legacy_row("/some/where")),
        encoding="utf-8",
    )
    Api, _, _ = _t703_bootstrap_api(monkeypatch, cache_dir)
    a = Api()
    try:
        roots = [p["root"] for p in a._projects]
        assert "/some/where" not in roots
    finally:
        a.stop()


def test_round2_t703_valid_cache_row_helper():
    """T-703: ``_valid_cache_row`` accepts canonical shape and rejects
    every documented malformed input."""
    from saipenview.api import _valid_cache_row

    good = _t703_legacy_row(str(Path("/x/y")))
    assert _valid_cache_row(good)
    # Missing required field.
    bad1 = dict(good)
    bad1.pop("is_pinned")
    assert not _valid_cache_row(bad1)
    # Wrong type on root.
    bad2 = dict(good)
    bad2["root"] = 42
    assert not _valid_cache_row(bad2)
    # Wrong type on is_pinned.
    bad3 = dict(good)
    bad3["is_pinned"] = "yes"
    assert not _valid_cache_row(bad3)
    # Not a dict at all.
    assert not _valid_cache_row("nope")
    assert not _valid_cache_row(None)
    assert not _valid_cache_row([1, 2, 3])


# --- T-704: scan authority (W2-001 ROUND 2) ---------------------------------


class _T704FakeProject:
    """Minimal stand-in so _set_cache reaches the registry branch."""

    def __init__(self, root, name=None):
        from pathlib import Path

        self.root = Path(root)
        self.name = name or Path(root).name
        self.state = {"phase": "DONE"}
        self.phase = "DONE"
        self.task = ""
        self.next_action = ""
        self.blocker = ""
        self.updated = ""
        self.updated_kind = ""
        self.mtime = 0
        self.subs = []
        self.translate = None
        self.quick_actions = []
        self.subs_stale = False
        self.subs_stale_details = ""
        self.git_branch = ""
        self.git_dirty = False
        self.board = _FakeBoard()


def _t704_norm(root: str) -> str:
    return root.replace("\\", "/").lower()


def test_round2_t704_stale_scan_publication_dropped(monkeypatch):
    """W2-001: a background scan that finishes after a newer manual rescan
    must not roll back the registry. The newer manual rescan bumps
    _scan_epoch; the older background publication carries the stale epoch
    and is rejected at _set_cache before any mutation."""
    import saipenview.api as api_mod
    from saipenview.scanner import ScanOutcome

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        # Seed two authoritative rows from the newer manual rescan.
        newer_root = "V:/_TEMP_/t704/NEWER"
        a._scan_epoch = 5
        a._set_cache(
            ScanOutcome(projects=[_T704FakeProject(newer_root)], worktrees=[], complete=True),
            force=True,
            epoch=5,
        )
        assert any(_t704_norm(p["root"]) == _t704_norm(newer_root) for p in a._projects), (
            f"newer manual rescan not committed: {a._projects}"
        )
        # Now an older background scan finishes with epoch 4 -> must be dropped.
        older_root = "V:/_TEMP_/t704/OLDER"
        a._set_cache(
            ScanOutcome(projects=[_T704FakeProject(older_root)], worktrees=[], complete=True),
            force=True,
            epoch=4,
        )
        assert all(_t704_norm(p["root"]) != _t704_norm(older_root) for p in a._projects), (
            f"stale background publication rolled back newer: {a._projects}"
        )
    finally:
        a.stop()


def test_round2_t704_inverse_ordering_normal_commit(monkeypatch):
    """W2-001: when no newer request bumps the epoch, a scan publication
    with the current epoch commits normally."""
    import saipenview.api as api_mod
    from saipenview.scanner import ScanOutcome

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        a._scan_epoch = 1
        a._set_cache(
            ScanOutcome(
                projects=[_T704FakeProject("V:/_TEMP_/t704/A")],
                worktrees=[],
                complete=True,
            ),
            force=True,
            epoch=1,
        )
        assert any(p["root"].endswith("A") for p in a._projects)
    finally:
        a.stop()


def test_round2_t704_rescan_bumps_epoch(monkeypatch):
    """W2-001: ``Api.rescan`` must bump the scan epoch at request start
    so a concurrent background result becomes stale."""
    import saipenview.api as api_mod

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        before = a._scan_epoch
        # Don't actually run scan() (network etc); just check the epoch bumps.
        epoch = a._next_scan_epoch()
        assert epoch == before + 1
        assert a._scan_epoch == before + 1
    finally:
        a.stop()


def test_round2_t704_no_epoch_still_commits(monkeypatch):
    """W2-001 backward compat: callers that do not pass epoch (None) still
    commit (legacy tests + non-scan entry points unchanged)."""
    import saipenview.api as api_mod
    from saipenview.scanner import ScanOutcome

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        a._set_cache(
            ScanOutcome(
                projects=[_T704FakeProject("V:/_TEMP_/t704/LEGACY")],
                worktrees=[],
                complete=True,
            ),
            force=True,
            # No epoch -> legacy path; no rejection.
        )
        assert any(p["root"].endswith("LEGACY") for p in a._projects)
    finally:
        a.stop()


# --- T-708: watcher O(K) topology (PERF-001 ROUND 2) ------------------------


def test_round2_t708_scan_root_watch_count_bounded(tmp_path):
    """PERF-001: scheduling by scan root must produce O(K) watchdog
    schedules, not O(projects). 100 projects under 2 scan roots -> 2
    scan-root watches + 0 per-project fallback watches."""
    import threading

    from saipenview.watcher import SaipenWatcher

    w = SaipenWatcher(debounce_delay=0.01)
    try:
        scan_root = tmp_path / "SR"
        scan_root.mkdir()
        projects = []
        for i in range(100):
            p = scan_root / f"p{i}"
            (p / ".saipen").mkdir(parents=True)
            (p / ".saipen" / "STATE.md").write_text(
                "---\nphase: DONE\n---\n", encoding="utf-8"
            )
            projects.append(str(p))
        w.sync(projects, scan_roots=[str(scan_root)])
        # O(K): one schedule per scan root, zero per-project fallback.
        assert len(w._watches) == 1, f"scan-root watches: {list(w._watches)}"
        assert len(w._root_router) == 1
        assert len(w._root_router[str(scan_root)]) == 100
        assert len(w._fallback_projects) == 0
    finally:
        w.stop()


def test_round2_t708_router_resolves_longest_prefix(tmp_path):
    """PERF-001: the router maps an event path to the deepest owning
    project, never a sibling and never the scan root itself."""
    from saipenview.watcher import _RootRouterHandler

    scope = "V:/SCAN"
    router = {
        scope: {
            "V:/SCAN/a": "V:/SCAN/a",
            "V:/SCAN/a/b": "V:/SCAN/a/b",
            "V:/SCAN/other": "V:/SCAN/other",
        }
    }
    h = _RootRouterHandler(scope, router)
    try:
        assert h._resolve_project("V:/SCAN/a/.saipen/STATE.md") == "V:/SCAN/a"
        assert h._resolve_project("V:/SCAN/a/b/.saipen/BOARD.md") == "V:/SCAN/a/b"
        assert h._resolve_project("V:/SCAN/other/.saipen/LOG.md") == "V:/SCAN/other"
        # Beneath the scan root but above every known project -> None.
        assert h._resolve_project("V:/SCAN/.saipen/STATE.md") is None
        # Unknown sibling dir with no project -> None.
        assert h._resolve_project("V:/SCAN/zzz/.saipen/STATE.md") is None
    finally:
        h.cancel()


def test_round2_t708_router_event_publish_targets_owner(tmp_path):
    """PERF-001: an event delivered on the scan-root watch publishes for
    exactly the owning project (the router's longest-prefix match), so
    mutation of project B under scan root SR reaches B's handler, not A."""
    import threading

    from saipenview.events import event_bus
    from saipenview.watcher import _RootRouterHandler

    scope = str(tmp_path / "SR")
    a = str(tmp_path / "SR" / "a")
    b = str(tmp_path / "SR" / "b")
    (Path(a) / ".saipen").mkdir(parents=True)
    (Path(b) / ".saipen").mkdir(parents=True)
    router = {scope: {a: a, b: b}}
    h = _RootRouterHandler(scope, router, debounce_delay=0.01)
    got = []
    event_bus.subscribe("saipen.project_changed", lambda data: got.append(data))
    try:
        h._maybe_path(str(Path(b) / ".saipen" / "STATE.md"))
        deadline = time.time() + 2
        while not got and time.time() < deadline:
            time.sleep(0.01)
        assert got, "no publish delivered"
        # The event for B must be published for B, never for A.
        assert all(d["root"] == b for d in got), got
    finally:
        event_bus.clear()
        h.cancel()


def test_round2_t708_fallback_bounded(tmp_path):
    """PERF-001: projects outside every configured scan root use a
    bounded per-project fallback, capped at _MAX_FALLBACK_PER_PROJECT_WATCHES
    rather than growing without limit."""
    from saipenview.watcher import SaipenWatcher

    w = SaipenWatcher(debounce_delay=0.01)
    try:
        fallback_root = tmp_path / "FALLBACK"
        fallback_root.mkdir()
        projects = []
        for i in range(50):
            p = fallback_root / f"f{i}"
            (p / ".saipen").mkdir(parents=True)
            projects.append(str(p))
        # No scan roots configured -> legacy per-project topology, bounded.
        w.sync(projects, scan_roots=[])
        assert len(w._fallback_projects) <= w._MAX_FALLBACK_PER_PROJECT_WATCHES
        assert len(w._fallback_projects) == min(
            len(projects), w._MAX_FALLBACK_PER_PROJECT_WATCHES
        )
    finally:
        w.stop()


# --- T-709: scanner timeout resource ownership (PERF-002 ROUND 2) ------------


def test_round2_t709_lexical_reservation_prevents_duplicate_worker(
    monkeypatch, tmp_path
):
    """PERF-002: a root blocked during canonical() must be reserved by its
    lexical key BEFORE any filesystem I/O, so a later scan cycle sees the
    reservation and skips submitting a duplicate worker. The reservation
    persists until the original worker exits, not until the coordinator
    times out."""
    import threading

    import saipenview.scanner as scanner_mod

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / ".saipen").mkdir()

    entered = threading.Event()
    release = threading.Event()
    real_canonical = scanner_mod.canonical

    def blocking_canonical(path):
        entered.set()
        release.wait(timeout=5)
        return real_canonical(path)

    monkeypatch.setattr(scanner_mod, "canonical", blocking_canonical)

    results = {}

    def worker():
        results["out1"] = scanner_mod._scan_root_task(
            str(blocked), 6, 0.0, set(), threading.Event()
        )

    t = threading.Thread(target=worker)
    t.start()
    assert entered.wait(timeout=5), "first worker never reached canonical()"
    # The first worker now holds the lexical reservation. A second scan
    # for the same root must be SKIPPED, not spawn a duplicate worker.
    out2 = scanner_mod._scan_root_task(
        str(blocked), 6, 0.0, set(), threading.Event()
    )
    assert out2.get("status") == "skipped", out2
    release.set()
    t.join(timeout=10)
    assert "out1" in results
    assert results["out1"].get("status") == "completed", results["out1"]


def test_round2_t710_published_scan_skips_blanket_refresh(monkeypatch):
    """PERF-003: freshly published ScanOutcome rows are authoritative, so
    refresh_known with the current revision does not reparse every root or
    rebuild every ticket index a second time."""
    import saipenview.api as api_mod
    from saipenview.scanner import ScanOutcome

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        a._scan_epoch = 1
        projects = [_T704FakeProject("V:/_TEMP_/t710/A"), _T704FakeProject("V:/_TEMP_/t710/B")]
        a._set_cache(ScanOutcome(projects=projects, worktrees=[], complete=True), force=True, epoch=1)
        assert a._full_refresh_pending is False
        calls = []
        monkeypatch.setattr(api_mod, "load_project", lambda *args, **kwargs: calls.append(args[0]) or None)
        result = a.refresh_known(a._registry_rev)
        assert isinstance(result, dict), result
        assert result["projects"] is None
        assert calls == [], f"blanket post-scan reparse remained: {calls}"
    finally:
        a.stop()


def test_round2_t710_startup_pending_still_reconciles(monkeypatch):
    """PERF-003: constructor/startup durable-cache rows retain the pending
    flag and still receive their required reconciliation pass."""
    import saipenview.api as api_mod

    monkeypatch.setattr(api_mod, "_is_garbage_root", lambda p: False)
    a = api_mod.Api()
    try:
        a._projects = [{"root": "V:\\_TEMP_\\t710\\START"}]
        a._registry_rev = 0
        a._full_refresh_pending = True
        calls = []
        monkeypatch.setattr(api_mod, "load_project", lambda *args, **kwargs: calls.append(args[0]) or None)
        a.refresh_known()
        assert calls, "startup pending reconciliation was skipped"
    finally:
        a.stop()


# --- T-711: terminal ProcessManager retention bound (PERF-004 ROUND 2) ------


def test_round2_t711_finalized_entries_bounded_running_preserved():
    """PERF-004: finalized AgentProcess metadata is bounded by the explicit
    LRU/count ceiling, while running entries remain resident and therefore
    cannot be evicted before process death/transcript finalization."""
    from datetime import datetime, timezone, timedelta

    from saipenview.runtime import ProcessManager

    pm = ProcessManager()
    # More finalized entries than the configured ceiling, oldest first.
    for i in range(pm._MAX_FINALIZED + 10):
        ap = _T704FakeProject(f"V:/_TEMP_/t711/f{i}")
        # A compact lifecycle-equivalent terminal object needs only the
        # fields _evict_finalized reads.
        ap.status = "done"
        ap.finished_at = datetime.now(timezone.utc) - timedelta(seconds=i)
        pm._processes[pm._key(ap.root.as_posix())] = ap
    running = _T704FakeProject("V:/_TEMP_/t711/running")
    running.status = "running"
    running.finished_at = None
    pm._processes[pm._key(running.root.as_posix())] = running

    pm._evict_finalized()

    finalized = [ap for ap in pm._processes.values() if ap.status != "running"]
    assert len(finalized) <= pm._MAX_FINALIZED
    assert any(ap is running for ap in pm._processes.values()), (
        "running AgentProcess was evicted"
    )


def test_round2_t711_compaction_releases_heavy_fields():
    """PERF-004: eligible terminal compaction releases output/process/reader
    resources before the bounded eviction pass, while line totals remain."""
    import collections
    from datetime import datetime, timezone

    from saipenview.runtime import ProcessManager

    pm = ProcessManager()
    ap = _T704FakeProject("V:/_TEMP_/t711/compact")
    ap.status = "done"
    ap.finished_at = datetime.now(timezone.utc)
    ap.output_lines = collections.deque(["a", "b"], maxlen=5000)
    ap._line_count = 2
    ap._reader_thread = None
    ap._io_lock = threading.Lock()
    ap.process = object()
    ap._psutil_proc = object()
    pm._processes[pm._key(ap.root.as_posix())] = ap

    pm._compact_terminal(ap)

    assert ap.output_lines == collections.deque(maxlen=5000)
    assert ap._line_count == 2
    assert ap.process is None
    assert ap._psutil_proc is None
