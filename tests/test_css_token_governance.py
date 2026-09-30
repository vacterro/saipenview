"""style.css must carry no colour literal outside the :root token block.

The one survivor is the near-white at `.error-badge`, which the stylesheet
documents in place: it is white text on the `danger` fill, a filled chip
rather than text on the surface, and the near-white is the signal. Everything
else has to be a theme token, or a theme switch cannot reach it.

This is a measurement, not a string search: comments are stripped first (with
newlines preserved, so line numbers still mean something), because the file
documents several retired hexes in fix comments and a naive grep would count
documentation as drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "saipenview" / "ui" / "static" / "style.css"
APP_JS = ROOT / "saipenview" / "ui" / "static" / "app.js"

HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
ROOT_BLOCK = re.compile(r":root\s*\{.*?\n\}", re.DOTALL)

#: The sanctioned survivor, and the one selector allowed to carry it.
ALLOWED = {"#fff": ".error-badge"}
HOVER_IDIOM = re.compile(
    r"^\.custom-cmd-btn:hover\s*\{[^}]*background:\s*var\(--surfaceSoft\);"
    r"[^}]*color:\s*var\(--textPrimary\);[^}]*\}$"
)


def strip_css_comments(text: str) -> str:
    """Comment-free CSS, with comments blanked so line numbers still hold.

    Blanking must preserve newlines: one long run of spaces would fold a
    multi-line comment onto a single line and shift every line number after it,
    which is exactly the drift a measurement must not introduce.
    """
    return re.sub(
        r"/\*.*?\*/",
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)),
        text,
        flags=re.DOTALL,
    )


@pytest.fixture(scope="module")
def live() -> str:
    return strip_css_comments(CSS.read_text(encoding="utf-8"))


def _line_offsets(text: str) -> list[int]:
    starts, pos = [], 0
    for line in text.split("\n"):
        starts.append(pos)
        pos += len(line) + 1
    return starts


def _literals_outside_root(live: str) -> dict[str, list[int]]:
    block = ROOT_BLOCK.search(live)
    assert block is not None, "style.css lost its :root token block"
    starts = _line_offsets(live)
    found: dict[str, list[int]] = {}
    for match in HEX.finditer(live):
        if block.start() <= match.start() < block.end():
            continue
        line = max(i for i, start in enumerate(starts, 1) if start <= match.start())
        found.setdefault(match.group(0).lower(), []).append(line)
    return found


def test_root_token_block_exists(live: str) -> None:
    assert ROOT_BLOCK.search(live) is not None


def test_no_colour_literal_outside_the_token_block(live: str) -> None:
    found = _literals_outside_root(live)
    assert set(found) == set(ALLOWED), f"ungoverned literals: {sorted(set(found) - set(ALLOWED))}"


def test_the_one_survivor_sits_at_error_badge(live: str) -> None:
    lines = live.split("\n")
    for literal, selector in ALLOWED.items():
        for line_no in _literals_outside_root(live).get(literal, []):
            assert selector in lines[line_no - 1], f"{literal} at line {line_no} is not {selector}"


def test_custom_cmd_hover_uses_the_token_fill_idiom(live: str) -> None:
    hover = next(
        (ln.strip() for ln in live.split("\n") if ln.strip().startswith(".custom-cmd-btn:hover")),
        "",
    )
    assert HOVER_IDIOM.match(hover), hover


def test_custom_cmd_hover_carries_no_raw_hex(live: str) -> None:
    hover = next(
        (ln.strip() for ln in live.split("\n") if ln.strip().startswith(".custom-cmd-btn:hover")),
        "",
    )
    assert not HEX.search(hover), hover


def test_the_token_it_uses_is_required_by_every_palette() -> None:
    from saipenview import themes

    assert "surfaceSoft" in themes.REQUIRED_TOKENS
    slugs = [t["slug"] for t in themes.list_themes()]
    assert slugs, "no palette loaded"
    missing = [s for s in slugs if "surfaceSoft" not in (themes.load_theme(s) or {})]
    assert not missing, f"palettes without surfaceSoft: {missing}"


def test_app_js_carries_no_named_ui006_hex() -> None:
    app = APP_JS.read_text(encoding="utf-8").lower()
    named = [
        h
        for h in ("#7A2020", "#4A3A10", "#4E3A18", "#2A1510", "#E08A8A", "#CC6666", "#FFDD00")
        if h.lower() in app
    ]
    assert not named, f"raw hexes in app.js: {named}"
