"""T-127/T-190: the unrecorded-external-change prompt is wired.

Source-level contract: a watcher event whose origin is NOT "self" raises the
persistent "Record manual work" bar; origin attribution moved BACKEND-side in
T-190 -- the frontend no longer guesses which root it wrote (the old
selfWriteRoots Set was an unsafe causal model), it trusts the origin the Api
pushed.
"""

from __future__ import annotations

from pathlib import Path

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)
INDEX_HTML = (
    Path(__file__).resolve().parent.parent
    / "saipenview"
    / "ui"
    / "static"
    / "index.html"
)
STYLE_CSS = (
    Path(__file__).resolve().parent.parent
    / "saipenview"
    / "ui"
    / "static"
    / "style.css"
)


def test_unrecorded_bar_and_record_button_exist():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'id="unrecordedBar"' in src
    assert 'id="recordManualWorkBtn"' in src
    assert "agent.unrecorded" in src


def test_on_saipen_file_changed_takes_origin_and_prompts_only_on_external():
    src = APP_JS.read_text(encoding="utf-8")
    assert "window.onSaipenFileChanged = function(root, fileName, origin)" in src
    body = src[src.index("window.onSaipenFileChanged =") : src.index("function poll()")]
    assert 'origin !== "self"' in body
    assert "showUnrecordedChange(root)" in body
    # The unsafe frontend causal model is gone: no mark-before-write helper,
    # no single global debounce swallowing events across projects.
    assert "markSelfWrite" not in src
    assert "fileChangeDebounce" not in src


def test_record_button_calls_the_backend():
    src = APP_JS.read_text(encoding="utf-8")
    body = src[src.index('getElementById("recordManualWorkBtn")') :]
    assert (
        "record_manual_work(intent.root, desc.trim(), opId, intent.ack_tokens)" in body
    )
    assert 'prompt("Describe what you changed manually:")' in body
    assert "unrecordedChangeRoot = null" in body
    assert "pendingRecordOpId" in src
    assert "manualWorkIntents" in src


def test_no_frontend_self_write_calls_remain():
    src = APP_JS.read_text(encoding="utf-8")
    assert "markSelfWrite(" not in src


def test_unrecorded_bar_is_bounded_not_inline_chips():
    """T-191: the bar must never grow to fill the pane.

    The pre-fix bar rendered one chip per pending path in the SAME wrapping
    flex row as its own message, with no height limit anywhere -- a sub-agent
    sweep touching STATE/BOARD/LOG per sub stacked the bar to full pane
    height and pushed the header, NEXT and every card off-screen. The bar is
    now a one-line summary (never wraps) with the paths in a capped,
    collapsed-then-scrollable body, and the DOM is capped so a runaway
    registry cannot build thousands of nodes.
    """
    src = APP_JS.read_text(encoding="utf-8")
    # The list the bar draws is capped.
    assert "UNRECORDED_CHIP_CAP" in src
    assert "_pending.slice(0, UNRECORDED_CHIP_CAP)" in src
    assert "_rest" in src  # "+N more" chip for whatever exceeds the cap
    # The summary row and the paths live in SEPARATE containers; the paths are
    # hidden until the user unfolds them.
    assert 'class="unrecorded-summary"' in src
    assert 'class="unrecorded-items"' in src
    assert 'id="unrecordedToggleBtn"' in src
    assert '_unrecordedExpandedRoot' in src
    # One render per burst: a sweep must not rebuild the whole pane per event.
    assert "UNRECORDED_RENDER_DEBOUNCE_MS" in src
    assert "clearTimeout(timer)" in src


def test_unrecorded_bar_css_bounds_the_list():
    css = STYLE_CSS.read_text(encoding="utf-8")
    # The list body is capped and scrolls; the summary row never wraps.
    assert ".unrecorded-bar.expanded .unrecorded-items" in css
    assert "max-height: 76px" in css
    assert "overflow-y: auto" in css
    assert ".unrecorded-text" in css
    assert "white-space: nowrap" in css
