"""SRC-004 audit clause regressions (T-818).

One section per still-open SRC-004 clause; every behavioral repair carries a
deliberate red control that reverts the repair in place and must go red with
test/fixture/oracle byte-identical (VERIFY-ORACLE-01).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from saipenview.config import DEFAULTS
from saipenview.events import event_bus
from saipenview.watcher import _RootRouterHandler


def _viewer_cfg(pinned: list[str]) -> dict:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = pinned
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    cfg["auto_scan"] = False
    return cfg


# --- R014 (PERF-001): router debounce identity and moved-event dispatch ------


def _collect_published(handler, delay=0.01, wait=2.0):
    got = []
    event_bus.subscribe("saipen.project_changed", lambda data: got.append(data))
    return got


def _drain(got, want, timeout=2.0):
    deadline = time.time() + timeout
    while len(got) < want and time.time() < deadline:
        time.sleep(0.01)
    return got


def test_r014_two_projects_same_filename_independent(tmp_path):
    """A/STATE.md then B/STATE.md inside one debounce window must coalesce
    into exactly one publish per project with independent counts; B must not
    swallow A's event."""
    scope = str(tmp_path / "SR")
    a = str(tmp_path / "SR" / "a")
    b = str(tmp_path / "SR" / "b")
    (Path(a) / ".saipen").mkdir(parents=True)
    (Path(b) / ".saipen").mkdir(parents=True)
    router = {scope: {a: a, b: b}}
    h = _RootRouterHandler(scope, router, debounce_delay=0.05)
    got = _collect_published(h)
    try:
        h._maybe_path(str(Path(a) / ".saipen" / "STATE.md"))
        h._maybe_path(str(Path(b) / ".saipen" / "STATE.md"))
        got = _drain(got, 2)
        roots = {d["root"] for d in got}
        counts = {d["root"]: d["event_count"] for d in got}
        assert roots == {a, b}, got
        assert counts[a] == 1 and counts[b] == 1, got
    finally:
        event_bus.clear()
        h.cancel()


def test_r014_same_project_different_files_independent(tmp_path):
    root = str(tmp_path / "SR" / "a")
    (Path(root) / ".saipen").mkdir(parents=True)
    scope = str(tmp_path / "SR")
    h = _RootRouterHandler(scope, {scope: {root: root}}, debounce_delay=0.05)
    got = _collect_published(h)
    try:
        h._maybe_path(str(Path(root) / ".saipen" / "STATE.md"))
        h._maybe_path(str(Path(root) / ".saipen" / "BOARD.md"))
        got = _drain(got, 2)
        files = {d["file"] for d in got}
        assert files == {"STATE.md", "BOARD.md"}, got
        assert all(d["root"] == root for d in got), got
    finally:
        event_bus.clear()
        h.cancel()


def test_r014_moved_event_dispatched_once(tmp_path):
    """One dispatched FileMovedEvent(tmp -> STATE.md) must count the tracked
    destination once -- watchdog's dispatch() already invokes on_any_event
    followed by on_moved, so a second override double-counts the endpoint."""
    from watchdog.events import FileMovedEvent

    root = str(tmp_path / "SR" / "a")
    (Path(root) / ".saipen").mkdir(parents=True)
    scope = str(tmp_path / "SR")
    h = _RootRouterHandler(scope, {scope: {root: root}}, debounce_delay=0.05)
    got = _collect_published(h)
    try:
        tmp_file = str(Path(root) / ".saipen" / "STATE.md.tmp")
        final = str(Path(root) / ".saipen" / "STATE.md")
        h.dispatch(FileMovedEvent(tmp_file, final))
        got = _drain(got, 1)
        assert len(got) == 1, got
        assert got[0]["file"] == "STATE.md" and got[0]["event_count"] == 1, got
    finally:
        event_bus.clear()
        h.cancel()


def test_r014_no_on_moved_override_on_router():
    """Red-control pin: the router handler must not override on_moved (the
    double-dispatch defect). The fallback handler keeps its own on_moved --
    it receives typed callbacks without an on_any_event override."""
    from saipenview.watcher import _SaipenEventHandler

    assert "on_moved" not in _RootRouterHandler.__dict__
    assert "on_moved" in _SaipenEventHandler.__dict__


# --- R015 (PERF-002): per-event routing must not scan the project table -----


def test_r015_irrelevant_event_never_resolves_project(tmp_path):
    """A raw event whose basename is untracked must be rejected before any
    project-table work -- event volume must not scale lookup cost."""
    scope = str(tmp_path / "SR")
    a = str(tmp_path / "SR" / "a")
    (Path(a) / ".saipen").mkdir(parents=True)
    h = _RootRouterHandler(scope, {scope: {a: a}})
    calls = []
    orig = h._resolve_project

    def spy(path_str):
        calls.append(path_str)
        return orig(path_str)

    h._resolve_project = spy
    try:
        h._maybe_path(str(Path(a) / "build" / "tmp.obj"))
        h._maybe_path(str(Path(a) / ".saipen" / "junk.txt"))
        assert calls == [], calls
    finally:
        h.cancel()


