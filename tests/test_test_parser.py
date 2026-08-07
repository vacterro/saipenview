r"""T-163: test-result parser hygiene.

The shipped app.js carried literal 0x08 control bytes (BACKSPACE) around
`(\d+) failed` and `(\d+) passed`. A raw 0x08 inside a regex literal is a
literal backspace character, NOT the `\b` word boundary the author meant --
so a real line reading `1 failed` never matched and those two branches were
dead code. Only the combined `passed.*failed` branch ever worked.

Two layers of protection:

- a source-hygiene test that fails on ANY C0 control byte in app.js except
  TAB/LF/CR -- this is the check that would have caught the original
  corruption at commit time;
- behavior tests that EXECUTE the real `parseTestLine` under node, because
  `node --check` proves syntax and nothing about what a regex matches.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


def _extract_function(source: str, name: str) -> str:
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


HARNESS = """\
const window = {{ agentTestState: {{}} }};
{fn}
function st(root, line) {{
  parseTestLine(root, line);
  return (window.agentTestState[root] || {{}}).status;
}}
const out = {{}};
out.p1 = st("r1", "1 passed");
out.p15 = st("r2", "15 passed");
out.f1 = st("r3", "1 failed");
out.mix = st("r4", "14 passed, 2 failed");
out.failed_file = st("r5", "FAILED tests/test_x.py");
out.bypassed = st("r6", "bypassed");
st("r7", "1 failed");
out.guard = st("r7", "15 passed");
st("r8", "1 failed");
st("r8", "==== test session starts ====");
out.new_run = st("r8", "15 passed");
console.log(JSON.stringify(out));
"""


def _run_parser() -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    fn = _extract_function(source, "parseTestLine")
    harness = HARNESS.format(fn=fn)
    r = subprocess.run(
        ["node", "-e", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(f"node harness failed: {r.stderr}")
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def parsed() -> dict:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("node not available")
    return _run_parser()


class TestSourceHygiene:
    def test_no_c0_control_bytes_in_app_js(self) -> None:
        """Only TAB/LF/CR may appear below 0x20 in app.js."""
        bad = sorted(
            {b for b in APP_JS.read_bytes() if b < 0x20 and b not in (0x09, 0x0A, 0x0D)}
        )
        assert not bad, (
            f"app.js carries C0 control bytes: {[hex(b) for b in bad]} -- "
            "raw 0x08 in a regex literal is a backspace, not \\b"
        )


class TestParserBehavior:
    def test_single_passed_is_pass(self, parsed) -> None:
        assert parsed["p1"] == "pass"

    def test_plural_passed_is_pass(self, parsed) -> None:
        assert parsed["p15"] == "pass"

    def test_single_failed_is_fail(self, parsed) -> None:
        assert parsed["f1"] == "fail"

    def test_mixed_counts_fail_when_any_failed(self, parsed) -> None:
        assert parsed["mix"] == "fail"

    def test_pytest_failed_summary_line_is_fail(self, parsed) -> None:
        assert parsed["failed_file"] == "fail"

    def test_word_bypassed_is_not_pass(self, parsed) -> None:
        assert parsed["bypassed"] == "none"

    def test_earlier_fail_not_overwritten_by_later_pass(self, parsed) -> None:
        assert parsed["guard"] == "fail"

    def test_new_run_resets_an_earlier_fail(self, parsed) -> None:
        assert parsed["new_run"] == "pass"
