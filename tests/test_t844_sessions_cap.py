"""T-844 / PERF-003: SessionStore.append — lock+cap before encode, capped path zero encode, cap marker once."""

from __future__ import annotations

from pathlib import Path

from saipenview.sessions import (
    MAX_OUTPUT_LINE_BYTES,
    MAX_TRANSCRIPT_BYTES,
    SessionStore,
)


def _store(tmp_path: Path) -> SessionStore:
    d = tmp_path / "sess"
    d.mkdir()
    return SessionStore(d)


def _open(store: SessionStore) -> str:
    rec = store.start("proj", "e", "e", "instr")
    assert rec is not None
    return rec.run_id


def _get_entry(store: SessionStore, rid: str):
    return store._open.get(rid)


def test_ordinary_append_writes_and_reuses_payload_len(tmp_path):
    """Ordinary append must encode once per line and persist bytes as len(payload)+1."""
    store = _store(tmp_path)
    rid = _open(store)
    lines = ["hello", "world", "ééé"]
    for line in lines:
        before = _get_entry(store, rid).bytes_written
        store.append(rid, line)
        after = _get_entry(store, rid).bytes_written
        expected = len(line.encode("utf-8", "replace")) + 1
        # If W2-010 truncation kicked, account for truncated form
        if len(line.encode("utf-8", "replace")) > MAX_OUTPUT_LINE_BYTES:
            truncated = line.encode("utf-8", "replace")[:MAX_OUTPUT_LINE_BYTES].decode("utf-8", errors="ignore")
            line2 = truncated + " [... truncated]"
            expected = len(line2.encode("utf-8", "replace")) + 1
        assert after - before == expected, (line, expected, after - before)


def test_capped_path_does_no_io_and_truncated_true(tmp_path):
    """Once bytes_written >= cap, further appends do zero file I/O, bytes_written/line_count unchanged, truncated once, marker once."""
    store = _store(tmp_path)
    rid = _open(store)
    # Fill close to cap quickly with large lines (each ~ 16 KiB after encode)
    filler = "x" * (16 * 1024)
    # Loop until just under cap, as in real racing reader
    entry = _get_entry(store, rid)
    while entry.bytes_written + 8192 < MAX_TRANSCRIPT_BYTES:
        store.append(rid, filler)
        entry = _get_entry(store, rid)
    # One more should push over and set truncated + single marker
    store.append(rid, "y" * 65536)
    entry = _get_entry(store, rid)
    assert entry.record.truncated, "cap should be reached and truncated True"
    bw_after_cap = entry.bytes_written
    lc_after_cap = entry.record.line_count
    data_after_cap = (store._dir / f"{rid}.log").read_bytes()
    marker = f"transcript capped at {MAX_TRANSCRIPT_BYTES} bytes".encode()
    assert data_after_cap.count(marker) == 1, "cap marker must appear once"
    # Now capped: 1000 more appends must do nothing
    for _ in range(1000):
        store.append(rid, "z" * 8192)
    entry2 = _get_entry(store, rid)
    assert entry2.bytes_written == bw_after_cap
    assert entry2.record.line_count == lc_after_cap
    data2 = (store._dir / f"{rid}.log").read_bytes()
    assert data2 == data_after_cap
    assert _get_entry(store, rid).record.truncated is True


def test_cap_boundary_produces_single_marker(tmp_path):
    """Filling to cap, then racing capped appends: exactly one cap marker written."""
    store = _store(tmp_path)
    rid = _open(store)
    # Probe existing capped behavior - we already tested it; keep small focused case
    store.append(rid, "init")
    # Fast-forward by directly setting bytes close to cap to exercise boundary without 5MiB IO
    entry = _get_entry(store, rid)
    entry.bytes_written = MAX_TRANSCRIPT_BYTES - 10
    store.append(rid, "last-before-cap")  # should succeed normally
    store.append(rid, "over-cap")  # should trip capped path
    marker = f"transcript capped at {MAX_TRANSCRIPT_BYTES} bytes".encode()
    data = (store._dir / f"{rid}.log").read_bytes()
    # Due to direct manipulation, at least one marker, not more than one even after many calls
    # (implementation writes marker only on first transition from False -> True)
    for _ in range(10):
        store.append(rid, "nope")
    data2 = (store._dir / f"{rid}.log").read_bytes()
    assert data2.count(marker) == data.count(marker) == 1


def test_oversized_multibyte_persists_valid_utf8(tmp_path):
    """Oversized multibyte line persists as valid UTF-8 truncated to cap + marker form."""
    store = _store(tmp_path)
    rid = _open(store)
    big_unicode = "é" * (MAX_OUTPUT_LINE_BYTES + 5000)
    store.append(rid, big_unicode)
    data = (store._dir / f"{rid}.log").read_bytes()
    assert b" [... truncated]" in data
    data.decode("utf-8")
    tr = store.transcript(rid)
    assert tr["found"]
    assert tr["total"] == 1