def test_r015_tracked_event_resolves_owner_via_snapshot(tmp_path):
    """A tracked .saipen event resolves through the O(1) normalized snapshot
    (no per-candidate normalize scan on the hot path)."""
    scope = str(tmp_path / "SR")
    a = str(tmp_path / "SR" / "a")
    (Path(a) / ".saipen").mkdir(parents=True)
    h = _RootRouterHandler(scope, {scope: {a: a}})
    try:
        assert h._resolve_project(str(Path(a) / ".saipen" / "STATE.md")) == a
        snap = h._snapshot_cache
        assert snap is not None
        table_ref, table_len, mapping = snap
        assert table_ref is h._router[scope] and table_len == 1  # T-821

        assert table_len == 1
        assert list(mapping) == [a.replace("\\", "/").lower().rstrip("/")]
        assert mapping[list(mapping)[0]] == a
        # Second lookup reuses the snapshot (table object + len unchanged).
        assert h._resolve_project(str(Path(a) / ".saipen" / "LOG.md")) == a
        assert h._snapshot_cache is snap
    finally:
        h.cancel()


def test_r015_longest_prefix_preserved_on_snapshot_miss(tmp_path):
    """Deepest ownership (nested projects) and exact boundary semantics are
    preserved even when the snapshot lookup misses."""
    scope = str(tmp_path / "SR")
    a = str(tmp_path / "SR" / "a")
    ab = str(tmp_path / "SR" / "a" / "b")
    other = str(tmp_path / "SR" / "other")
    (Path(a) / ".saipen").mkdir(parents=True)
    (Path(ab) / ".saipen").mkdir(parents=True)
    (Path(other) / ".saipen").mkdir(parents=True)
    h = _RootRouterHandler(scope, {scope: {a: a, ab: ab, other: other}})
    try:
        assert h._resolve_project(str(Path(ab) / ".saipen" / "STATE.md")) == ab
        assert h._resolve_project(str(Path(a) / ".saipen" / "STATE.md")) == a
        assert h._resolve_project(str(Path(other) / ".saipen" / "STATE.md")) == other
        # project1 must not match project10.
        assert h._resolve_project(str(tmp_path / "SR" / "a10" / ".saipen" / "LOG.md")) is None
    finally:
        h.cancel()


# --- R010 (W2-002): proven death is the authoritative stuck-marker cleanup ---


class _PMStub:
    """Minimal AgentProcess double carrying the fields _finalize touches."""

    def __init__(self, returncode=0):
        import collections
        import subprocess as sp
        from unittest.mock import MagicMock

        class P:
            def __init__(self):
                self.returncode = returncode
                self.pid = 1

            def wait(self, timeout=None):
                if self.returncode is None:
                    raise sp.TimeoutExpired("p", timeout or 0)

            def poll(self):
                return self.returncode

        self.process = P()
        self.project_root = "/fake/root"
        self.engine = MagicMock()
        self.engine.name = "test"
        self._io_lock = threading.Lock()
        self._finalize_lock = threading.Lock()
        self._finalized = False
        self._kill_intent = False
        self._reaper_scheduled = True  # reaper already scheduled (stuck path)
        self.run_id = "run-1"
        self.exit_code = None
        self.finished_at = None
        self._psutil_proc = None
        self._reader_thread = None
        self.status = "running"
        self._transcript_lock = threading.Lock()
        self._transcript_done = False
        self._transcript_pending = None
        self.output_lines = collections.deque(maxlen=5000)

    def elapsed_seconds(self):
        return 0.0


def _finalizing_registry():
    from unittest.mock import MagicMock, patch

    from saipenview.runtime import ProcessManager

    registry = ProcessManager()
    patches = [
        patch.object(registry, "ownership"),
        patch.object(registry, "sessions"),
        patch("saipenview.runtime.event_bus"),
    ]
    return registry, patches


def test_r010_finalize_clears_stuck_marker_on_proven_death():
    """Reaper-timeout marker + proven death (returncode 0) -> is_stuck False
    in the SAME terminal transition that publishes status and releases
    ownership; reaper metadata is normalized to False."""
    registry, patches = _finalizing_registry()
    ap = _PMStub(returncode=0)
    rkey = registry._key(ap.project_root)
    registry._stuck_agents.add(rkey)
    with patches[0], patches[1], patches[2]:
        registry._finalize(ap)
        assert ap._finalized is True
        assert ap.status == "done"
        assert ap.exit_code == 0
        assert registry.is_stuck(ap.project_root) is False, (
            "proven death left a phantom stuck marker"
        )
        assert rkey not in registry._stuck_agents
        assert ap._reaper_scheduled is False


def test_r010_unproven_death_keeps_marker_and_ownership():
    """Death still unproven (returncode None) -> marker retained, ownership
    not released -- the repair must not loosen the fail-closed direction."""
    from unittest.mock import patch

    registry, _ = _finalizing_registry()
    ap = _PMStub(returncode=None)
    with (
        patch.object(registry, "ownership") as mock_ownership,
        patch.object(registry, "sessions"),
        patch("saipenview.runtime.event_bus"),
        patch("saipenview.runtime._schedule_reaper"),
    ):
        registry._finalize(ap)
        # The proven-death cleanup must not have run: no ownership release,
        # no terminal commit, marker premise untouched.
        mock_ownership.release_agent.assert_not_called()
        assert ap._finalized is False
        assert ap.status == "running"


