"""The LOG grader's per-line hot path: fewer passes, same verdict.

`_parse_log_record` runs once per line of every LOG segment of every project,
so a full grade of a real tree crosses ~23k lines. Three things in it were
per-line waste rather than per-line work: `strptime` (which rebuilds a
format-driven matcher and re-reads the locale on every call), two extra regex
passes re-deriving the date and event id the skeleton match had already seen,
and a `datetime.now()` per dated record while folding.

Speed is not the contract, so these tests do not assert timings. They assert
the thing that makes the speed safe: the cheap path answers EXACTLY what the
expensive one did, including the awkward cases (the two-digit-year pivot,
out-of-range components, undated lines, non-entry lines).
"""

from __future__ import annotations

import datetime

import pytest

from saipenview import conformance
from saipenview.conformance import (
    _LOG_ANY_EVENT_RE,
    _LOG_ENTRY_RE,
    _LOG_SKELETON_RE,
    _log_stamp,
    _parse_log_record,
)

UTC = datetime.timezone.utc

# The reference spelling this optimisation must stay identical to.
_STRPTIME_FORMAT = "%d.%m.%y %H:%M"


def _reference_stamp(day: str, clock: str) -> datetime.datetime:
    return datetime.datetime.strptime(f"{day} {clock}", _STRPTIME_FORMAT).replace(
        tzinfo=UTC
    )


@pytest.mark.parametrize(
    "day,clock",
    [
        ("01.01.00", "00:00"),  # lowest two-digit year
        ("31.12.68", "23:59"),  # last year that pivots to 20xx
        ("01.01.69", "12:30"),  # first year that pivots to 19xx
        ("31.12.99", "23:59"),  # highest two-digit year
        ("29.02.24", "00:00"),  # leap day
        ("03.09.26", "19:23"),  # ordinary current stamp
    ],
)
def test_log_stamp_matches_strptime(day: str, clock: str) -> None:
    assert _log_stamp(day, clock) == _reference_stamp(day, clock)


@pytest.mark.parametrize(
    "day,clock",
    [
        ("32.01.26", "00:00"),  # day out of range
        ("01.13.26", "00:00"),  # month out of range
        ("01.01.26", "25:00"),  # hour out of range
        ("30.02.26", "00:00"),  # day not in that month
        ("00.01.26", "00:00"),  # zero day
    ],
)
def test_log_stamp_rejects_what_strptime_rejects(day: str, clock: str) -> None:
    """An impossible stamp must still raise, so the caller still records it as
    undated instead of inventing a date."""
    with pytest.raises(ValueError):
        _reference_stamp(day, clock)
    with pytest.raises(ValueError):
        _log_stamp(day, clock)


def test_skeleton_groups_carry_date_and_event() -> None:
    """The single skeleton match must expose everything the two dropped
    patterns used to re-derive, or the hot path silently loses information."""
    line = (
        "- 03.09.26 19:23 [E-888] [parent: E-887] [T-810] [agent: agents] "
        "[op: silence-x] RUN: did the thing"
    )
    match = _LOG_SKELETON_RE.match(line)
    assert match is not None
    day, clock, event, parent, ticket, taxonomy, text = match.groups()
    assert (day, clock) == ("03.09.26", "19:23")
    assert event == "888"
    assert parent == "887"
    assert ticket == "T-810"
    assert taxonomy == "RUN"
    assert text == "did the thing"
    # Identical to what the reference patterns produced.
    assert _LOG_ENTRY_RE.match(line).group(1, 2) == (day, clock)
    assert _LOG_ANY_EVENT_RE.match(line).group(1) == event


def test_undated_entry_still_parses_as_undated(tmp_path) -> None:
    """A legal-but-undated sealed-segment line keeps event id and dated=False."""
    line = "- [E-42] [parent: E-41] DEC: historical, no stamp"
    record = _parse_log_record(line, tmp_path / "LOG-001.md", 7, is_active=False)
    assert record is not None
    assert record.event == 42
    assert record.dated is False
    assert record.stamp is None
    assert record.fails == 0  # only the ACTIVE log fails on a missing stamp


def test_undated_entry_in_active_log_fails() -> None:
    from pathlib import Path

    line = "- [E-42] RUN: no stamp in the live log"
    record = _parse_log_record(line, Path("LOG.md"), 3, is_active=True)
    assert record is not None
    assert record.dated is False
    assert record.fails == 1
    assert [f.rule for f in record.findings] == ["log.timestamp.missing"]


def test_out_of_range_stamp_degrades_to_undated_without_raising() -> None:
    """A stamp that cannot be a date must not crash the grader mid-parse."""
    from pathlib import Path

    line = "- 32.13.26 99:99 [E-9] RUN: impossible stamp"
    record = _parse_log_record(line, Path("LOG.md"), 1, is_active=True)
    assert record is not None
    # The skeleton's date group is shape-only (\d\d.\d\d.\d\d), so this line is
    # still a dated entry structurally; the unparseable value leaves stamp None.
    assert record.stamp is None


def test_fold_uses_one_clock_read_for_the_batch(tmp_path, monkeypatch) -> None:
    """Folding N dated records must not call datetime.now() N times."""
    from pathlib import Path

    log = tmp_path / ".saipen"
    log.mkdir()
    lines = ["# Log"]
    for i in range(1, 61):
        parent = f" [parent: E-{i - 1}]" if i > 1 else ""
        lines.append(f"- 28.08.26 00:{i % 60:02d} [E-{i}]{parent} RUN: entry {i}")
    (log / "LOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    calls = {"now": 0}
    real_datetime = datetime.datetime

    class _CountingDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            calls["now"] += 1
            return real_datetime.now(tz)

    conformance._LOG_CACHE.clear()
    monkeypatch.setattr(conformance.datetime, "datetime", _CountingDatetime)
    aggregate = conformance._log_aggregate(
        tmp_path, (Path(log / "LOG.md"),), Path(log / "LOG.md")
    )
    assert aggregate.prev_event == 60
    assert calls["now"] <= 2, (
        f"one clock read per aggregate expected, got {calls['now']} for 60 records"
    )


def test_grade_is_unchanged_on_a_real_shaped_log(tmp_path) -> None:
    """End-to-end: a log mixing clean, undated, out-of-order and junk lines
    produces the same rule set the slow path produced."""
    from pathlib import Path

    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "LOG.md").write_text(
        "# Log\n"
        "- 28.08.26 00:00 [E-1] RUN: first\n"
        "- 28.08.26 00:01 [E-2] [parent: E-1] DEC: second\n"
        "- 28.08.26 00:02 [E-2] [parent: E-1] DEC: duplicate id\n"
        "- [E-5] RUN: undated in active log\n"
        "this line is not an entry at all\n"
        "- 28.08.26 00:05 [E-6] [parent: E-5] NOPE: unknown verb\n"
        "- 28.08.26 00:06 [E-7] [parent: E-6] [T-oops] RUN: bad ticket ref\n"
        "- 28.08.26 00:07 [E-4] [parent: E-7] DEC: goes backwards\n",
        encoding="utf-8",
    )
    conformance._LOG_CACHE.clear()
    aggregate = conformance._log_aggregate(
        tmp_path, (Path(saipen / "LOG.md"),), Path(saipen / "LOG.md")
    )
    rules = sorted({f.rule for f in aggregate.findings})
    assert rules == [
        "log.event.duplicate",
        "log.event.order",
        "log.skeleton",
        "log.taxonomy",
        "log.ticket_ref",
        "log.timestamp.missing",
    ]
    assert aggregate.undated == 1
    assert aggregate.active_missing is True
    assert aggregate.prev_event == 7
