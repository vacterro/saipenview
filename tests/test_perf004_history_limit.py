"""PERF-004 (SRC-018 R014 / T-865): history/last_run limit contract.

The audited defect: ``SessionStore.history()`` read EVERY metadata record for
the target project, re-stat'ed each file a second time for ordering, sorted
all of it, and only then applied the limit -- so ``last_run()`` performed O(H)
metadata work for ``limit=1``.

Fixed contract:
  * ``last_run`` work is proportional to the newest candidate/tie group;
  * ``history(limit=N)`` reads only enough newest candidates to obtain N valid
    records (plus the boundary tie group, so same-clock mtime ordering holds);
  * NO duplicate stat per metadata file (ordering mtime comes from the same
    stat the decode cache uses);
  * same-clock collision ordering remains correct;
  * corrupt records are skipped without consuming the requested limit;
  * out-of-process metadata becomes visible after the index signature moves;
  * pending-terminal overlay and interrupted reconciliation stay correct.
"""

from __future__ import annotations

import json
from pathlib import Path

from saipenview.sessions import SessionStore, project_key


def _write_meta(
    dir_: Path,
    key: str,
    stamp: str,
    engine: str = "codex",
    status: str = "done",
    started_at: str | None = None,
    root: str | None = None,
) -> Path:
    run_id = f"{stamp}-{key}-{engine}"
    rec = {
        "run_id": run_id,
        "root": root if root is not None else f"V:\\proj\\{key}",
        "project": key,
        "engine": engine,
        "engine_display": engine.title(),
        "instruction": "go",
        "started_at": started_at or f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        f"T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}.{stamp[15:21]}",
        "status": status,
        "finished_at": "2026-01-01T00:01:00Z",
        "exit_code": 0,
        "line_count": 3,
        "truncated": False,
        "pid": None,
    }
    p = dir_ / f"{run_id}.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p


def _make_store(tmp_path: Path, n: int = 50) -> tuple[SessionStore, str]:
    base = tmp_path / "sessions"
    base.mkdir(exist_ok=True)
    store = SessionStore(base_dir=base)
    key = project_key(r"V:\proj\alpha")
    for i in range(n):
        # Distinct stamps, i ascending = older. 12 digits after T.
        stamp = f"20260101T010{i:02d}{i % 10:02d}{i % 10:05d}"
        _write_meta(base, key, stamp, engine=f"e{i}", root=r"V:\proj\alpha")
    return store, key


def test_last_run_reads_only_newest_candidate(tmp_path):
    """last_run (limit=1) must not decode all 50 records: the 50-record audit
    oracle."""
    import pathlib

    store, key = _make_store(tmp_path, n=50)
    store.history(r"V:\proj\alpha")  # warm the filename index

    decodes = {"n": 0}
    real_read_text = pathlib.Path.read_text

    def counting_read_text(self, *a, **k):
        if str(self).endswith(".json"):
            decodes["n"] += 1
        return real_read_text(self, *a, **k)

    pathlib.Path.read_text = counting_read_text
    try:
        store._invalidate_meta_cache()  # drop the warm decode cache
        last = store.last_run(r"V:\proj\alpha")
    finally:
        pathlib.Path.read_text = real_read_text

    assert last is not None
    assert last["engine"] == "e49", f"wrong newest run: {last['engine']}"
    assert decodes["n"] == 1, (
        f"last_run decoded {decodes['n']} metadata files for limit=1 -- "
        "work is not proportional to the newest candidate"
    )


def test_history_limit_reads_only_enough_newest(tmp_path):
    import pathlib

    store, key = _make_store(tmp_path, n=50)
    store.history(r"V:\proj\alpha")

    decodes = {"n": 0}
    real_read_text = pathlib.Path.read_text

    def counting_read_text(self, *a, **k):
        if str(self).endswith(".json"):
            decodes["n"] += 1
        return real_read_text(self, *a, **k)

    pathlib.Path.read_text = counting_read_text
    try:
        store._invalidate_meta_cache()
        runs = store.history(r"V:\proj\alpha", limit=5)
    finally:
        pathlib.Path.read_text = real_read_text

    assert [r["engine"] for r in runs] == ["e49", "e48", "e47", "e46", "e45"]
    assert decodes["n"] <= 5, (
        f"history(limit=5) decoded {decodes['n']} metadata files -- "
        "should read only enough newest candidates for N valid records"
    )