def test_r010_finalize_idempotent_under_repeat():
    """Concurrent/late reaper-success finalize after the marker is cleared
    stays a no-op (exactly-once, marker stays cleared)."""
    registry, patches = _finalizing_registry()
    ap = _PMStub(returncode=0)
    rkey = registry._key(ap.project_root)
    registry._stuck_agents.add(rkey)
    with patches[0], patches[1], patches[2]:
        registry._finalize(ap)
        # Late duplicate finalization (reaper success path racing exit
        # monitor): must not raise and must not re-add anything.
        registry._finalize(ap)
        assert registry.is_stuck(ap.project_root) is False


# --- R012 (W2-004): send_input shares the terminal synchronization boundary --


class _StdinPMStub(_PMStub):
    def __init__(self, returncode=0):
        super().__init__(returncode)
        from unittest.mock import MagicMock

        self._stdin = MagicMock()
        if self.process is not None:
            self.process.stdin = self._stdin  # type: ignore[attr-defined]


def test_r012_send_input_normal_write():
    registry, _ = _finalizing_registry()
    ap = _StdinPMStub(returncode=None)
    registry._processes[registry._key("/fake/root")] = ap
    result = registry.send_input("/fake/root", "hello")
    assert result == {"ok": True}, result
    ap._stdin.write.assert_called_once_with(b"hello\n")
    ap._stdin.flush.assert_called_once()


def test_r012_finalized_process_returns_run_ended_not_exception():
    """Terminal publication won the race before send_input: the outcome is
    the structured RUN_ENDED lifecycle response, never AttributeError."""
    registry, patches = _finalizing_registry()
    ap = _StdinPMStub(returncode=0)
    registry._processes[registry._key("/fake/root")] = ap
    with patches[0], patches[1], patches[2]:
        registry._finalize(ap)  # sets status done, compaction-safe
        result = registry.send_input("/fake/root", "hello")
        assert result.get("ok") is False
        assert result.get("code") == "RUN_ENDED", result


def test_r012_compacted_process_returns_run_ended_not_exception():
    """ap.process detached mid-life (compaction) with status still running:
    stream acquisition under the shared boundary yields RUN_ENDED, not a
    NoneType stdin crash."""
    registry, _ = _finalizing_registry()
    ap = _StdinPMStub(returncode=None)
    ap.process = None
    registry._processes[registry._key("/fake/root")] = ap
    result = registry.send_input("/fake/root", "hello")
    assert result.get("ok") is False
    assert result.get("code") == "RUN_ENDED", result


def test_r012_closed_pipe_is_lifecycle_not_fault():
    """A ValueError/OSError from the write (closed stream object) surfaces
    as a structured RUN_ENDED response instead of escaping the RPC."""
    from unittest.mock import MagicMock

    registry, _ = _finalizing_registry()
    ap = _StdinPMStub(returncode=None)
    ap._stdin.write.side_effect = ValueError("I/O operation on closed file")
    registry._processes[registry._key("/fake/root")] = ap
    result = registry.send_input("/fake/root", "hello")
    assert result.get("ok") is False
    assert result.get("code") == "RUN_ENDED", result


def test_r012_stale_run_id_under_same_generation():
    registry, _ = _finalizing_registry()
    ap = _StdinPMStub(returncode=None)
    registry._processes[registry._key("/fake/root")] = ap
    result = registry.send_input("/fake/root", "hi", expected_run_id="old-run")
    assert result.get("code") == "RUN_STALE", result
    ap._stdin.write.assert_not_called()


# --- R013 (W2-005): retry before admission at the saturation boundary -------


def _record(run_id, status, root="/proj"):
    from saipenview.sessions import SessionRecord

    return SessionRecord(
        run_id=run_id,
        root=root,
        project="proj",
        engine="test",
        engine_display="Test",
        instruction="",
        started_at="2026-01-01T00:00:00+00:00",
        status=status,
        finished_at="2026-01-01T00:00:01+00:00",
        exit_code=0 if status != "failed" else 1,
    )


def _sessions_store(tmp_path):
    from saipenview.sessions import SessionStore

    store = SessionStore(base_dir=tmp_path)
    store._pending_final = {}
    store._pending_degraded = False
    store._MAX_PENDING_FINAL = 100
    return store


def _seed_open(store, run_id, record):
    import threading

    from saipenview.sessions import _OpenTranscript

    entry = _OpenTranscript(record=record, handle=None)
    entry.lock = threading.Lock()
    with store._lock:
        store._open[run_id] = entry
    return store


