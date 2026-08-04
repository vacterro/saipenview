"""Guards the fluid-layout layer in `style.css` (T-155).

Two reasons this is a file test rather than "we looked at it once":

1. `style.css` has been silently rewritten from outside this repo twice
   (T-096, T-142 -- Wintage's installer recoloured from a stale snapshot and
   pasted the result back). Both times the damage was invisible in review
   because the file still parsed and still looked like itself. A test that
   names the rules the layout depends on turns that class of accident into a
   red run instead of a bug report weeks later.
2. The fluid layer is easy to "tidy" away. `clamp()` and `cqi` read like
   over-engineering next to a plain `160px`, and a container query with no
   media query in sight reads like a mistake. The comments explain why; this
   test makes reverting it cost something.

Deliberately NOT a snapshot test of the whole file -- that would go red on
every unrelated edit and get deleted within a week. It asserts only the
handful of declarations the responsive behaviour cannot survive without.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static"
CSS_PATH = STATIC / "style.css"


@pytest.fixture(scope="module")
def css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_body_is_the_query_container(css: str) -> None:
    """Every breakpoint in the file is a container query on `body`.

    Media queries are wrong here and the reason is not stylistic: the app runs
    at a user-set `zoom_level` applied as `body.style.zoom`, so the window's
    pixel width is not the width the layout receives. If this declaration goes,
    every `@container` rule below silently stops matching -- no error, no
    warning, just a layout frozen at its widest band.
    """
    assert "container-type: inline-size" in css
    assert "container-name: app" in css


def test_responsive_bands_are_present(css: str) -> None:
    bands = re.findall(r"@container app \(([^)]+)\)", css)
    assert "min-width: 1100px" in bands, "wide band (cards side by side) missing"
    assert "max-width: 620px" in bands, "narrow band missing"
    assert "max-width: 420px" in bands, "very-narrow band missing"


@pytest.mark.parametrize(
    "token",
    ["--sidebarW", "--fieldLabelW", "--searchW", "--excludeW", "--filterW",
     "--subNameW", "--subIndentW"],
)
def test_fluid_metric_tokens_are_declared(css: str, token: str) -> None:
    assert re.search(rf"^\s*{re.escape(token)}\s*:", css, re.MULTILINE), (
        f"{token} is used by the layout but no longer declared"
    )


def test_fluid_metrics_are_clamped_not_fixed(css: str) -> None:
    """Each metric needs a floor AND a ceiling.

    An unbounded fluid value is its own bug: a sidebar that is a bare
    percentage vanishes on a narrow window and swallows the pane on a wide one.
    `--subIndentW` is exempt -- it deliberately aliases `--fieldLabelW` so the
    sub-agent rows line up under the fields above them.
    """
    for token in ["--sidebarW", "--fieldLabelW", "--searchW", "--excludeW",
                  "--filterW", "--subNameW"]:
        match = re.search(rf"^\s*{re.escape(token)}\s*:\s*([^;]+);", css, re.MULTILINE)
        assert match, f"{token} not declared"
        assert match.group(1).strip().startswith("clamp("), (
            f"{token} is {match.group(1).strip()!r}, which has no floor or no ceiling"
        )


def test_shell_geometry_reads_the_tokens(css: str) -> None:
    """The tokens are pointless if the rules that size the shell ignore them."""
    for selector, token in [
        (r"\.project-list \{[^}]*", "var(--sidebarW)"),
        (r"\.detail-field \.label \{[^}]*", "var(--fieldLabelW)"),
        (r"\.search-input \{[^}]*", "var(--searchW)"),
    ]:
        block = re.search(selector, css)
        assert block, f"rule {selector!r} is gone"
        assert token in block.group(0), f"{selector!r} no longer uses {token}"


def test_no_viewport_units_left_in_the_shell(css: str) -> None:
    """`vw`/`vh` resolve against the UNSCALED viewport under `body { zoom }`.

    At 125% a `90vw` box renders at 112.5% of the window. The shell is free of
    them; the overlays are not yet (T-156 owns those), so this checks the shell
    rules by name rather than the whole file, and will tighten to the whole
    file once the overlays are converted.
    """
    shell_selectors = [
        r"\.project-list \{[^}]*\}",
        r"\.detail-pane \{[^}]*\}",
        r"\.detail-content \{[^}]*\}",
        r"\.toolbar \{[^}]*\}",
        r"\.main-container \{[^}]*\}",
    ]
    for pattern in shell_selectors:
        block = re.search(pattern, css)
        assert block, f"rule {pattern!r} is gone"
        assert not re.search(r"\d(vw|vh)\b", block.group(0)), (
            f"{pattern!r} uses a viewport unit, which is wrong under body zoom"
        )


def test_detail_content_is_a_class_not_an_inline_style() -> None:
    """`renderDetailPane` must not re-inline the wrapper's layout.

    It used to write `style="display:flex; flex-direction:column"` on
    `#detailPaneContent`, and an inline declaration outranks the wide band that
    turns that column into a grid -- so the grid would never apply and nothing
    would look broken enough to notice.
    """
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    match = re.search(r'id="detailPaneContent"[^>]*', app_js)
    assert match, "#detailPaneContent is no longer created by app.js"
    assert 'class="detail-content"' in match.group(0)
    assert "flex-direction" not in match.group(0), (
        "layout is inline again; the responsive bands cannot override it"
    )
