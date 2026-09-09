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
    assert "max-width: 620px" in bands, "narrow band missing"
    assert "max-width: 420px" in bands, "very-narrow band missing"


def test_the_wide_band_asks_the_pane_not_the_body(css: str) -> None:
    """Multi-card layout is a PANE decision, and the body cannot answer it.

    The wide band used to be `@container app (min-width: 1100px)`, so `body`
    decided whether the detail cards went side by side. A 1100px window carries
    a sidebar, which leaves roughly 750px of pane -- less than the two 360px
    columns plus gap the band had just declared there was room for. The columns
    were squeezed below their own stated minimum at exactly the width the band
    turned on.
    """
    bands = re.findall(r"@container pane \(([^)]+)\)", css)
    assert any(b.startswith("min-width:") for b in bands), (
        "no pane band turns on the multi-card layout; a body band cannot know "
        "how wide the pane actually is"
    )


@pytest.mark.parametrize(
    "token",
    [
        "--sidebarW",
        "--fieldLabelW",
        "--searchW",
        "--excludeW",
        "--filterW",
        "--subNameW",
        "--subIndentW",
    ],
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
    for token in [
        "--sidebarW",
        "--fieldLabelW",
        "--searchW",
        "--excludeW",
        "--filterW",
        "--subNameW",
    ]:
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


def _without_comments(source: str) -> str:
    """The comments quote the removed `90vw`/`92vh` on purpose; skip them."""
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


def test_no_viewport_units_anywhere(css: str) -> None:
    """`vw`/`vh` resolve against the UNSCALED viewport under `body { zoom }`.

    At 125% a `90vw` box renders at 112.5% of the window, and `max-height:
    92vh` let the Settings dialog render 176px taller than the window at
    1280x720/150% -- pinning its own Save and Close buttons off-screen. There
    is no correct use of either unit in this file while `zoom_level` is applied
    the way it is, so the rule is the whole file, not a list of selectors.
    """
    offenders = []
    for match in re.finditer(r"[\d.]+(vw|vh|vmin|vmax)\b", _without_comments(css)):
        line = css[: match.start()].count("\n") + 1
        offenders.append(f"style.css:{line}: {match.group(0)}")
    assert not offenders, (
        "viewport units are wrong under body zoom; use cqi or a percentage:\n"
        + "\n".join(offenders)
    )


def test_settings_is_a_grid_that_finds_its_own_column_count(css: str) -> None:
    """One `auto-fit` rule, not a list of breakpoints per field count.

    Eighteen fields in the old fixed 320px column meant every label wrapped to
    two lines and the dialog scrolled -- on a 1920px screen, with the space for
    three columns sitting empty either side of it.
    """
    block = re.search(r"#settingsModal \.modal-body \{[^}]*\}", css)
    assert block, "the Settings grid rule is gone"
    assert "grid" in block.group(0)
    assert "auto-fit" in block.group(0), (
        "a fixed column count goes wrong at some width; auto-fit cannot"
    )


# --- Dead vertical space: the layout must not RESERVE room it has no use for --
#
# Every case below is the same failure with a different mechanism: a box states
# a size independent of its content, and at some window size the difference
# becomes a wall of nothing. They are separate tests because the mechanisms are
# separate and a fix for one says nothing about the others.


def test_detail_cards_flow_and_are_not_a_row_grid(css: str) -> None:
    """A grid ROW is as tall as its tallest item. That is the whole bug.

    `repeat(auto-fit, minmax(360px, 1fr))` with `align-self: start` on the cards
    put Conformance (2 rows) next to Tickets (20 rows) and left a dead column
    the height of the difference. `align-self: start` is what made it visible --
    without it the short card stretches, which is ugly but not empty -- so the
    pair is what this forbids. Multicol has no row concept: the only vertical
    space between two cards is the margin.
    """
    band = re.search(
        r"@container pane \(min-width:[^)]*\)\s*\{(.*?\n\})\s*\n", css, re.DOTALL
    )
    assert band, "the pane band that lays out the cards is gone"
    rule = band.group(1)
    assert "column-width" in rule, (
        "the wide layout is not a multi-column flow; if it went back to a grid, "
        "row height is back to being the tallest card in the row"
    )
    assert "grid-template-columns" not in rule, (
        "a row grid is back -- a short card beside a tall one leaves a hole the "
        "height of the difference"
    )
    assert "align-self" not in rule, (
        "align-self:start is what turns unequal card heights into visible dead "
        "space; nothing in a flow layout needs it"
    )
    assert "break-inside: avoid" in rule, (
        "without this a card fragments mid-body across a column boundary"
    )


def test_full_width_rows_span_every_column(css: str) -> None:
    """Header, NEXT and the unrecorded warning are not cards.

    In a multicol flow an unspanned block becomes one more fragment in the
    first column, so the project name would end up beside the cards instead of
    above them, and the change warning would be as easy to miss as a footnote.
    """
    band = re.search(
        r"@container pane \(min-width:[^)]*\)\s*\{(.*?\n\})\s*\n", css, re.DOTALL
    )
    assert band, "the pane band is gone"
    rule = band.group(1)
    for selector in (".detail-header", ".next-action-banner", ".unrecorded-bar"):
        assert selector in rule, f"{selector} no longer spans the columns"
    assert "column-span: all" in rule


@pytest.mark.parametrize(
    "selector",
    [r"\.modal-box-lg", r"\.modal-box-xl", r"\.agent-output-panel"],
)
def test_content_boxes_cap_their_height_and_never_fix_it(css: str, selector: str) -> None:
    """`height` RESERVES; `max-height` CAPS. Only one of them is honest.

    `.modal-box-lg { height: 80% }` meant a clean `git status` opened a dialog
    80% of the window tall to say "no changes" -- one line of text over a wall
    of empty panel, worse the larger the window. `.agent-output-panel` reserved
    a flat 150px for a console with nothing in it. A cap gives the long case
    exactly the same behaviour and the short case an honest one.
    """
    blocks = re.findall(selector + r"[^{]*\{[^}]*\}", css)
    assert blocks, f"{selector} rule is gone"
    for rule in blocks:
        assert not re.search(r"(?<!max-)(?<!min-)height:\s*[\d.]+(%|px|lh|em|ch)", rule), (
            f"{selector} states a fixed height, so it reserves that space "
            f"whatever the content is: {rule.strip()}"
        )


@pytest.mark.parametrize(
    "selector",
    ["#fileViewerContent", "#diffViewerContent", "#fleetDashboardContent",
     r"\.agent-output-panel"],
)
def test_capped_scroll_regions_keep_a_floor(css: str, selector: str) -> None:
    """The other half of removing a fixed height.

    These regions are `flex: 1` inside a column that is now content-sized, so
    with two lines of content they would collapse to two lines -- a scroll box
    thinner than its own scrollbar. The floor is stated in `lh` because what
    matters is how many LINES stay readable, not how many pixels.
    """
    blocks = re.findall(re.escape(selector).replace(r"\\", "") + r"[^{]*\{[^}]*\}", css)
    blocks = [b for b in blocks if "min-height" in b] or blocks
    assert blocks, f"{selector} has no rule at all"
    assert any(re.search(r"min-height:\s*\d+lh", b) for b in blocks), (
        f"{selector} can collapse to nothing once its parent stopped "
        f"reserving a fixed height"
    )


def test_modal_geometry_is_not_inline_in_the_markup() -> None:
    """Three dialogs carried the same inline `max-width/width/height` triple.

    Inline geometry outranks every rule in the stylesheet, so the narrow bands
    could not reach those dialogs at all.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'class="modal-box[^"]*"[^>]*style="[^"]*width', html), (
        "a modal box is sizing itself inline again"
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


def test_the_detail_pane_is_its_own_query_container(css: str) -> None:
    """Pane-internal rows must ask the PANE how much room there is.

    `@container app` asks `body`. A 1920px window routinely holds a 400px
    detail pane, so every app-band rule reads "plenty of room" while the pane
    is starving -- which is how a conformance row ended up rendering its
    message one character per line on a maximised window.
    """
    block = re.search(r"\.detail-pane \{[^}]*\}", css)
    assert block, ".detail-pane rule is gone"
    assert "container-type: inline-size" in block.group(0)
    assert "container-name: pane" in block.group(0)
    assert re.search(r"@container pane \(", css), "no pane band uses the container"


@pytest.mark.parametrize(
    "selector",
    [r"\.conf-where", r"\.conf-cite", r"\.conf-rule", r"\.error-time"],
)
def test_row_metadata_can_always_shrink(css: str, selector: str) -> None:
    """The squeezed-message bug lives in the sibling, not in the message.

    `.conf-where` holds a path and was `flex: 0 0 auto`, so it took its full
    max-content width; the message was the only flexible thing left and
    absorbed the entire shortfall. Measured on the pre-fix stylesheet at a
    291px pane: `.conf-msg` computed to **0px wide and 76 lines for 79
    characters** -- exactly one letter per line -- while `.conf-where` sat at
    268px. `min-width: 0` on the message could not help; it was already
    willing to shrink, and shrinking is what killed it.
    """
    block = re.search(selector + r" \{[^}]*\}", css)
    assert block, f"{selector} rule is gone"
    rule = block.group(0)
    assert not re.search(r"flex:\s*0\s+0\s", rule), (
        f"{selector} refuses to shrink; whatever grows beside it eats the loss"
    )
    assert not re.search(r"flex-shrink:\s*0", rule), f"{selector} cannot shrink"


@pytest.mark.parametrize("selector", [r"\.conf-msg", r"\.error-message"])
def test_message_columns_have_a_floor_in_characters(css: str, selector: str) -> None:
    """A floor in `ch` is the only basis that means anything for text.

    Below roughly twelve characters a row stops being a message and becomes a
    column of letters, so the floor is stated in the unit the failure is
    measured in.
    """
    block = re.search(selector + r" \{[^}]*\}", css)
    assert block, f"{selector} rule is gone"
    assert re.search(r"min-width:\s*\d+ch", block.group(0)), (
        f"{selector} has no character floor and can be squeezed to nothing"
    )