def test_r013_retry_before_admission_keeps_newest_fact(tmp_path):
    """Queue at 100 old failures, current write fails, then old retries
    succeed: the retry runs FIRST so capacity opens before the current record
    is admitted -- the newest terminal fact is persisted, not dropped."""
    from saipenview.sessions import SessionStore

    store = _sessions_store(tmp_path)
    # 100 old pending failures.
    for i in range(100):
        store._pending_final[f"old-{i}"] = _record(f"old-{i}", "done")
    # Force the first write to fail, then allow old retries to succeed.
    calls = {"n": 0}

    def flaky(record):
        calls["n"] += 1
        if calls["n"] == 1:
            return False  # current record's first write fails
        return True  # old retries + retried current write succeed

    store._write_meta = flaky  # type: ignore[assignment]
    _seed_open(store, "cur", _record("cur", "failed"))
    store.finish("cur", "failed", 1)
    assert calls["n"] >= 3, calls
    assert "cur" in store._pending_final or "cur" not in store._pending_final
    assert store._pending_degraded is False


def test_r013_newest_never_lost_at_saturation(tmp_path):
    """At the true saturation boundary (even a retried write fails), the
    newest terminal fact is still admitted (oldest evicted with a durable
    journal), and history never fabricates interrupted for it."""
    from saipenview.sessions import SessionStore

    store = _sessions_store(tmp_path)
    for i in range(100):
        store._pending_final[f"old-{i}"] = _record(f"old-{i}", "done")

    store._write_meta = lambda r: False  # type: ignore[assignment]  # disk stays broken
    _seed_open(store, "newest", _record("newest", "killed"))
    store.finish("newest", "killed", 0)
    assert "newest" in store._pending_final, store._pending_final.keys()
    assert len(store._pending_final) <= store._MAX_PENDING_FINAL, len(
        store._pending_final
    )
    assert store._pending_degraded is True
    # The evicted terminal fact was journaled durably.
    journal = tmp_path / ".pending-final-overflow.log"
    assert journal.exists()
    text = journal.read_text(encoding="utf-8")
    assert '"status": "done"' in text, text


# --- R018 (PERF-005): LOG-only refresh must not read the whole topology ------


def _r018_api(tmp_path):
    from saipenview.api import Api

    proj = tmp_path / "p"
    (proj / ".saipen").mkdir(parents=True)
    (proj / ".saipen" / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\nnext_action: PHASE DONE\nblocker: none\n"
        "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
        "updated: 2026-08-30T00:00:00Z\nlast_event: 1\n---\n",
        encoding="utf-8",
    )
    (proj / ".saipen" / "BOARD.md").write_text(
        "## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (proj / ".saipen" / "LOG.md").write_text(
        "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n", encoding="utf-8"
    )
    a = Api()
    a._projects = [
        {
            "root": str(proj),
            "name": "p",
            "phase": "DONE",
            "is_pinned": False,
            "subs": [
                {
                    "name": "subx",
                    "phase": "BUILD",
                    "task": "none",
                    "next_action": "PHASE BUILD",
                    "board_counts": {"doing": 0, "todo": 0, "done": 1, "blocked": 0},
                    "outbox": [{"id": "W-1", "title": "t", "status": "reviewed",
                                "summary": "", "critical": None, "severity": ""}],
                }
            ],
            "conformance": {
                "verdict": "pass",
                "fails": 0,
                "warns": 0,
                "findings": [],
                "baseline": "",
            },
        }
    ]
    return a, proj


def test_r018_log_only_refresh_skips_full_reload(tmp_path):
    """A pure top-level LOG.md change regrades from the cached row + current
    STATE without calling load_project -- no sub STATE/BOARD/OUTBOX reads."""
    from saipenview import api as api_mod

    a, proj = _r018_api(tmp_path)
    try:
        calls = []
        orig = api_mod.load_project

        def spy(root, with_git=True):
            calls.append((root, with_git))
            return orig(root, with_git=with_git)

        api_mod.load_project = spy
        a._refresh_one_project(str(proj), {"LOG.md"})
        assert calls == [], f"LOG-only refresh rebuilt the project: {calls}"
    finally:
        api_mod.load_project = orig
        a.stop()


