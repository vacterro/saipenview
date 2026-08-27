"""Bounded backward tail readers for large append-only logs.

PERF-007: ``load_log_tail``, ``load_sub_log_tail`` and
``SessionStore.transcript`` promise a tail but used to materialize the whole
file first (`read_doc(...).splitlines()` / `read_text(...).split()`). A 5 MiB
log cost ~20 ms and ~11.8 MB of peak allocations to display three-to-five
recent lines, and sub tails are re-read on every project parse.

The readers here walk the file backward in fixed blocks and stop as soon as
the wanted number of records has been collected, so latency and peak memory
scale with the TAIL, never with total file size. Parity contract with the
whole-file readers they replace:

* UTF-8 files without a BOM take the backward path; every other encoding
  (any BOM, BOM-less UTF-16) returns ``None`` so the caller falls back to its
  exact legacy whole-file decode -- backward byte scans cannot align UTF-16.
* Records are decoded independently; "\\n" is a single byte and can never be
  part of a multi-byte sequence, so per-record decoding is exact.
* Trailing-newline semantics match ``text.split("\\n")`` plus the one
  trailing-empty-string pop: a final record without a terminating newline
  still counts, a file ending in "\\n" does not produce an extra record.
"""

from __future__ import annotations

from pathlib import Path

_BLOCK_BYTES = 65536
_DEFAULT_BUDGET_BYTES = 512 * 1024
_SNIFF_BYTES = 4096


class _UnsupportedEncoding(Exception):
    """Raised internally: the file needs the caller's legacy whole-file path."""


def _sniff_encoding(path: Path) -> str:
    """Return "utf-8" when the backward path is safe, else raise."""
    with path.open("rb") as f:
        head = f.read(_SNIFF_BYTES)
    if head[:4] in (
        b"\x00\x00\xfe\xff",  # UTF-32 BE
        b"\xff\xfe\x00\x00",  # UTF-32 LE
    ):
        raise _UnsupportedEncoding
    if head[:3] == b"\xef\xbb\xbf":  # UTF-8 BOM -> legacy utf-8-sig decode
        raise _UnsupportedEncoding
    if head[:2] in (b"\xfe\xff", b"\xff\xfe"):  # UTF-16 BE/LE BOM
        raise _UnsupportedEncoding
    if len(head) >= 4 and b"\x00" in head:
        # BOM-less UTF-16 looks like alternating NULs; leave it to the
        # caller's whole-file sniffer (mirrors textio._bomless_utf16).
        even_nul = head[0::2].count(0)
        odd_nul = head[1::2].count(0)
        half = len(head) // 2
        if odd_nul > half * 0.3 and even_nul < half * 0.1:
            raise _UnsupportedEncoding
        if even_nul > half * 0.3 and odd_nul < half * 0.1:
            raise _UnsupportedEncoding
    return "utf-8"


def _collect_tail(
    path: Path,
    *,
    wanted: int,
    predicate,
    budget: int,
):
    """Walk *path* backward collecting up to *wanted* records (oldest-last).

    Returns ``(records, reached_bof)`` where *records* is a list of decoded
    strings in file order and *predicate(bytes) -> bool* decides which records
    count toward *wanted*. Scanning stops early once *wanted* records are
    collected; if the byte budget is exhausted first, ``None`` is returned so
    the caller can fall back to its exact whole-file read.
    """
    _sniff_encoding(path)
    size = path.stat().st_size

    def _decode(raw: bytes) -> str:
        # One trailing CR is a CRLF terminator (universal-newlines parity);
        # interior CRs are preserved like any other content byte.
        text = raw.decode("utf-8", errors="replace")
        return text[:-1] if text.endswith("\r") else text

    collected: list[str] = []  # newest-first during the walk
    kept = 0
    buffer = b""
    pos = size
    eof_tail_done = False
    # "Reached BOF" is exact only when the first block's records were ALL
    # scanned -- breaking out early because *wanted* was satisfied means
    # older records exist and the total stays unknown to the caller.
    bof_fully_scanned = False

    with path.open("rb") as f:
        while True:
            if kept >= wanted or pos <= 0:
                break
            if size - pos >= budget:
                return None
            start = max(0, pos - _BLOCK_BYTES)
            f.seek(start)
            chunk = f.read(pos - start)
            pos = start
            at_bof = start == 0
            buffer = chunk + buffer
            parts = buffer.split(b"\n")
            if not eof_tail_done:
                # The right edge is the file end: the segment after the final
                # newline is the EOF tail -- empty when the file ends in "\n".
                eof_tail_done = True
                tail = parts.pop()
                if tail and predicate(tail):
                    collected.append(_decode(tail))
                    kept += 1
                    if kept >= wanted:
                        break
            if at_bof:
                # Everything left is complete, including the leading partial
                # (which is simply the first record).
                complete = parts
                buffer = b""
            else:
                # The first element runs into not-yet-read bytes -- hold it.
                # (parts may be empty when the block held nothing new.)
                if parts:
                    buffer = parts.pop(0)
                complete = parts
            for raw in reversed(complete):
                if predicate(raw):
                    collected.append(_decode(raw))
                    kept += 1
                    if kept >= wanted:
                        break
            if at_bof:
                bof_fully_scanned = kept < wanted
                break

    if kept < wanted and pos > 0:
        # Budget ran out before enough records -- caller falls back.
        return None
    return collected[::-1], bof_fully_scanned


def tail_entry_lines(
    path: Path,
    max_entries: int,
    *,
    budget: int = _DEFAULT_BUDGET_BYTES,
) -> list[str] | None:
    """Last *max_entries* non-empty lines starting with "-", stripped.

    Exact replacement for ``[l.strip() for l in read_doc(p).splitlines()
    if l.strip().startswith("-")][-max_entries:]`` on UTF-8-no-BOM files;
    ``None`` tells the caller to use that legacy path instead.
    """

    def _is_entry(raw: bytes) -> bool:
        return raw.strip().startswith(b"-")

    try:
        result = _collect_tail(
            path, wanted=max_entries, predicate=_is_entry, budget=budget
        )
    except _UnsupportedEncoding:
        return None
    if result is None:
        return None
    records, _reached_bof = result
    return [rec.strip() for rec in records]


def tail_raw_lines(
    path: Path,
    max_lines: int,
    *,
    budget: int = _DEFAULT_BUDGET_BYTES,
) -> tuple[list[str], bool] | None:
    """Last *max_lines* logical records plus whether the scan reached BOF.

    When ``(lines, True)`` is returned the file was fully walked, so
    ``len(lines)`` IS the total record count. ``None`` -> legacy fallback.
    """
    try:
        result = _collect_tail(
            path, wanted=max_lines, predicate=lambda _raw: True, budget=budget
        )
    except _UnsupportedEncoding:
        return None
    if result is None:
        return None
    records, reached_bof = result
    return records, reached_bof
