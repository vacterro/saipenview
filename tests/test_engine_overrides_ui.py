"""T-178: engine_overrides settings UI -- source-level contract.

The settings modal edits the per-engine override dict as JSON and saves it
through the validated API. These pin the wiring: the textarea exists, it
loads from config, and the save path parses JSON and refuses invalid input.
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


def test_settings_modal_has_the_override_editor():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="engineOverridesInput"' in html
    assert 'id="engineOverridesError"' in html


def test_open_settings_loads_the_overrides_from_config():
    src = APP_JS.read_text(encoding="utf-8")
    body = _function_body(src, "openSettings")
    assert "engineOverridesInput" in body
    assert "JSON.stringify(cfg.engine_overrides || {}, null, 2)" in body


def test_save_parses_json_and_calls_the_validated_api():
    src = APP_JS.read_text(encoding="utf-8")
    # the save handler is anonymous; find the second reference to the input
    # (the parse happens in the save handler, after the openSettings load)
    first = src.index("engineOverridesInput")
    second = src.index("engineOverridesInput", first + 1)
    body = src[second : second + 1200]
    assert "JSON.parse(ovInput.value" in body
    assert "set_engine_overrides(engineOverrides)" in src


def test_invalid_json_aborts_the_save_with_a_visible_error():
    src = APP_JS.read_text(encoding="utf-8")
    first = src.index("engineOverridesInput")
    second = src.index("engineOverridesInput", first + 1)
    body = src[second : second + 1200]
    assert "is not valid JSON" in body
    assert 'ovErr.style.display = "block"' in body
    assert "return;" in body.split("is not valid JSON")[1][:200]
