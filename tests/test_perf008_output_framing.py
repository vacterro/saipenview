"""T-597 / PERF-008: the stdout reader must bound a logical record WHILE
reading it, not after an unbounded string already exists.

The old reader iterated ``ap.process.stdout`` -- TextIOWrapper handed it a
complete newline-delimited string of arbitrary length, and only then applied
the 64 Ki cap. A child emitting one multi-megabyte record without a newline
forced the viewer process to materialize the whole thing. The contract now:

* one logical record per newline, capped at OUTPUT_RECORD_MAX_CHARS during
  accumulation, with exactly one `` [... truncated]`` marker per oversized
  record and overflow bytes discarded;
* normal newline-delimited output is byte/text-identical to the old reader
  (CRLF stripped, incremental UTF-8 replace decoding, trailing record at EOF);
* peak reader memory stays near chunk size + cap, never record size;
* latency: a complete line is emitted as soon as it arrives in a short read,
  never held back waiting for a full buffer.
"""

from __future__ import annotations

import sys
import time
import tracemalloc

import pytest

from saipenview.engines.base import AgentEngine
from saipenview.runtime import (
    OUTPUT_RECORD_MAX_CHARS,
    ProcessManager,
    _bounded_output_lines,
)
from saipenview.sessions import SessionStore


