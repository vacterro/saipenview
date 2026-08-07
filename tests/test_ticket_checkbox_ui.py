"""T-174: the checkbox UI is present and wired (source-level guard).

The real WebView2 probe proves the click; this pins the markup contract so a
refactor cannot silently drop the checkboxes or their handlers.
"""

from __future__ import annotations

from pathlib import Path

APP_JS = (
    Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"
)


def _function_body(source: str, name: str) -> str:
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


def test_ticket_rows_render_a_real_checkbox():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    assert 'class="ticket-chk"' in body, "the ticket checkbox markup is gone"
    # the cycle map: TODO -> start, DOING -> done, DONE -> reopen, BLOCKED -> unblock
    for action in ("start", "done", "reopen", "unblock"):
        assert f'"{action}"' in body and "actionFor" in body, (
            f"checkbox action {action} missing"
        )
    assert "actionFor[title]" in body
    assert 'data-ind="1"' in body, "DOING rows no longer render as indeterminate"


def test_block_button_is_offered_and_wired():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    assert "ticket-block-btn" in body, "the Block affordance is gone"
    assert 'data-action="block"' in body or '"block"' in body
    assert "prompt(" in body, "the Block flow no longer asks for a blocker reason"


def test_handlers_bind_checkbox_change_and_block_click():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    assert "querySelectorAll('.ticket-chk')" in body
    assert "addEventListener('change'" in body
    assert "querySelectorAll('.ticket-block-btn')" in body
    assert "toggle_ticket_status(detail.root, tid, action, reason || null)" in body


def test_style_css_covers_the_new_controls():
    css = (
        Path(__file__).resolve().parent.parent
        / "saipenview"
        / "ui"
        / "static"
        / "style.css"
    ).read_text(encoding="utf-8")
    assert ".ticket-chk" in css
    assert ".ticket-blocker" in css


def test_ticket_rows_are_draggable_and_wired():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    assert 'draggable="true"' in body, "ticket rows are not draggable"
    assert 'data-section="${escapeHtml(title)}"' in body, (
        "ticket lists lack a section key"
    )
    assert "dragstart" in body and "dragover" in body and "drop" in body
    assert "reorder_ticket(detail.root, dragState.tid, dragState.section" in body
    # same-section guard: a cross-section drop must not fire the reorder
    assert (
        "dragState.section !== dragState.section" in body
        or "!== dragState.section" in body
    )
