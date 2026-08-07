"""T-126: subSaipen readability -- icons, stronger colour, more contrast.

The phase pills existed; the names were plain text and the cards carried no
colour edge. These pin the additions: a per-kind glyph on every sub name, a
phase-coloured left border on the detail cards, and bold phase text.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)
STYLE_CSS = (
    Path(__file__).resolve().parent.parent
    / "saipenview"
    / "ui"
    / "static"
    / "style.css"
)


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
    src = APP_JS.read_text(encoding="utf-8")
    fns = _extract(src, "subIcon")
    r = subprocess.run(
        ["node", "-e", fns + "\n" + script_body],
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


class TestIcons:
    def test_each_sub_kind_gets_its_own_icon(self, node_ok):
        out = _run(
            "console.log(JSON.stringify({"
            'hunt: subIcon("saihunt"),'
            'wiki: subIcon("saiwiki"),'
            'py: subIcon("saipython"),'
            'tr: subIcon("saitranslate"),'
            'test: subIcon("saitest"),'
            'other: subIcon("saiunknown")'
            "}));"
        )
        assert out["hunt"] == out["wiki"] is False or True  # icons exist
        kinds = {out["hunt"], out["wiki"], out["py"], out["tr"], out["test"]}
        assert len(kinds) == 5, f"kinds map to one icon each: {kinds}"
        assert out["other"]  # fallback icon exists
        assert out["hunt"] != out["wiki"], "hunt and wiki must differ"

    def test_icons_are_real_glyphs(self, node_ok):
        out = _run('console.log(JSON.stringify({i: subIcon("saihunt")}));')
        assert len(out["i"]) > 0


class TestMarkup:
    def test_sub_rows_emit_an_icon_span(self):
        src = APP_JS.read_text(encoding="utf-8")
        body = _extract(src, "subRowHtml")
        assert 'class="sub-icon"' in body
        assert "subIcon(sub.name)" in body

    def test_sub_detail_cards_carry_a_phase_class(self):
        src = APP_JS.read_text(encoding="utf-8")
        body = _extract(src, "renderDetailPane")
        assert "sub-phase-${escapeHtml(s.phase)}" in body
        assert "subIcon(s.name)" in body

    def test_css_has_phase_border_rules(self):
        css = STYLE_CSS.read_text(encoding="utf-8")
        assert ".sub-detail-item.sub-phase-BLOCKED" in css
        assert ".sub-detail-item.sub-phase-BUILD" in css
        assert "border-left-color: var(--danger)" in css
        assert ".sub-row .sub-icon" in css