class _ChunkedStream:
    """Serves fixed byte chunks, counting reads -- stands in for the raw
    (bufsize=0) pipe so tests control exactly where boundaries fall."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.reads = 0

    def read(self, n: int) -> bytes:
        self.reads += 1
        if self._chunks:
            return self._chunks.pop(0)
        return b""


def _drain(chunks: list[bytes], **kwargs) -> list[str]:
    return list(_bounded_output_lines(_ChunkedStream(chunks), **kwargs))


class TestFramingContract:
    def test_normal_lines_pass_through_identically(self):
        out = _drain([b"hello\nworld\n"])
        assert out == ["hello", "world"]

    def test_crlf_is_stripped_like_the_old_reader(self):
        out = _drain([b"a\r\nbb\r\r\n"])
        # Old code did rstrip("\n\r") per line: all trailing CR characters go.
        assert out == ["a", "bb"]

    def test_multibyte_sequence_split_across_chunks_decodes_intact(self):
        e = "é".encode()
        out = _drain([b"caf", e[:1], e[1:] + b"\ndone\n"])
        assert out == ["café", "done"]

    def test_trailing_record_without_newline_is_still_emitted(self):
        out = _drain([b"one\ntwo"])
        assert out == ["one", "two"]

    def test_invalid_utf8_becomes_replacement_characters(self):
        out = _drain([b"a\xffb\n"])
        assert out == ["a\ufffdb"]

    def test_empty_lines_are_preserved(self):
        out = _drain([b"\n\nx\n"])
        assert out == ["", "", "x"]


class TestBoundedRecords:
    def test_oversized_record_yields_one_capped_line_with_one_marker(self):
        record = b"x" * (OUTPUT_RECORD_MAX_CHARS * 3) + b"\n"
        out = _drain([record[:1000], record[1000:], b"after\n"])
        assert len(out) == 2
        capped, after = out
        assert capped.count(" [... truncated]") == 1
        assert len(capped) == OUTPUT_RECORD_MAX_CHARS + len(" [... truncated]")
        assert after == "after"

    def test_overflow_bytes_until_next_newline_are_discarded(self):
        huge = b"y" * (OUTPUT_RECORD_MAX_CHARS * 2)
        out = _drain([huge, b"tail-junk", b"\nnext\n"])
        assert out[0].count(" [... truncated]") == 1
        assert out[1] == "next"
        assert len(out) == 2

    def test_peak_memory_stays_bounded_by_cap_not_record(self):
        record = b"z" * (4 * 1024 * 1024) + b"\n"
        stream = _ChunkedStream([record])  # single 4 MiB read served in one go
        tracemalloc.start()
        try:
            lines = list(_bounded_output_lines(stream))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert len(lines) == 1 and lines[0].endswith(" [... truncated]")
        # The old path allocated ~3 copies of the whole record (~12 MB traced
        # in the audit's probe); the new path must stay far below record size.
        assert peak < 1024 * 1024, f"peak {peak} bytes"

    def test_a_line_is_yielded_without_waiting_for_more_chunks(self):
        stream = _ChunkedStream([b"first\nseco", b"nd\n"])
        gen = _bounded_output_lines(stream)
        first = next(gen)
        assert first == "first"
        # Only ONE read happened to produce the first line -- latency is not
        # held hostage by the chunk size.
        assert stream.reads == 1
        assert next(gen) == "second"


class TestRealSubprocess:
    class _ScriptEngine(AgentEngine):
        name = "echo-perf008"

        def __init__(self, script: str, with_stdin: bool = False) -> None:
            self._script = script
            self._stdin = with_stdin

        @property
        def display_name(self):
            return "Echo PERF-008"

        def detect(self):
            return True

        def build_command(self, root, instruction, *, extra_args=None):
            return [sys.executable, "-c", self._script]

        @property
        def supports_stdin(self):
            return self._stdin

    def _engine(self, script: str, *, with_stdin: bool = False) -> AgentEngine:
        return self._ScriptEngine(script, with_stdin=with_stdin)

    def test_reader_sees_three_records_with_middle_capped(self, tmp_path):
        pm = ProcessManager()
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        try:
            # The child builds its own oversized record; embedding the payload
            # in the command line would blow past the OS argv limit.
            n = OUTPUT_RECORD_MAX_CHARS * 2
            script = (
                "import sys\n"
                "print('start', flush=True)\n"
                f"sys.stdout.write('m' * {n})\n"
                "sys.stdout.write('tail-of-big')\n"
                "sys.stdout.flush()\n"
                "print(flush=True)\n"
                "print('end', flush=True)\n"
            )
            pm.launch(self._engine(script), str(tmp_path), "go")
            deadline = time.monotonic() + 30
            while pm.get_status(str(tmp_path))["status"] == "running":
                assert time.monotonic() < deadline
                time.sleep(0.05)

            res = pm.get_output(str(tmp_path))
            lines = res["lines"]
            assert res["total"] == 3
            assert lines[0] == "start"
            assert lines[1].count(" [... truncated]") == 1
            assert len(lines[1]) == OUTPUT_RECORD_MAX_CHARS + len(" [... truncated]")
            assert lines[2] == "end"
        finally:
            pm.stop_all()
            pm._output_notifier.cancel()

    def test_stdin_bridge_writes_utf8_bytes_into_the_binary_pipe(self, tmp_path):
        pm = ProcessManager()
        pm.sessions = SessionStore(base_dir=tmp_path / "sessions")
        try:
            script = (
                "import sys\n"
                "data = sys.stdin.buffer.readline()\n"
                # Write raw UTF-8 bytes: the child's own text-stdout encoding
                # is whatever the console defaults to, not ours.
                "sys.stdout.buffer.write(b'GOT:' + data)\n"
            )
            engine = self._engine(script, with_stdin=True)
            pm.launch(engine, str(tmp_path), "go")
            deadline = time.monotonic() + 10
            while pm.get_status(str(tmp_path))["status"] != "running":
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert pm.send_input(str(tmp_path), "héllo wörld")["ok"] is True
            deadline = time.monotonic() + 10
            while pm.get_status(str(tmp_path))["status"] == "running":
                assert time.monotonic() < deadline
                time.sleep(0.05)
            body = "".join(pm.get_output(str(tmp_path))["lines"])
            assert body == "GOT:héllo wörld"
        finally:
            pm.stop_all()
            pm._output_notifier.cancel()


@pytest.mark.parametrize(
    "chunks",
    [
        [b""],
        [b"\n"],
        [b"no-newline-at-all"],
        [b"\xff\xfe\n"],
    ],
)
def test_degenerate_inputs_do_not_hang_or_crash(chunks):
    assert isinstance(_drain(chunks), list)
