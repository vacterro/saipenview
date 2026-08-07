r"""T-123: relative time under deterministic clocks.

`relativeTime()` / `formatLocalTime()` used to silently append Z to
timezone-naive stamps (assuming UTC for a value that may be local -- the 1-2h
"timing is wrong" report), and `Math.max(0, ...)` turned a future stamp into
"just now". These run the REAL functions under node with `Date.now` pinned and
a stubbed `t()`, because the bucket boundaries and the tz handling are the
defect and a source-grep proves nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)

# 2026-08-07T12:00:00Z -- the pinned "now".
NOW = "2026-08-07T12:00:00Z"

PREAMBLE = f"""\
process.env.TZ = process.env.TZ || "UTC";
let NOW_MS = Date.parse("{NOW}");
Date.now = function () {{ return NOW_MS; }};
function t(key, params) {{ return (params && params.n !== undefined) ? key.replace("time.", "") + ":" + params.n : key.replace("time.", ""); }}
function escapeHtml(x) {{ return String(x); }}
"""


def _extract(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    brace = source.index("{", start)
    depth = 0
    i = brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    raise AssertionError(f"function {name} never closes")


def _run(script_body: str, tz: str | None = None) -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    fns = "\n".join(
        _extract(source, n)
        for n in ("timestampKind", "formatLocalTime", "relativeTime", "heatColorFor")
    )
    tz_pre = ('process.env.TZ = "' + tz + '";\n') if tz else ""
    r = subprocess.run(
        ["node", "-e", PREAMBLE + tz_pre + fns + "\n" + script_body],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(f"node harness failed: {r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def node_ok() -> None:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("node not available")


class TestBackendClassify:
    """The Python side normalizes valid stamps to explicit UTC (T-123)."""

    def test_utc_passthrough(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("2026-08-07T11:00:00Z") == (
            "2026-08-07T11:00:00Z",
            "utc",
        )

    def test_plus_offset_converted_to_utc(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("2026-08-07T14:00:00+03:00") == (
            "2026-08-07T11:00:00Z",
            "offset",
        )

    def test_minus_offset_converted_to_utc(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("2026-08-07T06:00:00-05:00") == (
            "2026-08-07T11:00:00Z",
            "offset",
        )

    def test_fractional_kept_utc(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("2026-08-07T11:00:00.500Z") == (
            "2026-08-07T11:00:00.500Z",
            "utc",
        )

    def test_naive_kept_raw_and_marked(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("2026-08-07T11:00:00") == (
            "2026-08-07T11:00:00",
            "naive",
        )

    def test_invalid_and_missing(self):
        from saipenview.parser import classify_timestamp

        assert classify_timestamp("garbage")[1] == "invalid"
        assert classify_timestamp("") == ("", "missing")
        assert classify_timestamp(None) == ("", "missing")


class TestKinds:
    def test_explicit_z_is_utc(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({k: timestampKind("2026-08-07T11:00:00Z")}));'
        )
        assert out["k"] == "utc"

    def test_plus_offset_is_offset(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({k: timestampKind("2026-08-07T14:00:00+03:00")}));'
        )
        assert out["k"] == "offset"

    def test_minus_offset_is_offset(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({k: timestampKind("2026-08-07T06:00:00-05:00")}));'
        )
        assert out["k"] == "offset"

    def test_fractional_seconds_is_utc(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({k: timestampKind("2026-08-07T11:00:00.500Z")}));'
        )
        assert out["k"] == "utc"

    def test_naive_is_ambiguous(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({k: timestampKind("2026-08-07T11:00:00")}));'
        )
        assert out["k"] == "naive"

    def test_invalid(self, node_ok):
        out = _run('console.log(JSON.stringify({k: timestampKind("not a date")}));')
        assert out["k"] == "invalid"


class TestAges:
    def test_59_seconds(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:59:01Z")}));'
        )
        assert out["r"] == "secondsAgo:59", out

    def test_60_seconds_rolls_to_minutes(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:59:00Z")}));'
        )
        assert out["r"] == "minutesAgo:1", out

    def test_59_minutes(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:01:00Z")}));'
        )
        assert out["r"] == "minutesAgo:59", out

    def test_60_minutes_rolls_to_hours(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:00:00Z")}));'
        )
        assert out["r"] == "hoursAgo:1", out

    def test_23_hours(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-06T13:00:00Z")}));'
        )
        assert out["r"] == "hoursAgo:23", out

    def test_24_hours_rolls_to_days(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-06T12:00:00Z")}));'
        )
        assert out["r"] == "daysAgo:1", out

    def test_plus_three_offset_counts_same_age(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T14:59:01+03:00", "offset")}));'
        )
        assert out["r"] == "secondsAgo:59", out

    def test_minus_five_offset_counts_same_age(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T06:59:01-05:00", "offset")}));'
        )
        assert out["r"] == "secondsAgo:59", out

    def test_fractional_seconds_floor(self, node_ok):
        # .500 fraction means 58.5s elapsed -> floor 58.
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:59:01.500Z")}));'
        )
        assert out["r"] == "secondsAgo:58", out

    def test_naive_claims_no_age(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T11:59:01", "naive")}));'
        )
        assert out["r"] == "", out

    def test_invalid_claims_no_age(self, node_ok):
        out = _run('console.log(JSON.stringify({r: relativeTime("nope", "invalid")}));')
        assert out["r"] == ""

    def test_future_stamp_is_clock_ahead_not_just_now(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: relativeTime("2026-08-07T13:00:00Z")}));'
        )
        assert out["r"] == "clockAhead", out


class TestLocalDisplay:
    def test_naive_is_marked_not_converted(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: formatLocalTime("2026-08-07T11:59:01", "naive")}));'
        )
        assert "naive" in out["r"], out
        assert out["r"].startswith("2026-08-07T11:59:01"), out

    def test_invalid_passes_through(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: formatLocalTime("nope", "invalid")}));'
        )
        assert out["r"] == "nope"

    def test_z_stamp_renders_local_on_europe_tallinn(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: formatLocalTime("2026-08-07T10:00:00Z", "utc")}));',
            tz="Europe/Tallinn",
        )
        # 10:00 UTC is 13:00 EEST in Tallinn in August.
        assert out["r"] == "2026-08-07 13:00", out

    def test_dst_boundary_renders_same_wall_clock(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({a: formatLocalTime("2026-03-29T00:30:00Z", "utc"), b: formatLocalTime("2026-03-29T01:30:00Z", "utc")}));',
            tz="Europe/Tallinn",
        )
        # 00:30 UTC = 02:30 EET (before the spring-forward at 03:00 EET),
        # 01:30 UTC = 04:30 EEST (after) -- Date must not invent a non-existent
        # 03:xx wall-clock hour.
        assert out["a"] == "2026-03-29 02:30", out
        assert out["b"] == "2026-03-29 04:30", out
