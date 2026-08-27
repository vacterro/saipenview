"""T-596 / PERF-007: tails must not materialize whole logs.

``load_log_tail`` / ``load_sub_log_tail`` / ``SessionStore.transcript``
promised a tail but read and split the complete file first -- a 5 MiB log
cost ~20 ms and ~11.8 MB of peak traced allocation to show three-to-five
lines, and sub tails re-read on every project parse. The contract now:

* returned values are EXACTLY the legacy implementation's output for every
  input class (entries filter, strip, CRLF normalization, trailing-record
  handling, graceful fallbacks);
* UTF-8-no-BOM files take the bounded backward walk; anything exotic (BOM,
  UTF-16) falls back to the legacy whole-file decode;
* peak memory scales with the tail window, never the file size;
* ``SessionStore.transcript`` uses a finished run's metadata ``line_count``
  as the authoritative total and still answers exactly when it is absent.
"""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

from saipenview.parser import load_log_tail, load_sub_log_tail
from saipenview.sessions import SessionStore
from saipenview.tailio import tail_entry_lines, tail_raw_lines


def _legacy_entries(path: Path, max_lines: int) -> list[str]:
    raw = path.read_bytes()
    text = (
        raw[3:].decode("utf-8-sig")
        if raw.startswith(b"\xef\xbb\xbf")
        else raw.decode("utf-8", errors="replace")
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("-")]
    return lines[-max_lines:]


def _legacy_transcript(path: Path, max_lines: int) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"lines": [], "total": 0, "found": False}
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return {"lines": lines[-max_lines:], "total": len(lines), "found": True}


def _big_log(entries: int = 40, filler_bytes: int = 5 * 1024 * 1024) -> str:
    """A big LOG whose wanted entries sit at the very end."""
    parts = ["# header", "- 01.01.26 00:00 [E-1] RUN: old entry", ""]
    parts.append("x" * filler_bytes)
    parts.append("")
    parts.append("# recent notes, not entries")
    for i in range(entries):
        parts.append(f"- 02.01.26 10:{i:02d} [E-{100 + i}] RUN: recent entry {i}")
        if i % 3 == 0:
            parts.append("   indented continuation detail")
        if i % 4 == 0:
            parts.append("")
    return "\n".join(parts) + "\n"


class TestEntryTailParity:
    def test_big_log_last_five_entries_match_legacy(self, tmp_path):
        p = tmp_path / "LOG.md"
        p.write_text(_big_log(), encoding="utf-8")
        got = tail_entry_lines(p, 5)
        assert got is not None
        assert got == _legacy_entries(p, 5)
        assert len(got) == 5
        assert got[-1].endswith("recent entry 39")

    def test_load_log_tail_and_sub_tail_use_the_bounded_path(self, tmp_path):
        root = tmp_path / "proj" / ".saipen"
        root.mkdir(parents=True)
        (root / "LOG.md").write_text(_big_log(), encoding="utf-8")
        sub = tmp_path / "proj" / ".saipen" / "subs" / "saipython"
        sub.mkdir(parents=True)
        (sub / "LOG.md").write_text(_big_log(), encoding="utf-8")

        expected = _legacy_entries(root / "LOG.md", 5)
        assert load_log_tail(tmp_path / "proj", 5) == expected
        assert load_sub_log_tail(sub, 3) == _legacy_entries(sub / "LOG.md", 3)

    def test_small_and_degenerate_files_match_legacy(self, tmp_path):
        cases = [
            "",
            "\n",
            "- only entry\n",
            "no entries at all\njust text\n",
            "- a\n- b\n- c\n",
            "- a\n\n\n- b\n",
            "text before\n- e1\nmid text\n- e2\n",
            "- e1\n- e2",  # no trailing newline
            "\r\n- crlf entry\r\nplain\r\n- last\r\n",
            "﻿- bom entry\n- second\n",  # utf-8 BOM -> legacy fallback
        ]
        for i, content in enumerate(cases):
            p = tmp_path / f"LOG-{i}.md"
            p.write_text(content, encoding="utf-8")
            for want in (1, 3, 10):
                got = tail_entry_lines(p, want)
                # BOM'd files take the legacy fallback inside the callers;
                # the raw tailio API reports None for them instead.
                if content.startswith("﻿"):
                    assert got is None
                    continue
                assert got == _legacy_entries(p, want), (i, want)

    def test_utf16_falls_back_to_none(self, tmp_path):
        p = tmp_path / "LOG.md"
        p.write_bytes("- entry\n".encode("utf-16-le"))
        assert tail_entry_lines(p, 3) is None

    def test_budget_exhaustion_returns_none_not_partial_truth(self, tmp_path):
        p = tmp_path / "LOG.md"
        body = "".join(
            f"- entry {i}\n" + "z" * 2048 + "\n" for i in range(2000)
        )
        p.write_text(body, encoding="utf-8")
        # Entries are far apart; a tiny budget cannot guarantee the real
        # last-N -- refuse rather than return a wrong tail.
        assert tail_entry_lines(p, 50, budget=64 * 1024) is None

    def test_peak_memory_is_bounded_by_the_window(self, tmp_path):
        p = tmp_path / "LOG.md"
        p.write_text(_big_log(), encoding="utf-8")
        tracemalloc.start()
        try:
            got = tail_entry_lines(p, 5)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert got is not None and len(got) == 5
        # The audit measured ~11.8 MB peak on this shape; the backward walk
        # must stay orders of magnitude below the file size.
        assert peak < 2 * 1024 * 1024, f"peak {peak} bytes"

    def test_latency_does_not_scale_with_file_size(self, tmp_path):
        small = tmp_path / "small.md"
        big = tmp_path / "big.md"
        small.write_text(_big_log(filler_bytes=0), encoding="utf-8")
        big.write_text(_big_log(filler_bytes=8 * 1024 * 1024), encoding="utf-8")

        def timed(path):
            t0 = time.perf_counter()
            for _ in range(5):
                tail_entry_lines(path, 5)
            return (time.perf_counter() - t0) / 5

        t_small, t_big = timed(small), timed(big)
        # The extra 8 MiB of dead weight must cost (almost) nothing.
        assert t_big < t_small + 0.05, (t_small, t_big)


