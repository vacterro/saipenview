"""A human_note must land where an agent will actually find it.

`add_human_note` used to append to the end of STATE.md, which put the line
AFTER the frontmatter's closing `---` -- outside the block every reader
parses. `parse_frontmatter` returned None for it, while BOOT.md step 5
("human_note: set? Apply it this session, clear it, LOG the trace") looks in
exactly the place the note never reached.

So the UI's Note button wrote a message to the next agent that no agent could
ever read, and returned ok while doing it. These lock the contract: if the
call reports success, the note is readable by the frontmatter parser.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from saipenview.api import Api
from saipenview.config import DEFAULTS
from saipenview.parser import parse_frontmatter


@pytest.fixture
def api(tmp_path) -> Api:
    cfg = dict(DEFAULTS)
    cfg["pinned_roots"] = []
    cfg["hidden_roots"] = []
    cfg["scan_roots"] = None
    with (
        patch("saipenview.api.config_path"),
        patch("saipenview.api.load_config", return_value=cfg),
        patch("saipenview.api.save_config"),
        patch("saipenview.api.BackgroundScanner"),
    ):
        yield Api()


def _register(api: Api, tmp_path):
    api._config["pinned_roots"] = [str(tmp_path)]


def _project(tmp_path, tail="---\n"):
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text(
        "---\nphase: DONE\ntask: none\nupdated: 2026-08-01T00:00:00Z\n" + tail,
        encoding="utf-8",
    )
    return saipen / "STATE.md"


def _note(state_md):
    return parse_frontmatter(state_md.read_text(encoding="utf-8")).get("human_note")


def test_note_is_readable_by_the_frontmatter_parser(api, tmp_path):
    state_md = _project(tmp_path)
    _register(api, tmp_path)
    assert api.add_human_note(str(tmp_path), "PICK ME UP")["ok"] is True
    assert _note(state_md) == "PICK ME UP", (
        "the note landed somewhere parse_frontmatter cannot see it -- which is "
        "the whole bug: BOOT.md step 5 reads the frontmatter and nowhere else"
    )


def test_note_survives_a_file_that_does_not_end_on_a_line_boundary(api, tmp_path):
    # SAIPEN 7.147.0: appending to a file that stops mid-line does not add a
    # line, it EXTENDS the last one. The old "a"-mode write was exposed to
    # that; rewriting the frontmatter block is not.
    state_md = _project(tmp_path, tail="---")
    _register(api, tmp_path)
    assert api.add_human_note(str(tmp_path), "PICK ME UP")["ok"] is True
    assert _note(state_md) == "PICK ME UP"


def test_a_newline_in_the_note_cannot_forge_another_field(api, tmp_path):
    # The frontmatter is flat, one key per line, so an embedded newline would
    # otherwise let a note write a second key -- here, silently reassigning the
    # project's phase.
    state_md = _project(tmp_path)
    _register(api, tmp_path)
    api.add_human_note(str(tmp_path), "harmless\nphase: HACKED")
    fm = parse_frontmatter(state_md.read_text(encoding="utf-8"))
    assert fm["phase"] == "DONE", "a note forged a frontmatter field"
    assert fm["human_note"] == "harmless phase: HACKED"


def test_replacing_a_note_does_not_stack_duplicates(api, tmp_path):
    state_md = _project(tmp_path)
    _register(api, tmp_path)
    api.add_human_note(str(tmp_path), "first")
    api.add_human_note(str(tmp_path), "second")
    body = state_md.read_text(encoding="utf-8")
    assert body.count("human_note:") == 1, "two human_note keys -- which wins?"
    assert _note(state_md) == "second"


def test_empty_note_is_refused_rather_than_written(api, tmp_path):
    state_md = _project(tmp_path)
    _register(api, tmp_path)
    assert api.add_human_note(str(tmp_path), "   ")["ok"] is False
    assert _note(state_md) is None


def test_missing_state_md_is_reported_not_crashed(api, tmp_path):
    (tmp_path / ".saipen").mkdir()
    result = api.add_human_note(str(tmp_path), "note")
    assert result["ok"] is False
    assert "root" in result["error"] or "STATE.md" in result["error"]
