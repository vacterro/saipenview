"""T-127: the unrecorded-external-change prompt is wired.

Source-level contract: a watcher event for a root SAIPENVIEW did not just
write raises the persistent "Record manual work" bar; self-writes are marked
so the prompt never re-appears for the app's own actions.
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


def test_unrecorded_bar_and_record_button_exist():
    src = APP_JS.read_text(encoding="utf-8")
    assert 'id="unrecordedBar"' in src
    assert 'id="recordManualWorkBtn"' in src
    assert "agent.unrecorded" in src


def test_self_writes_are_marked_and_consumed():
    src = APP_JS.read_text(encoding="utf-8")
    assert "const selfWriteRoots = new Set();" in src
    assert "function markSelfWrite(root)" in src
    # the watcher handler consumes a self-write instead of raising the prompt
    body = src[src.index("window.onSaipenFileChanged =") : src.index("function poll()")]
    assert "selfWriteRoots.has(root)" in body
    assert "selfWriteRoots.delete(root)" in body
    assert "showUnrecordedChange(root)" in body


def test_record_button_calls_the_backend():
    src = APP_JS.read_text(encoding="utf-8")
    body = src[src.index('getElementById("recordManualWorkBtn")') :]
    assert "api.record_manual_work(detail.root, desc.trim())" in body
    assert 'prompt("Describe what you changed manually:")' in body
    assert "unrecordedChangeRoot = null" in body


def test_self_write_sites_mark_the_root():
    src = APP_JS.read_text(encoding="utf-8")
    assert "markSelfWrite(detail.root);" in src  # ticket toggles + reorder
    assert "markSelfWrite(root);" in src  # human note + record