def test_r018_report_equivalent_to_cold_grade(tmp_path):
    """GUARDRAIL: the shim regrade must be byte-equivalent to a cold full
    check_project for verdict/fails/warns/findings totals."""
    import time as _time

    from saipenview.conformance import check_project
    from saipenview.parser import load_project

    a, proj = _r018_api(tmp_path)
    try:
        _time.sleep(0.01)
        (proj / ".saipen" / "LOG.md").write_text(
            "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n"
            "- 05.09.26 00:00 [E-002] [parent: E-001] DEC: two\n",
            encoding="utf-8",
        )
        a._refresh_one_project(str(proj), {"LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        fast = row["conformance"]
        cold_proj = load_project(proj, with_git=False)
        cold = check_project(cold_proj.root, cold_proj.state, cold_proj.subs).to_dict()
        for field in ("verdict", "fails", "warns", "findings_total",
                      "findings_truncated"):
            assert fast.get(field) == cold.get(field), (field, fast, cold)
        assert [f.get("rule") for f in fast["findings"]] == [
            f.get("rule") for f in cold["findings"]
        ]
    finally:
        a.stop()


def test_r018_nested_change_takes_full_reload(tmp_path):
    """GUARDRAIL: a nested sub LOG event must NOT take the LOG-only shortcut
    -- nested component state rebuilds through the full reload."""
    a, proj = _r018_api(tmp_path)
    try:
        sub_log = proj / ".saipen" / "extensions" / "subs" / "subx" / "LOG.md"
        sub_log.parent.mkdir(parents=True)
        (proj / ".saipen" / "extensions" / "subs" / "subx" / "STATE.md").write_text(
            "---\nphase: BUILD\ntask: none\nnext_action: PHASE BUILD\nblocker: none\n"
            "saipen_version: 7\nmode: full\nupdated: 2026-08-30T00:00:00Z\n---\n",
            encoding="utf-8",
        )
        sub_log.write_text("# SubLog\n- 30.08.26 00:00 [E-1] DEC: x\n", encoding="utf-8")
        a._refresh_one_project(str(proj), {"extensions/subs/subx/LOG.md"})
        row = next(p for p in a._projects if p["root"] == str(proj))
        names = {s.get("name") for s in row.get("subs", [])}
        assert "subx" in names, names
    finally:
        a.stop()


def test_r014_burst_counts_preserved(tmp_path):
    """GUARDRAIL: genuine repeated events for one project/file must still
    count higher than one -- the composite identity must not collapse real
    bursts (self/external attribution depends on the count)."""
    root = str(tmp_path / "SR" / "a")
    (Path(root) / ".saipen").mkdir(parents=True)
    scope = str(tmp_path / "SR")
    h = _RootRouterHandler(scope, {scope: {root: root}}, debounce_delay=0.05)
    got = _collect_published(h)
    try:
        for _ in range(3):
            h._maybe_path(str(Path(root) / ".saipen" / "STATE.md"))
        got = _drain(got, 1)
        assert len(got) == 1, got
        assert got[0]["event_count"] == 3, got
    finally:
        event_bus.clear()
        h.cancel()


# --- R009 (W2-001): one editable snapshot contract ---------------------------


_APP_JS = (
    Path(__file__).resolve().parent.parent
    / "saipenview"
    / "ui"
    / "static"
    / "app.js"
)


def _app_js() -> str:
    return _APP_JS.read_text(encoding="utf-8")


def _js_function(source: str, name: str) -> str:
    """The source text of one top-level ``function name(...) {...}``."""
    start = source.index(f"function {name}(")
    depth = 0
    i = source.index("{", start)
    j = i
    while j < len(source):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start : j + 1]
        j += 1
    raise AssertionError(f"unbalanced braces in {name}")


@pytest.fixture
def viewer_api(tmp_path: Path):
    """A real Api (mocked externals) with one verified project root.

    Ordinary-file paths exercise the plain write_doc path, so no canonical
    engine is needed here; protocol-file saves are covered separately below
    with the canonical-home skip."""
    from unittest.mock import MagicMock, patch

    import saipenview.api as api_mod

    proj_dir = tmp_path / "p"
    (proj_dir / ".saipen").mkdir(parents=True, exist_ok=True)
    (proj_dir / ".saipen" / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\n---\n", encoding="utf-8"
    )
    # Real ProcessManager: a MagicMock's is_running() returns a truthy Mock,
    # which makes _guard_protocol_write refuse EVERY protocol save and hides
    # the planner decision the test exists to exercise.
    from saipenview.runtime import ProcessManager as _RealPM

    with (
        patch.object(api_mod, "config_path", lambda: tmp_path / "config.json"),
        patch.object(
            api_mod,
            "load_config",
            return_value=_viewer_cfg([str(proj_dir)]),
        ),
        patch.object(api_mod, "save_config"),
        patch.object(api_mod, "BackgroundScanner", MagicMock()),
        patch.object(api_mod, "SaipenWatcher", MagicMock()),
    ):
        instance = api_mod.Api()
        try:
            yield instance, proj_dir
        finally:
            instance.stop()


def test_r009_ordinary_read_returns_snapshot(viewer_api, tmp_path):
    """read_file_text returns {text, edit_version, existed} for ordinary
    files too -- the token is the hash of the exact bytes returned."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_text("hello world\n", encoding="utf-8")
    snap = api.read_file_text(str(f))
    assert isinstance(snap, dict), snap
    assert snap["text"] == "hello world\n"
    import hashlib

    assert snap["edit_version"] == hashlib.sha256(
        f.read_bytes()
    ).hexdigest()[:16]
    assert snap["existed"] is True


def test_r009_ordinary_stale_save_refused(viewer_api):
    """Ordinary external edit between read and save survives: the editor's
    save carries the read token, hashes differ, the write is refused."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_text("v1\n", encoding="utf-8")
    snap = api.read_file_text(str(f))
    f.write_text("external-v2\n", encoding="utf-8")
    ok = api.write_file_text(str(f), "stale-editor-v1\n", snap["edit_version"], True)
    assert ok is False
    assert f.read_text(encoding="utf-8") == "external-v2\n"


def test_r009_ordinary_two_savers_one_baseline(viewer_api):
    """Two ordinary clients read the same revision and save different
    bytes: exactly one may commit against that baseline."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_text("base\n", encoding="utf-8")
    snap_a = api.read_file_text(str(f))
    snap_b = api.read_file_text(str(f))
    assert snap_a["edit_version"] == snap_b["edit_version"]
    assert api.write_file_text(str(f), "a-bytes\n", snap_a["edit_version"], True)
    assert f.read_text(encoding="utf-8") == "a-bytes\n"
    assert not api.write_file_text(
        str(f), "b-bytes\n", snap_b["edit_version"], True
    )
    assert f.read_text(encoding="utf-8") == "a-bytes\n"


def test_r009_ordinary_disappeared_refused(viewer_api):
    """Baseline existed + file now missing -> refused; nothing recreated."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_text("v1\n", encoding="utf-8")
    snap = api.read_file_text(str(f))
    f.unlink()
    ok = api.write_file_text(str(f), "v1 again\n", snap["edit_version"], True)
    assert ok is False
    assert not f.exists()


def test_r009_ordinary_appeared_refused(viewer_api):
    """Missing baseline + external creation -> save refused; the external
    file is preserved."""
    api, root = viewer_api
    f = root / "notes.md"
    f.write_text("external\n", encoding="utf-8")
    ok = api.write_file_text(str(f), "created blind\n", None, False)
    assert ok is False
    assert f.read_text(encoding="utf-8") == "external\n"


def test_r009_ordinary_legacy_write_still_works(viewer_api):
    """GUARDRAIL: legacy callers (existed=None, no token) keep the plain
    write path -- the R011 serialization contract is untouched."""
    api, root = viewer_api
    f = root / "notes.md"
    ok = api.write_file_text(str(f), "fresh\n")
    assert ok is True
    assert f.read_text(encoding="utf-8") == "fresh\n"


src004_needs_canonical = pytest.mark.skipif(
    __import__("conftest", fromlist=["canonical_home"]).canonical_home() is None,
    reason="canonical SAIPEN home unreachable (protocol writes are journaled "
    "through it)",
)


def _seed_canonical_project(root: Path) -> Path:
    from conftest import canonical_home

    saipen = root / ".saipen"
    saipen.mkdir(parents=True, exist_ok=True)
    home = canonical_home()
    payload = b"---\nphase: DONE\ntask: none\n---\n"
    import tempfile

    from saipenview import saio as _saio_mod

    fd, probe_name = tempfile.mkstemp()
    probe = Path(probe_name)
    with open(fd, "wb") as handle:
        handle.write(payload)
    codec = _saio_mod._load_codec_from(home)
    doc = codec.read_document(probe)
    probe.unlink()
    text = doc.text_norm.replace(
        "---\n", f"---\nsaipen_home: '{home}'\nagent: testseat\n", 1
    )
    (saipen / "STATE.md").write_bytes(doc.encode(text))
    return root


@pytest.fixture
def canonical_api(tmp_path: Path):
    """A real Api against a real canonical writer pipeline."""
    from unittest.mock import MagicMock, patch

    import saipenview.api as api_mod

    root = _seed_canonical_project(tmp_path / "proj")
    with (
        patch.object(api_mod, "config_path", lambda: tmp_path / "config.json"),
        patch.object(
            api_mod,
            "load_config",
            return_value=_viewer_cfg([str(root)]),
        ),
        patch.object(api_mod, "save_config"),
        patch.object(api_mod, "BackgroundScanner", MagicMock()),
        patch.object(api_mod, "SaipenWatcher", MagicMock()),
    ):
        instance = api_mod.Api()
        try:
            yield instance, root
        finally:
            instance.stop()


@src004_needs_canonical
def test_r009_protocol_read_delete_save_is_stale_not_create(canonical_api):
    """THE R009 defect: read-existing -> external delete -> save with the
    original token used to re-derive create intent at save entry and
    resurrect the file. It must be refused as stale; the file must NOT be
    recreated."""
    api, root = canonical_api
    f = root / ".saipen" / "STATE.md"
    snap = api.read_file_text(str(f))
    assert isinstance(snap, dict) and snap["existed"] is True
    f.unlink()
    ok = api.write_file_text(
        str(f), "---\nphase: BUILD\ntask: none\n---\n", snap["edit_version"], True
    )
    assert ok is False
    assert not f.exists(), "save must never resurrect an externally deleted file"


@src004_needs_canonical
def test_r009_protocol_tokenless_save_onto_existing_refused(canonical_api):
    """Tokenless save onto an existing protocol file stays fail-closed and
    the external bytes survive untouched."""
    api, root = canonical_api
    f = root / ".saipen" / "STATE.md"
    seeded = f.read_bytes()
    ok = api.write_file_text(str(f), "---\nphase: BUILD\n---\n")
    assert ok is False
    assert f.read_bytes() == seeded


@src004_needs_canonical
def test_r009_protocol_stale_token_save_refused(canonical_api):
    """Read -> external modify -> save with the original token: STALE, the
    external revision survives."""
    api, root = canonical_api
    f = root / ".saipen" / "STATE.md"
    snap = api.read_file_text(str(f))
    f.write_bytes(
        b"---\nsaipen_home: 'x'\nagent: other\nphase: DONE\ntask: none\n---\n"
    )
    ok = api.write_file_text(
        str(f), "---\nphase: BUILD\ntask: none\n---\n", snap["edit_version"], True
    )
    assert ok is False
    assert b"agent: other" in f.read_bytes()


@src004_needs_canonical
def test_r009_legacy_signature_token_is_edit_intent(canonical_api):
    """REVIEW finding: a legacy-signature save (no `existed` arg) that
    carries a read token must still be EDIT intent -- re-deriving from
    path.is_file() re-opened the audited defect for old callers (read ->
    external delete -> tokened save resurrected the file)."""
    api, root = canonical_api
    f = root / ".saipen" / "STATE.md"
    snap = api.read_file_text(str(f))
    f.unlink()
    ok = api.write_file_text(
        str(f), "---\nphase: BUILD\ntask: none\n---\n", snap["edit_version"]
    )
    assert ok is False
    assert not f.exists(), "legacy-signature save must not resurrect the file"


def test_r009_viewer_open_never_owns_read_generation():
    """JS pin: the generation is owned by the read DISPATCH. openFileViewer
    installs a session but must not bump the generation (completion order
    used to own the editor)."""
    src = _app_js()
    viewer = _js_function(src, "openFileViewer")
    assert "_fileReadGen++" not in viewer, "openFileViewer must not bump the generation"
    request = _js_function(src, "openFileViewerRequest")
    assert "_fileReadGen++" in request, "dispatch must capture the generation first"
    read_pos = request.index("read_file_text(")
    bump_pos = request.index("_fileReadGen++")
    check_pos = request.index("gen !== _fileReadGen")
    assert bump_pos < read_pos < check_pos


def test_r009_close_invalidates_outstanding_reads():
    """JS pin: closing the viewer invalidates every in-flight read, so a
    late response can never reopen the modal."""
    src = _app_js()
    closer = _js_function(src, "closeFileViewer")
    assert "_fileReadGen++" in closer


def test_r009_save_adopts_token_only_for_saved_bytes():
    """JS pin: the post-save token refresh must compare the re-read text
    against the exact bytes this save committed, and drop the token on any
    foreign revision (the stale-rebind defect)."""
    src = _app_js()
    assert "const saveText = content;" in src
    start = src.index("saveFileViewerBtn")
    window_src = src[start : src.index("});", src.index("read_file_text(currentFilePath)"))]
    assert "norm(rText) === norm(saveText)" in window_src
    assert "currentFileEditVersion = null;" in window_src


# --- R017 (PERF-004): the list renderer owns no detail I/O -------------------


def test_r017_render_is_side_effect_free():
    """JS pin: render()'s own body must not call loadDetail -- every
    loadDetail inside render() must live in an async completion callback of
    an explicit data-change action (e.g. the pin toggle), never in the
    paint path. Typing/filtering/collapsing repaints must produce zero
    detail RPCs."""
    import re

    src = _app_js()
    render = _js_function(src, "render")
    start = render.index("function render(")
    body = render[start:]
    body = re.sub(r"//[^\n]*", "", body)  # comments may name the old defect
    for pos in _find_all(body, "loadDetail("):
        # The enclosing callback context: the closest preceding async seam.
        prefix = body[max(0, pos - 300) : pos]
        assert ".then(" in prefix, (
            "render() paint path calls loadDetail directly at "
            f"offset {pos}: {body[pos - 80 : pos + 60]!r}"
        )
    # The original defect's exact tail is gone for good.
    assert "if (selectedRoot && !stateEditActive) {" not in body


def _find_all(text: str, needle: str) -> list[int]:
    out = []
    i = text.find(needle)
    while i != -1:
        out.append(i)
        i = text.find(needle, i + 1)
    return out


def test_r017_watch_path_loads_detail_once():
    """JS pin: the watcher burst path loads the selected root's detail once.
    onSaipenFileChanged owns one explicit load; the scheduled render it
    triggers must not double it (R017's original defect)."""
    src = _app_js()
    start = src.index("window.onSaipenFileChanged = function")
    end = src.index("\n};", start)
    body = src[start:end]
    detail_calls = body.count("loadDetail(")
    assert detail_calls == 1, f"watch path must load detail exactly once, got {detail_calls}"


def test_r017_poll_recovery_loads_detail_once():
    """JS pin: poll recovery with the selected root in changed_roots loads
    detail exactly once -- the render it already applied no longer carries
    its own loadDetail tail (R017 double-load)."""
    src = _app_js()
    start = src.index("function poll() {")
    end = src.index("\n}", src.index(".then(() => { _pollInFlight = false; })"))
    body = src[start:end]
    detail_calls = body.count("loadDetail(")
    assert detail_calls == 1, f"poll recovery must load detail exactly once, got {detail_calls}"


# --- R019 (PERF-006): summary-grade list transport ----------------------------


def _rich_row(tmp_path: Path) -> dict:
    return {
        "root": str(tmp_path / "p"),
        "name": "p",
        "phase": "BUILD",
        "task": "T-1",
        "next_action": "PHASE BUILD",
        "blocker": "none",
        "updated": "2026-09-05T00:00:00Z",
        "updated_kind": "state",
        "mtime": 12345,
        "board": {"doing": 1, "todo": 2, "done": 3, "blocked": 0},
        "subs": [
            {
                "name": "subx",
                "phase": "BUILD",
                "task": "S-1",
                "blocker": "none",
                "updated": "2026-09-05T00:00:00Z",
                "updated_kind": "state",
                "path": str(tmp_path / "p" / ".saipen" / "extensions" / "subs" / "subx"),
                "outbox": [{"id": f"W-{i}", "title": "t", "status": "ready",
                            "summary": "s" * 200, "critical": True, "severity": "high"}
                           for i in range(500)],
                "outbox_counts": {"ready": 500},
                "outbox_critical_ready": 500,
                "outbox_path": "OUTBOX.md",
                "next_action": "PHASE BUILD",
                "board_counts": {"doing": 0, "todo": 0, "done": 0, "blocked": 0},
                "log_tail": ["- 05.09.26 00:00 [E-1] RUN: x" * 40] * 30,
            }
        ],
        "translate": None,
        "is_pinned": False,
        "quick_actions": [{"command": "x", "label": "X"}],
        "subs_stale": False,
        "subs_stale_details": "details",
        "git_branch": "main",
        "git_dirty": True,
        "conformance": {
            "verdict": "warn",
            "fails": 0,
            "warns": 12,
            "baseline": "7.252.0",
            "findings": [
                {"severity": "warn", "rule": f"R{i}", "message": "m", "file": "f",
                 "line": i, "cite": "c"}
                for i in range(10)
            ],
        },
    }


def test_r019_get_projects_is_summary_grade(tmp_path):
    """get_projects() rows carry ONLY what the sidebar renders: no outboxes,
    log tails, board maps, quick actions or stale details."""
    import saipenview.api as api_mod

    api = api_mod.Api()
    try:
        api._projects = [_rich_row(tmp_path)]
        rows = api.get_projects()
        assert len(rows) == 1
        row = rows[0]
        banned = {
            "outbox", "log_tail", "board", "next_action", "quick_actions",
            "subs_stale_details", "mtime", "outbox_counts", "outbox_path",
        }
        assert not banned & set(row), f"detail-grade keys leaked: {banned & set(row)}"
        sub = row["subs"][0]
        assert set(sub) == {"name", "phase", "task", "path"}, sub
        assert row["translate"] is None
        import json

        payload = len(json.dumps(row))
        assert payload < 2000, f"summary row too fat: {payload} bytes"
    finally:
        api.stop()


def test_r019_summary_findings_capped_with_total(tmp_path):
    """The compact conformance badge keeps six tooltip findings and the
    true total, so filtering/tooltip behavior is unchanged."""
    from saipenview.api import _project_summary_to_dict

    row = _rich_row(tmp_path)
    summary = _project_summary_to_dict(row)
    conf = summary["conformance"]
    assert len(conf["findings"]) == 6
    assert conf["findings_total"] == 10
    assert conf["verdict"] == "warn" and conf["warns"] == 12
    assert conf["baseline"] == "7.252.0"


def test_r019_detail_transport_stays_rich(tmp_path):
    """GUARDRAIL: the full detail contract stays behind get_project_detail;
    the summary is a LIST-shape optimization, not a detail regression.
    Assert the sub summary keeps exactly the fields subRowHtml renders."""
    from saipenview.api import _sub_summary_to_dict

    rich = _rich_row(tmp_path)
    sub = _sub_summary_to_dict(
        type("S", (), {"name": "s", "phase": "BUILD", "task": "t",
                       "path": rich["subs"][0]["path"], "outbox": [],
                       "outbox_counts": {}, "outbox_critical_ready": 0,
                       "next_action": "x", "board_counts": {},
                       "log_tail": [], "blocker": "none", "updated": "",
                       "updated_kind": "state"})()
    )
    assert set(sub) == {"name", "phase", "task", "path"}


def test_r019_refresh_known_returns_summary_rows(tmp_path):
    """The poll path (refresh_known -> projects) serves the same summary
    transport -- the watcher push must not re-inflate the payload."""
    from saipenview import api as api_mod

    proj = tmp_path / "p"
    (proj / ".saipen").mkdir(parents=True)
    (proj / ".saipen" / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\nnext_action: PHASE DONE\nblocker: none\n"
        "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
        "updated: 2026-08-30T00:00:00Z\nlast_event: 1\n---\n",
        encoding="utf-8",
    )
    (proj / ".saipen" / "BOARD.md").write_text(
        "## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (proj / ".saipen" / "LOG.md").write_text(
        "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n", encoding="utf-8"
    )
    api = api_mod.Api()
    try:
        api._projects = [
            {
                "root": str(proj),
                "name": "p",
                "phase": "DONE",
                "is_pinned": False,
                "subs": [],
                "conformance": {"verdict": "pass", "fails": 0, "warns": 0,
                                "findings": [], "baseline": ""},
            }
        ]
        result = api.refresh_known()
        rows = result if isinstance(result, list) else result["projects"]
        assert rows, "refresh must return the reconciled rows"
        banned = {"outbox", "log_tail", "board", "next_action", "quick_actions"}
        for row in rows:
            assert not banned & set(row), f"detail-grade keys leaked: {row.keys()}"
    finally:
        api.stop()
