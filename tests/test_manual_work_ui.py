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