class TestTranscriptParity:
    def _store(self, tmp_path: Path) -> SessionStore:
        return SessionStore(base_dir=tmp_path / "sessions")

    def _write_run(
        self,
        store: SessionStore,
        run_id: str,
        n_lines: int,
        *,
        finished: bool = True,
        line_count: int | None = None,
        trailing_newline: bool = True,
    ) -> Path:
        d = store._dir
        d.mkdir(parents=True, exist_ok=True)
        log = d / f"{run_id}.log"
        body = "".join(f"line {i}\n" for i in range(n_lines))
        if not trailing_newline and n_lines:
            body = body[: -len("\n")] + "partial"
        # Real transcripts are written with newline="\n" (LF on disk).
        log.write_bytes(body.encode("utf-8"))
        meta = {
            "run_id": run_id,
            "root_key": "k",
            "engine": "e",
            "instruction": "go",
            "started_at": "2026-08-26T00:00:00+00:00",
            "status": "done" if finished else "running",
            "line_count": line_count if line_count is not None else n_lines,
        }
        if finished:
            meta["finished_at"] = "2026-08-26T00:01:00+00:00"
        (d / f"{run_id}.json").write_text(json.dumps(meta), encoding="utf-8")
        return log

    def test_finished_meta_line_count_is_authoritative_for_total(self, tmp_path):
        store = self._store(tmp_path)
        log = self._write_run(store, "r1", 3000)
        res = store.transcript("r1", max_lines=5)
        assert res["found"] is True
        assert res["total"] == 3000
        assert res["lines"] == _legacy_transcript(log, 5)["lines"]

    def test_small_finished_file_without_meta_still_exact(self, tmp_path):
        store = self._store(tmp_path)
        log = self._write_run(store, "r2", 7)
        (store._dir / "r2.json").unlink()
        res = store.transcript("r2", max_lines=5)
        assert res == _legacy_transcript(log, 5)

    def test_large_file_without_meta_falls_back_to_exact_full_read(
        self, tmp_path
    ):
        store = self._store(tmp_path)
        log = self._write_run(store, "r3", 4000)
        (store._dir / "r3.json").unlink()
        res = store.transcript("r3", max_lines=10)
        assert res == _legacy_transcript(log, 10)

    def test_running_meta_is_not_trusted_but_result_matches(self, tmp_path):
        store = self._store(tmp_path)
        log = self._write_run(store, "r4", 12, finished=False, line_count=9999)
        res = store.transcript("r4", max_lines=5)
        assert res == _legacy_transcript(log, 5)

    def test_trailing_record_without_newline_counts_once(self, tmp_path):
        store = self._store(tmp_path)
        log = self._write_run(store, "r5", 4, finished=False, trailing_newline=False)
        res = store.transcript("r5", max_lines=3)
        assert res == _legacy_transcript(log, 3)

    def test_empty_log_and_missing_run(self, tmp_path):
        store = self._store(tmp_path)
        self._write_run(store, "r6", 0, finished=False, line_count=0)
        assert store.transcript("r6") == {
            "lines": [],
            "total": 0,
            "found": True,
        }
        assert store.transcript("missing") == {
            "lines": [],
            "total": 0,
            "found": False,
        }

    def test_raw_tail_reached_bof_flag_is_accurate(self, tmp_path):
        store = self._store(tmp_path)
        log = self._write_run(store, "r7", 6)
        got = tail_raw_lines(log, 4)
        assert got is not None
        lines, reached_bof = got
        assert reached_bof is False  # stopped after 4 records, never saw BOF
        assert lines == [f"line {i}" for i in range(2, 6)]
