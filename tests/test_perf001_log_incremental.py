"""PERF-001: conformance.check_log incremental cache prevents O(n^2) rereads.

400-step append+conformance reproduced 6.7 MiB cumulative reads (199.1x) for
34.45 KiB LOG. Incremental cache must scale with newly appended bytes, not
the sum of every historical prefix.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.conformance import (
    _BOARD_CACHE,
    _LOG_CACHE,
    check_log,
    check_project,
)
from saipenview.parser import parse_frontmatter
from saipenview.textio import read_doc


@pytest.fixture
def project(tmp_path):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text(
        "---\nphase: BUILD\ntask: T-001\nnext_action: work\nblocker: none\n"
        "agent: test\nsaipen_version: 7\nmode: full\n"
        "updated: 2026-08-28T00:00:00Z\ntransition_from: SCOUT\n"
        "schema_version: 3\nlast_event: 1\nstyle_contract: test\n---\n",
        encoding="utf-8",
    )
    (saipen / "BOARD.md").write_text(
        "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    (saipen / "LOG.md").write_text(
        "# Log\n\n- 28.08.26 00:00 [E-1] RUN: bootstrap\n", encoding="utf-8"
    )
    return tmp_path


class _Collector:
    def __init__(self):
        self.findings = []

    def fail(self, *args, **kwargs):
        pass

    def warn(self, *args, **kwargs):
        pass


def test_incremental_append_scales_with_new_bytes_not_history(project):
    log_path = project / ".saipen" / "LOG.md"
    _LOG_CACHE.clear()
    
    from saipenview import conformance
    
    original_load = conformance._load_log_file
    stats = {"full_reads": 0, "append_reads": 0, "full_bytes": 0, "append_bytes": 0}
    
    def tracked_load(path, is_active, cached):
        if cached is not None:
            sig = conformance._log_signature(path)
            if sig == cached.signature:
                return cached
            if (
                sig[:2] == cached.signature[:2]
                and sig[2] > cached.size
                and conformance.encoding_of(path) == "utf-8"
            ):
                stats["append_reads"] += 1
                stats["append_bytes"] += sig[2] - cached.size
            else:
                stats["full_reads"] += 1
                stats["full_bytes"] += sig[2]
        else:
            stats["full_reads"] += 1
            stats["full_bytes"] += path.stat().st_size
        return original_load(path, is_active, cached)
    
    conformance._load_log_file = tracked_load
    
    try:
        c = _Collector()
        check_log(project, c)
        
        for i in range(2, 52):
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"- 28.08.26 00:{i:02d} [E-{i}] [parent: E-{i-1}] RUN: event {i}\n")
            c = _Collector()
            check_log(project, c)
        
        final_size = log_path.stat().st_size
        total_reads = stats["full_bytes"] + stats["append_bytes"]
        
        assert stats["full_reads"] == 1, f"Expected 1 full read, got {stats['full_reads']}"
        assert stats["append_reads"] == 50, f"Expected 50 append reads, got {stats['append_reads']}"
        assert total_reads < final_size * 3, (
            f"Total {total_reads} bytes read for {final_size} byte LOG "
            f"({total_reads/final_size:.1f}x) — should be <3x"
        )
    finally:
        conformance._load_log_file = original_load


def test_incremental_validation_matches_cold_counters(project):
    log_path = project / ".saipen" / "LOG.md"
    _LOG_CACHE.clear()
    state = parse_frontmatter(read_doc(project / ".saipen" / "STATE.md"))

    check_project(project, state)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("malformed log line\n" * 200)
    incremental = check_project(project, state)

    _LOG_CACHE.clear()
    cold = check_project(project, state)
    assert (incremental.fails, incremental.warns, incremental.verdict) == (
        cold.fails,
        cold.warns,
        cold.verdict,
    )


def test_truncation_invalidates_cache_and_reparses_full(project):
    log_path = project / ".saipen" / "LOG.md"
    _LOG_CACHE.clear()

    c = _Collector()
    check_log(project, c)

    for i in range(2, 12):
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"- 28.08.26 00:{i:02d} [E-{i}] [parent: E-{i - 1}] RUN: event {i}\n"
            )

    c = _Collector()
    check_log(project, c)

    log_path.write_text(
        "# Log\n\n- 28.08.26 01:00 [E-1] RUN: fresh start\n", encoding="utf-8"
    )

    c = _Collector()
    check_log(project, c)
    assert len(c.findings) == 0


def test_sealed_segments_cached_independently(project, tmp_path):
    _LOG_CACHE.clear()
    sealed = project / ".saipen" / "logs"
    sealed.mkdir()
    (sealed / "LOG-001.md").write_text(
        "# Log\n\n- 28.08.26 00:00 [E-1] RUN: sealed event 1\n", encoding="utf-8"
    )
    (sealed / "LOG-002.md").write_text(
        "# Log\n\n- 28.08.26 00:01 [E-2] [parent: E-1] RUN: sealed event 2\n",
        encoding="utf-8",
    )
    (project / ".saipen" / "LOG.md").write_text(
        "# Log\n\n- 28.08.26 00:02 [E-3] [parent: E-2] RUN: active\n", encoding="utf-8"
    )

    c = _Collector()
    check_log(project, c)

    from saipenview import conformance
    
    original_load = conformance._load_log_file
    loads = []
    
    def tracked_load(path, is_active, cached):
        loads.append((path.name, cached is not None))
        return original_load(path, is_active, cached)
    
    conformance._load_log_file = tracked_load
    
    try:
        with (project / ".saipen" / "LOG.md").open("a", encoding="utf-8") as handle:
            handle.write("- 28.08.26 00:03 [E-4] [parent: E-3] RUN: appended\n")

        c = _Collector()
        check_log(project, c)

        load_names = {name for name, _ in loads}
        cached_names = {name for name, cached in loads if cached}
        
        assert "LOG-001.md" in load_names
        assert "LOG-002.md" in load_names
        assert "LOG.md" in load_names
        assert "LOG-001.md" in cached_names
        assert "LOG-002.md" in cached_names
        assert "LOG.md" in cached_names
    finally:
        conformance._load_log_file = original_load


def test_state_only_change_skips_board_log_reread(project):
    """PERF-002: STATE-only conformance rerun must not reread BOARD or LOG."""
    _BOARD_CACHE.clear()
    _LOG_CACHE.clear()
    from saipenview import conformance as conf

    calls = {"parse": 0}
    original_parse = conf.parse_board_strict

    def tracked_parse(text):
        calls["parse"] += 1
        return original_parse(text)

    conf.parse_board_strict = tracked_parse
    state = {
        "phase": "BUILD",
        "task": "T-001",
        "next_action": "work",
        "blocker": "none",
        "agent": "test",
        "saipen_version": "7",
        "mode": "full",
        "updated": "2026-08-28T00:00:00Z",
        "transition_from": "SCOUT",
        "schema_version": "3",
        "last_event": "1",
        "style_contract": "test",
    }
    try:
        c = _Collector()
        check_project(project, state)
        first = calls["parse"]

        c = _Collector()
        check_project(project, state)
        assert calls["parse"] == first
    finally:
        conf.parse_board_strict = original_parse


def test_staleness_fingerprint_cache_dedupes(project, tmp_path):
    """PERF-003: repeated staleness reads of unchanged canonical files
    must reuse the SHA-256 instead of re-hashing.
    """
    from saipenview import parser as p

    p._STALENESS_FINGERPRINT_CACHE.clear()

    canon = tmp_path / "canon"
    canon.mkdir()
    file_path = canon / "MANIFEST.md"
    file_path.write_bytes(b"x" * (256 * 1024))

    call_count = {"reads": 0}
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(self, *args, **kwargs):
        if self == file_path:
            call_count["reads"] += 1
        return original_read_bytes(self, *args, **kwargs)

    Path.read_bytes = tracked_read_bytes
    try:
        for _ in range(50):
            p._file_staleness_key(file_path)
        assert call_count["reads"] == 1, (
            f"Expected 1 canonical file read, got {call_count['reads']}"
        )

        file_path.write_bytes(b"y" * (256 * 1024))
        for _ in range(50):
            p._file_staleness_key(file_path)
        assert call_count["reads"] == 2, (
            f"Expected 2 reads after content change, got {call_count['reads']}"
        )
    finally:
        Path.read_bytes = original_read_bytes


def test_protocol_read_single_pass(project, tmp_path):
    """PERF-010: protocol file read must not materialize the file twice."""
    from unittest.mock import MagicMock, patch
    from saipenview.api import Api
    from saipenview import textio

    root = tmp_path / "proj"
    (root / ".saipen").mkdir(parents=True)
    (root / ".saipen" / "STATE.md").write_text("phase: BUILD\n", encoding="utf-8")

    api = object.__new__(Api)
    api._known_roots = lambda: [str(root)]

    reads = []
    orig_read_doc = textio.read_doc

    def tracked_read_doc(p):
        reads.append(str(p))
        return orig_read_doc(p)

    with (
        patch.object(textio, "read_doc", tracked_read_doc),
        patch("saipenview.protocol_write.get_coordinator") as gc,
    ):
        coord = MagicMock()
        coord.is_protocol_file.return_value = True
        coord.root_for.return_value = root
        gc.return_value = coord
        with patch("saipenview.saio.engine") as engine_mock:
            codec = MagicMock()
            doc = MagicMock()
            doc.text_norm = "phase: BUILD\n"
            doc.raw_hash = "abc123"
            codec.read_document.return_value = doc
            engine_mock.return_value = {"codec": codec}
            result = api.read_file_text(str(root / ".saipen" / "STATE.md"))

    assert result == {"text": "phase: BUILD\n", "edit_version": "abc123"}
    assert not reads, "read_doc should not be called for protocol files"


def test_geometry_unchanged_skips_save(project):
    """PERF-013: repeated identical geometry snapshots persist once."""
    from unittest.mock import MagicMock, patch
    from saipenview.ui.window import MainWindow

    api = MagicMock()
    window = MagicMock()
    window.width = 800
    window.height = 600
    window.x = 10
    window.y = 20

    mw = object.__new__(MainWindow)
    mw._api = api
    mw._window = window

    mw._save_geometry()
    assert api.save_view_config.call_count == 1

    mw._save_geometry()
    mw._save_geometry()
    assert api.save_view_config.call_count == 1

    window.width = 900
    mw._save_geometry()
    assert api.save_view_config.call_count == 2

    api.save_view_config.side_effect = RuntimeError("disk full")
    window.width = 1000
    mw._save_geometry()
    # Failure must not update the last-persisted marker; a later success retries.
    assert api.save_view_config.call_count == 3
    api.save_view_config.side_effect = None
    mw._save_geometry()
    assert api.save_view_config.call_count == 4


def test_findings_bounded_but_counters_exact(project):
    """PERF-006: 10k findings -> bounded transport payload, exact totals."""
    from saipenview.conformance import Report, Finding

    findings = [
        Finding("log.skeleton", "fail", f"line {i}", "RFC § 1.2", "LOG.md", i)
        for i in range(10000)
    ]
    report = Report(findings)
    d = report.to_dict()
    assert d["fails"] == 10000
    assert d["verdict"] == "fail"
    assert len(d["findings"]) <= report.MAX_TRANSPORT_FINDINGS
    assert d["findings_total"] == 10000
    assert d["findings_truncated"] is True

    small = Report(findings[:3]).to_dict()
    assert len(small["findings"]) == 3
    assert "findings_total" not in small
    assert "findings_truncated" not in small
