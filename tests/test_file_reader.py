r"""T-125: LOG/STATE/BOARD reader formatting.

The reader-mode renderers existed but threw the ticket field tail away
(`| verify: ... | blocker: ...`) and rendered STATE frontmatter as one
generic list. These run the REAL renderers under node against the three
protocol documents, asserting the formatted structure and the source/reader
toggle contract.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)

PREAMBLE = """\
function escapeHtml(x) {{ return String(x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }}
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


def _run(script_body: str) -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    fns = "\n".join(
        _extract(source, n)
        for n in (
            "renderStateAsHtml",
            "renderBoardAsHtml",
            "renderLogAsHtml",
            "renderAsReader",
        )
    )
    r = subprocess.run(
        ["node", "-e", PREAMBLE + fns + "\n" + script_body],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(f"node harness failed: {r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


STATE = "---\nphase: BUILD\ntask: T-001\nnext_action: PHASE BUILD T-001\nblocker: none\nagent: opencode\n---\n"
BOARD = (
    "# BOARD\n"
    "## DOING\n"
    "- [/] T-002 working | owner: opencode\n"
    "## TODO\n"
    "- [ ] T-001 open | verify: node --check clean\n"
    "## DONE\n"
    "- [x] T-000 done | verify: it ran\n"
    "## BLOCKED\n"
    "- [ ] T-005 stuck | blocker: waiting on upstream\n"
)
LOG = "# LOG\n- 07.08.26 11:00 [E-1] RUN: hello\n- 07.08.26 11:01 [E-2] [parent: E-1] DEC: bye\n"


@pytest.fixture(scope="module")
def node_ok() -> None:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("node not available")


class TestState:
    def test_frontmatter_rows_are_rendered(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderStateAsHtml("
            + json.dumps(STATE)
            + ")}));"
        )
        html = out["r"]
        assert "reader-fm-row" in html
        assert "reader-fm-key" in html
        assert "phase" in html and "BUILD" in html

    def test_known_fields_are_highlighted(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderStateAsHtml("
            + json.dumps(STATE)
            + ")}));"
        )
        html = out["r"]
        assert "reader-fm-key-known" in html

    def test_body_is_escaped_raw(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderStateAsHtml("
            + json.dumps("---\nphase: DONE\n---\nnotes here")
            + ")}));"
        )
        html = out["r"]
        assert "reader-raw" in html


class TestBoard:
    def test_sections_and_tickets_rendered(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderBoardAsHtml("
            + json.dumps(BOARD)
            + ")}));"
        )
        html = out["r"]
        assert "reader-section-title" in html
        assert "T-002" in html
        assert "reader-doing" in html

    def test_done_gets_struck_class(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderBoardAsHtml("
            + json.dumps(BOARD)
            + ")}));"
        )
        assert "reader-done" in out["r"]

    def test_ticket_fields_are_kept_not_stripped(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderBoardAsHtml("
            + json.dumps(BOARD)
            + ")}));"
        )
        html = out["r"]
        assert "reader-ticket-field" in html
        assert "verify" in html
        assert "waiting on upstream" in html
        # the field must not be part of the ticket description
        assert "T-005 stuck" in html

    def test_empty_section_renders_empty_note(self, node_ok):
        out = _run(
            'console.log(JSON.stringify({r: renderBoardAsHtml("# B\\n## TODO\\n\\n## DONE\\n")}));'
        )
        assert "reader-empty" in out["r"]


class TestLog:
    def test_lines_rendered_with_date_and_event(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({r: renderLogAsHtml("
            + json.dumps(LOG)
            + ")}));"
        )
        html = out["r"]
        assert "reader-log-line" in html
        assert "reader-log-date" in html
        assert "reader-log-eid" in html
        assert "E-1" in html


class TestDispatch:
    def test_reader_dispatch_by_filename(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({"
            's: renderAsReader("STATE.md", ' + json.dumps(STATE) + "),"
            'b: renderAsReader("BOARD.md", ' + json.dumps(BOARD) + "),"
            'l: renderAsReader("LOG.md", ' + json.dumps(LOG) + ")"
            "}));"
        )
        assert "reader-fm-row" in out["s"]
        assert "reader-section-title" in out["b"]
        assert "reader-log-line" in out["l"]
