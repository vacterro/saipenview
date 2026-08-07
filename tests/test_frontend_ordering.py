"""T-122: the Edit button must survive a failure in the optional Agent Panel.

`renderDetailPane` used to call `renderAgentPanel(...)` in the middle of the
function -- after building the HTML but BEFORE binding the core controls
(Edit/Folder/Terminal/Code/STATE/BOARD/LOG/Pin/Hide). If the agent panel
threw, the whole tail of bindings silently never ran: the Edit button was
drawn but had no listener, so clicking it did nothing. These source-order
tests lock the structural boundary the fix enforces.
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


def test_edit_binds_before_the_optional_agent_panel():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    edit_pos = body.index("editStateBtn")
    agent_pos = body.index("renderAgentPanel")
    assert edit_pos < agent_pos, (
        "the Agent Panel runs before the Edit button is bound -- an agent "
        "panel exception still leaves Edit dead"
    )


def test_every_core_control_binds_before_the_agent_panel():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    agent_pos = body.index("renderAgentPanel")
    for control in (
        "openFolderBtn",
        "openTerminalBtn",
        "openEditorBtn",
        "togglePinDetailBtn",
        "editStateBtn",
        "cancelStateBtn",
        "saveStateBtn",
        "hide_project",
    ):
        pos = body.index(control)
        assert pos < agent_pos, (
            f"{control} binds after renderAgentPanel -- an exception there "
            "still kills it"
        )


def test_agent_panel_call_is_inside_an_error_boundary():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "renderDetailPane")
    # The call must be wrapped: try { renderAgentPanel(...) } catch (... reportRenderError ...)
    call_pos = body.index("renderAgentPanel(detail.root")
    try_pos = body.rfind("try {", 0, call_pos)
    catch_pos = body.find("catch", call_pos)
    report_pos = body.find("reportRenderError", call_pos)
    assert try_pos != -1, "no try { before the renderAgentPanel call"
    assert try_pos < call_pos < catch_pos < report_pos, (
        "renderAgentPanel is not inside a try/catch that reports the failure"
    )


def test_frontend_error_capture_is_registered():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'window.addEventListener("error"' in src
    assert 'window.addEventListener("unhandledrejection"' in src
    assert "function reportRenderError" in src
    assert "renderErrorRegion" in src


def test_error_region_exists_in_the_page():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="renderErrorRegion"' in html
