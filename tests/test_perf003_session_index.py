"""PERF-003: per-project session history must not rescan the whole flat
sessions directory, nor decode the same metadata twice for one panel.

Pre-fix, `_meta_files(key)` ran a fresh `glob("*-<key>-*.json")` over the ONE
flat `_data/sessions/` directory per lookup, and `last_run()` + `history()`
each decoded the same records. Both costs grew with UNRELATED projects' files.

The fix adds a rebuildable process-local filename index (invalidated on any
directory change or self-write) and a metadata decode cache keyed on each
file's (mtime_ns, size). Authority still lives in the individual files.
"""

from __future__ import annotations

import json
import os

from saipenview.sessions import SessionStore, project_key


def _write_meta(dir_, key, stamp, engine="codex", status="done"):
    run_id = f"{stamp}-{key}-{engine}"
    rec = {
        "run_id": run_id,
        "root": f"V:\\proj\\{key}",
        "project": key,
        "engine": engine,
        "engine_display": engine.title(),
        "instruction": "go",
        "started_at": f"2026-01-01T00:00:{stamp[-2:] if stamp[-2:].isdigit() else '00'}Z",
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


def test_steady_state_lookup_does_not_rescan_unrelated_files(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key_a = project_key(r"V:\proj\alpha")

    # 50 sessions for the target project + 2000 unrelated files.
    for i in range(50):
        _write_meta(base, key_a, f"20260101T0000{i:02d}000000", engine=f"e{i}")
    other_keys = [f"{i:010x}" for i in range(2000)]
    for k in other_keys:
        _write_meta(base, k, "20260101T000000000000", engine="x")

    # First lookup builds the index (one real glob).
    first = store._meta_files(key_a)
    assert len(first) == 50

    # Instrument glob: a steady-state lookup must perform ZERO globs.
    real_glob = type(base).glob
    globs = {"n": 0}

    def counting_glob(self, pattern):
        globs["n"] += 1
        return real_glob(self, pattern)

    import pathlib

    orig = pathlib.Path.glob
    pathlib.Path.glob = counting_glob
    try:
        for _ in range(20):
            got = store._meta_files(key_a)
            assert len(got) == 50
    finally:
        pathlib.Path.glob = orig
    assert globs["n"] == 0, f"steady-state lookup rescanned the directory {globs['n']}x"


def test_idle_panel_does_not_decode_metadata_twice(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key_a = project_key(r"V:\proj\alpha")
    for i in range(50):
        _write_meta(base, key_a, f"20260101T0000{i:02d}000000", engine=f"e{i}")

    # Count real JSON decodes of metadata files.
    import pathlib

    real_read_text = pathlib.Path.read_text
    decodes = {"n": 0}

    def counting_read_text(self, *a, **k):
        if str(self).endswith(".json"):
            decodes["n"] += 1
        return real_read_text(self, *a, **k)

    pathlib.Path.read_text = counting_read_text
    try:
        # The idle panel's two calls: last_run() then history().
        store.last_run(r"V:\proj\alpha")
        store.history(r"V:\proj\alpha", limit=20)
    finally:
        pathlib.Path.read_text = real_read_text

    # One panel population must not decode the same 50 records twice.
    assert decodes["n"] <= 50, (
        f"idle panel decoded {decodes['n']} metadata files for 50 records"
    )


def test_external_new_file_becomes_visible(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    key_a = project_key(r"V:\proj\alpha")
    _write_meta(base, key_a, "20260101T000000000001", engine="e1")
    assert len(store.history(r"V:\proj\alpha")) == 1

    # A second process writes a new run and bumps the directory mtime. The
    # stamp is forced explicitly: `os.utime(base, None)` only sets the mtime to
    # "now", and on NTFS the directory's st_mtime_ns advances per tick -- a
    # write and the utime landing in the same tick leave the signature
    # unchanged, so the invalidation this test means to prove would not fire.
    before = base.stat().st_mtime_ns
    _write_meta(base, key_a, "20260101T000000000002", engine="e2")
    os.utime(base, ns=(before + 1_000_000, before + 1_000_000))
    runs = store.history(r"V:\proj\alpha")
    assert len(runs) == 2, "a second process's completed session stayed invisible"


def test_legacy_flat_records_still_discovered(tmp_path):
    base = tmp_path / "sessions"
    base.mkdir()
    store = SessionStore(base_dir=base)
    # A store written by an OLDER run (plain flat files) must still be found.
    key_a = project_key(r"V:\proj\alpha")
    _write_meta(base, key_a, "20260101T000000000001", engine="legacy")
    runs = store.history(r"V:\proj\alpha")
    assert len(runs) == 1
    assert runs[0]["engine"] == "legacy"