def test_no_duplicate_stat_per_metadata_file(tmp_path):
    import pathlib

    store, key = _make_store(tmp_path, n=10)
    store.history(r"V:\proj\alpha")

    stats = {"n": 0}
    real_stat = pathlib.Path.stat

    def counting_stat(self, *a, **k):
        if str(self).endswith(".json"):
            stats["n"] += 1
        return real_stat(self, *a, **k)

    pathlib.Path.stat = counting_stat
    try:
        store._invalidate_meta_cache()
        runs = store.history(r"V:\proj\alpha", limit=10)
    finally:
        pathlib.Path.stat = real_stat

    assert len(runs) == 10
    # Exactly ONE stat per metadata file: the decode-cache signature AND the
    # ordering mtime come from the same call.
    assert stats["n"] == 10, (
        f"history stat'ed metadata files {stats['n']} times for 10 files -- "
        "duplicate stat work"
    )


def test_corrupt_records_do_not_consume_the_limit(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key = project_key(r"V:\proj\alpha")
    for i in range(6):
        stamp = f"20260101T010{i:02d}{i % 10:02d}{i % 10:05d}"
        p = _write_meta(
            base, key, stamp, engine=f"e{i}", root=r"V:\proj\alpha"
        )
        if i in (4, 3):  # two of the newest are corrupt
            p.write_text("{ not json", encoding="utf-8")

    runs = store.history(r"V:\proj\alpha", limit=2)
    assert [r["engine"] for r in runs] == ["e5", "e2"], (
        f"corrupt records leaked into the limit: {[r['engine'] for r in runs]}"
    )


def test_same_clock_collision_ordering_stays_correct(tmp_path):
    """Two runs in the same clock tick: the later-created meta file (higher
    mtime) must sort newer, exactly as the old full-sort did."""
    import os
    import time

    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key = project_key(r"V:\proj\alpha")
    stamp = "20260101T010203000001"
    older = _write_meta(base, key, stamp, engine="a-first")
    newer = _write_meta(base, key, stamp, engine="b-second")
    # Force distinct creation-order mtimes (the tie-breaker).
    m0 = int(time.time() * 1e9)
    os.utime(older, ns=(m0, m0))
    os.utime(newer, ns=(m0 + 5_000_000, m0 + 5_000_000))

    store._invalidate_meta_cache()
    last = store.last_run(r"V:\proj\alpha")
    assert last["engine"] == "b-second", (
        f"same-clock tie broken wrong: {last['engine']}"
    )
    runs = store.history(r"V:\proj\alpha", limit=1)
    assert runs[0]["engine"] == "b-second"


def test_history_unlimited_still_returns_everything(tmp_path):
    store, key = _make_store(tmp_path, n=12)
    runs = store.history(r"V:\proj\alpha", limit=None)
    assert len(runs) == 12
    assert runs[0]["engine"] == "e11"
    assert runs[-1]["engine"] == "e0"


def test_out_of_process_file_visible_after_signature_moves(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key = project_key(r"V:\proj\alpha")
    _write_meta(
        base, key, "20260101T010101000001", engine="e1", root=r"V:\proj\alpha"
    )
    assert len(store.history(r"V:\proj\alpha")) == 1
    import os

    before = base.stat().st_mtime_ns
    _write_meta(
        base, key, "20260101T010102000002", engine="e2", root=r"V:\proj\alpha"
    )
    os.utime(base, ns=(before + 1_000_000, before + 1_000_000))
    runs = store.history(r"V:\proj\alpha")
    assert len(runs) == 2, "a second process's completed session stayed invisible"
    assert runs[0]["engine"] == "e2"


def test_pending_terminal_overlay_still_applies_to_newest(tmp_path):
    """A running record with a replayable terminal sidecar is overlaid in the
    newest-first path."""
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key = project_key(r"V:\proj\alpha")
    run_id = f"20260101T010101000001-{key}-e1"
    _write_meta(
        base,
        key,
        "20260101T010101000001",
        engine="e1",
        status="running",
        root=r"V:\proj\alpha",
    )

    # Write the durable pending-final sidecar exactly as finish() would.
    record = {
        "run_id": run_id,
        "root": r"V:\proj\alpha",
        "project": key,
        "engine": "e1",
        "engine_display": "E1",
        "instruction": "go",
        "started_at": "2026-01-01T01:01:01.000001",
        "status": "killed",
        "finished_at": "2026-01-01T01:02:00Z",
        "exit_code": 1,
        "line_count": 0,
        "truncated": False,
        "pid": None,
    }
    sidecar_dir = base / ".pending-final" / key
    sidecar_dir.mkdir(parents=True)
    sidecar = sidecar_dir / f"{run_id}.json"
    sidecar.write_text(json.dumps(record), encoding="utf-8")

    store._invalidate_meta_cache()
    last = store.last_run(r"V:\proj\alpha")
    assert last["status"] == "killed", f"sidecar overlay missing: {last['status']}"
    assert last["exit_code"] == 1
