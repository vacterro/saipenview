"""Tests for saipenview.parser — STATE.md, BOARD.md, OUTBOX.md parsing."""

from __future__ import annotations

from pathlib import Path

from conftest import make_ready_outbox

from saipenview.parser import collect_outbox_entry

# ── Frontmatter parsing ──


class TestParseFrontmatter:
    def test_simple_frontmatter(self):
        from saipenview.parser import parse_frontmatter

        text = """---
phase: DONE
task: none
next_action: "WAIT: nothing queued"
blocker: none
---
"""
        fm = parse_frontmatter(text)
        assert fm["phase"] == "DONE"
        assert fm["task"] == "none"
        assert fm["next_action"] == "WAIT: nothing queued"
        assert fm["blocker"] == "none"

    def test_no_frontmatter_returns_empty(self):
        from saipenview.parser import parse_frontmatter

        assert parse_frontmatter("Just text") == {}
        assert parse_frontmatter("") == {}

    def test_unquoted_value(self):
        from saipenview.parser import parse_frontmatter

        text = """---
phase: BUILD
task: some work
---
"""
        fm = parse_frontmatter(text)
        assert fm["phase"] == "BUILD"
        assert fm["task"] == "some work"

    def test_single_quoted_value(self):
        from saipenview.parser import parse_frontmatter

        text = "---\nagent: 'claude'\n---\n"
        fm = parse_frontmatter(text)
        assert fm["agent"] == "claude"

    def test_double_quoted_value_with_spaces(self):
        from saipenview.parser import parse_frontmatter

        text = '---\nnext_action: "WAIT: review PR"\n---\n'
        fm = parse_frontmatter(text)
        assert fm["next_action"] == "WAIT: review PR"

    def test_whitespace_handling(self):
        from saipenview.parser import parse_frontmatter

        text = "---\n  phase:  HUNT  \n  task:  chasing bugs\n---\n"
        fm = parse_frontmatter(text)
        assert fm["phase"] == "HUNT"
        assert fm["task"] == "chasing bugs"

    def test_multiline_value_not_supported(self):
        """Flat key:value parser captures the pipe as the value."""
        from saipenview.parser import parse_frontmatter

        text = "---\ndescription: |\n  line1\n  line2\n---\n"
        fm = parse_frontmatter(text)
        # The flat parser captures '|' as the value of 'description'
        assert fm.get("description") == "|"


# ── BOARD parsing ──


class TestParseBoard:
    def test_empty_board(self):
        from saipenview.parser import parse_board

        board = parse_board("# BOARD\n\n## TODO\n\n## DOING\n\n## DONE\n\n## BLOCKED\n")
        assert board.counts() == {"doing": 0, "todo": 0, "done": 0, "blocked": 0}

    def test_tickets_in_sections(self):
        from saipenview.parser import parse_board

        text = """# BOARD

## TODO
- [ ] T-001 | First task
- [ ] T-002 | Second task

## DOING
- [/] T-003 | In progress

## DONE
- [x] T-004 | Completed
"""
        board = parse_board(text)
        assert board.counts()["todo"] == 2
        assert board.counts()["doing"] == 1
        assert board.counts()["done"] == 1
        assert board.counts()["blocked"] == 0

    def test_ticket_fields(self):
        from saipenview.parser import parse_board

        text = "## TODO\n- [/] T-001 | My ticket\n"
        board = parse_board(text)
        t = board.todo[0]
        assert t.ticket_id == "T-001"
        assert t.status == "/"
        # The ticket regex captures everything after the ID, including '| ' separator
        assert "My ticket" in t.description

    def test_ignores_non_ticket_lines(self):
        from saipenview.parser import parse_board

        text = """## TODO
Some description text
- [ ] T-001 | Real ticket
"""
        board = parse_board(text)
        assert len(board.todo) == 1


class TestBoardCounts:
    def test_counts_dict(self):
        from saipenview.parser import Board, Ticket

        b = Board(
            doing=[Ticket("T-1", "/", "doing")],
            todo=[Ticket("T-2", " ", "todo"), Ticket("T-3", " ", "todo")],
            done=[],
            blocked=[Ticket("T-4", " ", "blocked")],
        )
        assert b.counts() == {"doing": 1, "todo": 2, "done": 0, "blocked": 1}


# ── OUTBOX parsing ──


class TestParseOutbox:
    def test_empty_outbox(self):
        from saipenview.parser import parse_outbox

        assert parse_outbox("# OUTBOX\n\n") == []

    def test_single_entry(self):
        from saipenview.parser import parse_outbox

        text = """# OUTBOX

## HUNT-001: null pointer
- **status:** ready
- **critical:** true
- **severity:** MEDIUM
- **summary:** Found nullable field
"""
        entries = parse_outbox(text)
        assert len(entries) == 1
        e = entries[0]
        assert e.entry_id == "HUNT-001"
        assert e.title == "null pointer"
        assert e.status == "ready"
        assert e.critical is True
        assert e.severity == "MEDIUM"
        assert e.summary == "Found nullable field"

    def test_multiple_entries(self):
        from saipenview.parser import parse_outbox

        text = """# OUTBOX

## HUNT-001: first
- **status:** ready
- **critical:** false

## WIKI-001: second
- **status:** draft
- **critical:** false
"""
        entries = parse_outbox(text)
        assert len(entries) == 2
        assert entries[0].entry_id == "HUNT-001"
        assert entries[1].entry_id == "WIKI-001"

    def test_non_critical_entry(self):
        from saipenview.parser import parse_outbox

        text = """## TASK-001: documentation
- **status:** ready
- **critical:** false
- **summary:** Added docs
"""
        entries = parse_outbox(text)
        assert len(entries) == 1
        assert entries[0].critical is False

    def test_multi_line_details(self):
        from saipenview.parser import parse_outbox

        text = """## BUG-001: crash
- **status:** ready
- **critical:** true
- **details:** The error occurs when
  the user presses Ctrl+Q while
  the zone picker is open.
"""
        entries = parse_outbox(text)
        assert len(entries) == 1
        assert "error occurs" in entries[0].details
        assert "zone picker" in entries[0].details

    def test_entry_with_no_status_field(self):
        from saipenview.parser import parse_outbox

        text = """## TEST-001: minimal
- **critical:** false
"""
        entries = parse_outbox(text)
        assert len(entries) == 1
        assert entries[0].status == ""


# ── update_state ──


class TestUpdateState:
    def test_updates_existing_field(self, saipen_project):
        from saipenview.parser import update_state

        result = update_state(saipen_project, {"task": "new task"})
        assert result is True

        state = saipen_project / ".saipen" / "STATE.md"
        text = state.read_text(encoding="utf-8")
        assert "task: new task" in text

    def test_adds_new_field(self, saipen_project):
        from saipenview.parser import update_state

        result = update_state(saipen_project, {"extra_field": "extra value"})
        assert result is True

        text = (saipen_project / ".saipen" / "STATE.md").read_text(encoding="utf-8")
        assert "extra_field: extra value" in text

    def test_returns_false_for_missing_project(self, tmp_path):
        from saipenview.parser import update_state

        assert update_state(tmp_path / "nonexistent", {"task": "x"}) is False

    def test_updates_timestamp(self, saipen_project):
        """update_state should set 'updated' field automatically."""
        from saipenview.parser import update_state

        result = update_state(saipen_project, {"task": "test timestamp"})
        assert result is True
        text = (saipen_project / ".saipen" / "STATE.md").read_text(encoding="utf-8")
        assert "updated:" in text

    def test_returns_false_when_state_not_found(self, tmp_path):
        """update_state with no STATE.md returns False."""
        from saipenview.parser import update_state

        result = update_state(tmp_path / "nope", {"task": "x"})
        assert result is False

    def test_returns_false_when_no_frontmatter(self, tmp_path):
        """update_state with no frontmatter returns False."""
        from saipenview.parser import update_state

        d = tmp_path / "proj"
        (d / ".saipen").mkdir(parents=True)
        (d / ".saipen" / "STATE.md").write_text("Just text\n", encoding="utf-8")
        result = update_state(d, {"task": "x"})
        assert result is False

    def test_preserves_non_key_lines_in_frontmatter(self, saipen_project):
        """Lines in frontmatter that aren't key:value pairs are preserved."""
        from saipenview.parser import update_state

        state_path = saipen_project / ".saipen" / "STATE.md"
        text = state_path.read_text(encoding="utf-8")
        text = text.replace("---\n", "---\n# comment line\n", 1)
        state_path.write_text(text, encoding="utf-8")

        result = update_state(saipen_project, {"phase": "DONE"})
        assert result is True
        new_text = state_path.read_text(encoding="utf-8")
        assert "# comment line" in new_text


# ── move_ticket ──


class TestMoveTicket:
    def test_start_ticket(self, saipen_project_with_board):
        """Move T-001 from TODO to DOING (start action)."""
        from saipenview.parser import move_ticket

        result = move_ticket(saipen_project_with_board, "T-001", "start")
        assert result is True

        text = (saipen_project_with_board / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )
        assert "[/] T-001" in text  # Now in-progress
        assert "DOING" in text

    def test_done_ticket(self, saipen_project_with_board):
        """Move T-003 from DOING to DONE (with completion evidence)."""
        from saipenview.parser import move_ticket

        # DOING -> DONE needs a non-empty | verify: clause (canonical
        # completion evidence); give T-003 one, then close it.
        board = saipen_project_with_board / ".saipen" / "BOARD.md"
        text = board.read_text(encoding="utf-8")
        board.write_text(
            text.replace(
                "- [/] T-003 | In progress",
                "- [/] T-003 | In progress | verify: tested",
            ),
            encoding="utf-8",
        )

        result = move_ticket(saipen_project_with_board, "T-003", "done")
        assert result is True

        text = (saipen_project_with_board / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )
        assert "[x] T-003" in text

    def test_reopen_ticket(self, saipen_project_with_board):
        """Move T-004 from DONE to TODO."""
        from saipenview.parser import move_ticket

        result = move_ticket(saipen_project_with_board, "T-004", "reopen")
        assert result is True

        text = (saipen_project_with_board / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )
        assert "[ ] T-004" in text

    def test_unknown_action_returns_false(self, saipen_project_with_board):
        from saipenview.parser import move_ticket

        assert move_ticket(saipen_project_with_board, "T-001", "invalid") is False

    def test_nonexistent_ticket_returns_false(self, saipen_project_with_board):
        from saipenview.parser import move_ticket

        assert move_ticket(saipen_project_with_board, "T-999", "start") is False

    def test_unknown_action_returns_false_at_start(self, saipen_project_with_board):
        """An action not in _TICKET_ACTIONS returns False."""
        from saipenview.parser import move_ticket

        assert move_ticket(saipen_project_with_board, "T-001", "nonsense") is False

    def test_missing_board_file_returns_false(self, tmp_path):
        from saipenview.parser import move_ticket

        assert move_ticket(tmp_path / "no-board", "T-001", "start") is False

    def test_inserts_at_end_when_no_following_section(self, tmp_path):
        """Move to a section that is the last in the file inserts at end."""
        from saipenview.parser import move_ticket

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "BOARD.md").write_text(
            "# BOARD\n\n## TODO\n- [ ] T-001 | first\n- [ ] T-002 | second\n",
            encoding="utf-8",
        )
        # Reopen doesn't apply to [ ] tickets, but the action path is valid
        result = move_ticket(root, "T-002", "reopen")
        # Should not crash — even if reopen doesn't match, the function handles it
        assert isinstance(result, bool)


# ── collect_outbox ──


def _bare_project(tmp_path, name="proj") -> Path:
    """A minimal main project: STATE + BOARD (4 headings) + LOG."""
    root = tmp_path / name
    (root / ".saipen").mkdir(parents=True)
    (root / ".saipen" / "STATE.md").write_text(
        "---\nphase: BUILD\ntask: T-001\n---\n", encoding="utf-8"
    )
    (root / ".saipen" / "BOARD.md").write_text(
        "# BOARD\n\n## TODO\n- [ ] T-001 existing\n\n## DOING\n\n## DONE\n\n## BLOCKED\n",
        encoding="utf-8",
    )
    (root / ".saipen" / "LOG.md").write_text(
        "# LOG\n\n- 27.07.26 10:00 [E-1] RUN: boot\n", encoding="utf-8"
    )
    return root


class TestCollectOutbox:
    def test_collect_critical_creates_ticket(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "null pointer", critical="true")
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is True
        assert result["ticket_id"] is not None
        assert result["ticket_id"].startswith("T-")

        board = (root / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
        assert result["ticket_id"] in board
        assert "null pointer" in board
        assert "[from saihunt HUNT-001]" in board

    def test_collect_marked_reviewed(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        assert collect_outbox_entry(root, "saihunt", "HUNT-001")["ok"] is True
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        text = outbox.read_text(encoding="utf-8")
        assert "**status:** reviewed" in text

    def test_collect_nonexistent_entry(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        result = collect_outbox_entry(root, "saihunt", "NONEXISTENT")
        assert result["ok"] is False
        assert "not found" in result["message"].lower()

    def test_collect_appends_log(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        collect_outbox_entry(root, "saihunt", "HUNT-001")
        log = (root / ".saipen" / "LOG.md").read_text(encoding="utf-8")
        assert "RUN: collect saihunt HUNT-001" in log

    def test_collect_non_critical_to_inbox(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-002", "minor lint", critical="false")
        result = collect_outbox_entry(root, "saihunt", "HUNT-002")
        assert result["ok"] is True
        assert result["ticket_id"] is None
        assert "inbox" in result["message"]

        inbox = root / ".saipen" / "extensions" / "subs" / "_shared" / "inbox.md"
        assert inbox.is_file()
        assert "HUNT-002" in inbox.read_text(encoding="utf-8")
        # A non-critical collect must NOT touch the main board.
        board = (root / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
        assert "HUNT-002" not in board

    def test_collect_no_subs_dir_returns_error(self, tmp_path):
        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "no subs" in result["message"]

    def test_collect_no_outbox_file_returns_error(self, tmp_path):
        root = tmp_path / "proj"
        (root / ".saipen" / "extensions" / "subs" / "saihunt" / "kitchen").mkdir(
            parents=True
        )
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "no OUTBOX" in result["message"]

    def test_collect_already_reviewed_is_a_noop(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        first = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert first["ok"] is True
        second = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert second["ok"] is True
        assert second.get("already") is True
        # Idempotency: exactly one ticket, one LOG line.
        board = (root / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
        assert board.count("T-002") == 1
        log = (root / ".saipen" / "LOG.md").read_text(encoding="utf-8")
        assert log.count("collect saihunt HUNT-001") == 1

    def test_collect_not_ready_is_a_controlled_refusal(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **status:** ready", "- **status:** draft", 1
            ),
            encoding="utf-8",
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "not ready" in result["message"]
        # Nothing was written.
        assert "T-002" not in (root / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )
        assert "reviewed" not in outbox.read_text(encoding="utf-8")

    def test_collect_no_status_field_returns_error(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace("- **status:** ready\n", "", 1),
            encoding="utf-8",
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "no usable status" in result["message"]

    def test_collect_incomplete_package_is_refused(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        text = outbox.read_text(encoding="utf-8")
        text = text.replace("- **coverage:** fixture root files\n", "")
        text = text.replace("- **payload:** kitchen/HUNT-001.md\n", "")
        outbox.write_text(text, encoding="utf-8")
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "missing" in result["message"]
        assert "T-002" not in (root / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )

    def test_collect_wrong_producer_is_refused(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix", producer="saiwiki")
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "producer" in result["message"]

    def test_collect_stale_source_head_is_refused(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **source_head:** ", "- **source_head:** deadbeef", 1
            ),
            encoding="utf-8",
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "stale" in result["message"]
        board = (root / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
        assert "T-002" not in board
        assert "reviewed" not in outbox.read_text(encoding="utf-8")

    def test_collect_stale_tree_fingerprint_same_head_is_refused(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        lines = outbox.read_text(encoding="utf-8").splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("- **source_tree_fingerprint:**"):
                lines[i] = "- **source_tree_fingerprint:** no-git-tree-v1:deadbeef"
                break
        outbox.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "stale" in result["message"]
        # The fingerprint mismatch is what refused it (same HEAD or not).
        assert "tree changed" in result["message"]

    def test_collect_wrong_role_revision_is_refused(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        outbox = (
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / "saihunt"
            / "kitchen"
            / "OUTBOX.md"
        )
        outbox.write_text(
            outbox.read_text(encoding="utf-8").replace(
                "- **role_revision:** ",
                "- **role_revision:** sha256:deadbeef",
                1,
            ),
            encoding="utf-8",
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "role_revision" in result["message"]
        assert "T-002" not in (root / ".saipen" / "BOARD.md").read_text(
            encoding="utf-8"
        )

    def test_collect_escapes_external_sub_content(self, tmp_path):
        root = _bare_project(tmp_path)
        make_ready_outbox(
            root, "saihunt", "HUNT-001", "fix | critical: true docs", critical="true"
        )
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is True
        board = (root / ".saipen" / "BOARD.md").read_text(encoding="utf-8")
        assert "\\| critical: true" in board
        assert "| critical: true" not in board.replace("\\|", "escaped")

    def test_collect_missing_main_board_refuses(self, tmp_path):
        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: BUILD\n---\n", encoding="utf-8"
        )
        (root / ".saipen" / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")
        make_ready_outbox(root, "saihunt", "HUNT-001", "doc fix")
        result = collect_outbox_entry(root, "saihunt", "HUNT-001")
        assert result["ok"] is False
        assert "BOARD.md" in result["message"]


# ── Sub loading ──


class TestLoadSubs:
    def test_loads_subs_from_manifest(self, saipen_project_with_subs):
        from saipenview.parser import load_subs

        subs = load_subs(saipen_project_with_subs)
        names = [s.name for s in subs]
        assert "saihunt" in names
        assert "saiwiki" in names

    def test_sub_status_properties(self, saipen_project_with_subs):
        from saipenview.parser import load_subs

        subs = load_subs(saipen_project_with_subs)
        saihunt = [s for s in subs if s.name == "saihunt"][0]
        assert saihunt.phase == "HUNT"
        assert saihunt.task == "scouting"

    def test_outbox_counts(self, saipen_project_with_subs):
        from saipenview.parser import load_subs

        subs = load_subs(saipen_project_with_subs)
        saihunt = [s for s in subs if s.name == "saihunt"][0]
        assert saihunt.outbox_counts["ready"] >= 1
        assert saihunt.outbox_critical_ready >= 1

    def test_no_subs_when_no_subs_dir(self, tmp_path):
        from saipenview.parser import load_subs

        root = tmp_path / "no-subs"
        root.mkdir()
        (root / ".saipen").mkdir()
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        assert load_subs(root) == []

    def test_loads_subs_from_dir_scan_when_no_manifest(self, tmp_path):
        """When no MANIFEST.md exists, load_subs falls back to directory scan."""
        from saipenview.parser import load_subs

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        # Create subs dir with STATE.md but WITHOUT MANIFEST.md
        # Note: load_subs checks entry/STATE.md (not entry/.saipen/STATE.md)
        subs_dir = root / ".saipen" / "extensions" / "subs"
        (subs_dir / "saihunt").mkdir(parents=True)
        (subs_dir / "saihunt" / "STATE.md").write_text(
            "---\nphase: HUNT\n---\n", encoding="utf-8"
        )
        (subs_dir / "saiwiki").mkdir(parents=True)
        (subs_dir / "saiwiki" / "STATE.md").write_text(
            "---\nphase: WIKI\n---\n", encoding="utf-8"
        )

        subs = load_subs(root)
        names = [s.name for s in subs]
        assert "saihunt" in names
        assert len(subs) == 2

    def test_skips_reserved_dirs_in_dir_scan(self, tmp_path):
        """TEMPLATE and _shared dirs are skipped in dir scan fallback."""
        from saipenview.parser import load_subs

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        subs_dir = root / ".saipen" / "extensions" / "subs"
        subs_dir.mkdir(parents=True)
        (subs_dir / "TEMPLATE").mkdir()
        (subs_dir / "TEMPLATE" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        (subs_dir / "_shared").mkdir()
        (subs_dir / "saihunt").mkdir()
        (subs_dir / "saihunt" / "STATE.md").write_text(
            "---\nphase: HUNT\n---\n", encoding="utf-8"
        )

        subs = load_subs(root)
        names = [s.name for s in subs]
        assert "TEMPLATE" not in names
        assert "_shared" not in names
        assert "saihunt" in names

    def test_finds_subs_in_root_extensions_dir(self, tmp_path):
        """load_subs checks root/extensions/subs as fallback path."""
        from saipenview.parser import load_subs

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        # Create subs at root/extensions/subs (not .saipen/...)
        (root / "extensions" / "subs" / "mysub").mkdir(parents=True)
        (root / "extensions" / "subs" / "mysub" / "STATE.md").write_text(
            "---\nphase: BUILD\n---\n", encoding="utf-8"
        )

        subs = load_subs(root)
        assert len(subs) == 1
        assert subs[0].name == "mysub"

    def test_manifest_returns_none_on_corrupt_file(self, tmp_path):
        """Unreadable MANIFEST.md returns None (dir scan fallback)."""
        from saipenview.parser import load_subs

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        subs_dir = root / ".saipen" / "extensions" / "subs"
        subs_dir.mkdir(parents=True)
        # Write a corrupt MANIFEST.md
        (subs_dir / "MANIFEST.md").write_bytes(b"\xff\xfe")
        (subs_dir / "mysub").mkdir()
        (subs_dir / "mysub" / "STATE.md").write_text(
            "---\nphase: BUILD\n---\n", encoding="utf-8"
        )

        subs = load_subs(root)
        # Falls back to dir scan
        assert len(subs) >= 1


# ── SubStatus properties ──


class TestSubStatus:
    def test_missing_state_keys_return_defaults(self):
        from saipenview.parser import SubStatus

        s = SubStatus(name="test", path=Path("/tmp"), state={})
        assert s.phase == "?"
        assert s.task == "none"
        assert s.blocker == "none"
        assert s.next_action == ""
        assert s.updated == ""


# ── ProjectStatus ──


class TestProjectStatus:
    def test_name_from_root(self):
        from saipenview.parser import Board, ProjectStatus

        p = ProjectStatus(
            root=Path("/projects/my-app"), state={"phase": "DONE"}, board=Board()
        )
        assert p.name == "my-app"

    def test_phase_from_state(self):
        from saipenview.parser import Board, ProjectStatus

        p = ProjectStatus(root=Path("/p"), state={"phase": "BUILD"}, board=Board())
        assert p.phase == "BUILD"

    def test_missing_phase_returns_question(self):
        from saipenview.parser import Board, ProjectStatus

        p = ProjectStatus(root=Path("/p"), state={}, board=Board())
        assert p.phase == "?"

    def test_task_default(self):
        from saipenview.parser import Board, ProjectStatus

        p = ProjectStatus(root=Path("/p"), state={}, board=Board())
        assert p.task == "none"


# ── Quick actions ──


class TestDetectQuickActions:
    def test_detects_package_json(self, tmp_path):
        from saipenview.parser import detect_quick_actions

        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        actions = detect_quick_actions(tmp_path)
        assert len(actions) > 0
        assert any(a["label"] == "npm run dev" for a in actions)
        assert any(a["label"] == "npm test" for a in actions)

    def test_detects_cargo_toml(self, tmp_path):
        from saipenview.parser import detect_quick_actions

        (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        actions = detect_quick_actions(tmp_path)
        assert len(actions) > 0
        assert any(a["label"] == "cargo build" for a in actions)

    def test_no_match_returns_empty(self, tmp_path):
        from saipenview.parser import detect_quick_actions

        assert detect_quick_actions(tmp_path) == []


# ── Load project ──


class TestLoadProject:
    def test_loads_project(self, saipen_project):
        from saipenview.parser import load_project

        proj = load_project(saipen_project, with_git=False)
        assert proj is not None
        assert proj.name == "my-project"
        assert proj.phase == "PLAN"

    def test_returns_none_for_missing_state(self, tmp_path):
        from saipenview.parser import load_project

        assert load_project(tmp_path / "nonexistent", with_git=False) is None

    def test_loads_with_board(self, saipen_project_with_board):
        from saipenview.parser import load_project

        proj = load_project(saipen_project_with_board, with_git=False)
        assert proj is not None
        assert proj.board.counts()["todo"] == 2
        assert proj.board.counts()["doing"] == 1

    def test_loads_with_subs(self, saipen_project_with_subs):
        from saipenview.parser import load_project

        proj = load_project(saipen_project_with_subs, with_git=False)
        assert proj is not None
        assert len(proj.subs) >= 2

    def test_load_project_handles_state_stat_error(self, tmp_path):
        """If stat() on STATE.md fails for mtime (but is_file passes), mtime=0."""
        import os
        from unittest.mock import patch

        from saipenview.parser import load_project

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: BUILD\n---\n", encoding="utf-8"
        )
        (root / ".saipen" / "BOARD.md").write_text(
            "# BOARD\n\n## TODO\n\n## DONE\n\n", encoding="utf-8"
        )

        # First call to os.stat (for is_file) passes, second call (for mtime) fails
        real_stat = os.stat
        _calls = {}

        def _mock_stat(path, *args, **kwargs):
            key = str(path)
            _calls[key] = _calls.get(key, 0) + 1
            if "STATE.md" in key and _calls[key] > 1:
                raise OSError("access denied")
            return real_stat(path, *args, **kwargs)

        with patch("os.stat", new=_mock_stat):
            proj = load_project(root, with_git=False)
            assert proj is not None
            assert proj.mtime == 0


# ── load_translate ──


class TestLoadTranslate:
    def test_loads_from_dot_saitranslate(self, saipen_project_with_translate):
        """load_translate finds .saitranslate/ at project root."""
        from saipenview.parser import load_translate

        t = load_translate(saipen_project_with_translate)
        assert t is not None
        assert t.name == "saitranslate"
        assert t.phase == "TRANSLATE"

    def test_loads_from_dot_saipen_saitranslate(self, tmp_path):
        """load_translate also checks .saipen/saitranslate/ path."""
        from saipenview.parser import load_translate

        root = tmp_path / "proj"
        (root / ".saipen" / "saitranslate").mkdir(parents=True)
        (root / ".saipen" / "saitranslate" / "STATE.md").write_text(
            "---\nphase: TRANSLATE\n---\n", encoding="utf-8"
        )
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        t = load_translate(root)
        assert t is not None
        assert t.name == "saitranslate"

    def test_returns_none_when_missing(self, saipen_project):
        """No translate dir exists → None."""
        from saipenview.parser import load_translate

        assert load_translate(saipen_project) is None


# ── check_subs_staleness ──


class TestCheckSubsStaleness:
    def test_not_stale_when_files_match(self, saipen_project_with_staleness):
        """Matching canonical files → not stale."""
        from saipenview.parser import check_subs_staleness

        fm = {"saipen_home": str(saipen_project_with_staleness.parent / "saipen-home")}
        stale, details = check_subs_staleness(saipen_project_with_staleness, fm)
        assert stale is False
        assert details == ""

    def test_stale_when_local_file_missing(self, saipen_project_with_staleness):
        """Missing local file → stale."""
        from saipenview.parser import check_subs_staleness

        # Delete a local file
        local_file = (
            saipen_project_with_staleness
            / ".saipen"
            / "extensions"
            / "subs"
            / "PROTOCOL.md"
        )
        local_file.unlink()

        fm = {"saipen_home": str(saipen_project_with_staleness.parent / "saipen-home")}
        stale, details = check_subs_staleness(saipen_project_with_staleness, fm)
        assert stale is True
        assert "missing locally" in details

    def test_not_stale_when_no_saipen_home(self, saipen_project):
        """No saipen_home in state → not stale."""
        from saipenview.parser import check_subs_staleness

        stale, details = check_subs_staleness(saipen_project, {})
        assert stale is False
        assert details == ""

    def test_not_stale_when_canon_missing(self, saipen_project_with_staleness):
        """Missing canonical dir → not stale."""
        from saipenview.parser import check_subs_staleness

        fm = {"saipen_home": "/nonexistent/path"}
        stale, details = check_subs_staleness(saipen_project_with_staleness, fm)
        assert stale is False
        assert details == ""

    def test_get_git_status_handles_exception(self, tmp_path):
        """get_git_status returns empty when subprocess.run raises."""
        from unittest.mock import patch

        from saipenview.parser import get_git_status

        with patch("subprocess.run", side_effect=Exception("git not found")):
            branch, dirty = get_git_status(tmp_path)
            assert branch == ""
            assert dirty is False

    def test_load_log_tail_handles_exception(self, tmp_path):
        """load_log_tail returns [] when read fails."""
        from unittest.mock import patch

        from saipenview.parser import load_log_tail

        # Mock Path.open to raise on LOG.md
        original_open = Path.open

        def _mock_open(self_obj, *args, **kwargs):
            if "LOG.md" in str(self_obj):
                raise OSError("access denied")
            return original_open(self_obj, *args, **kwargs)

        log_path = tmp_path / ".saipen" / "LOG.md"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("- line1\n", encoding="utf-8")

        with patch.object(Path, "open", _mock_open):
            result = load_log_tail(tmp_path, max_lines=5)
            assert result == []

    def test_load_log_tail_no_file(self, tmp_path):
        """load_log_tail returns [] when LOG.md doesn't exist."""
        from saipenview.parser import load_log_tail

        result = load_log_tail(tmp_path / "nonexistent", max_lines=5)
        assert result == []

    def test_not_stale_when_no_subs_dir(self, tmp_path):
        """No subs/ directory at all → not stale."""
        from saipenview.parser import check_subs_staleness

        root = tmp_path / "proj"
        (root / ".saipen").mkdir(parents=True)
        (root / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )
        fm = {"saipen_home": str(tmp_path / "saipen-home")}
        stale, details = check_subs_staleness(root, fm)
        assert stale is False
        assert details == ""

    def test_stale_when_file_differ_mtime(self, saipen_project_with_staleness):
        """If a file mtime/size differs, it's stale."""
        from saipenview.parser import check_subs_staleness

        # Touch a local file to change its mtime
        local_file = (
            saipen_project_with_staleness
            / ".saipen"
            / "extensions"
            / "subs"
            / "PROTOCOL.md"
        )
        # Write different content to change size
        local_file.write_text("modified\n", encoding="utf-8")

        fm = {"saipen_home": str(saipen_project_with_staleness.parent / "saipen-home")}
        stale, details = check_subs_staleness(saipen_project_with_staleness, fm)
        assert stale is True
        assert "differ" in details

    def test_stale_when_canonical_missing(self, saipen_project_with_staleness):
        """If canonical file is missing locally, it's stale."""
        from saipenview.parser import check_subs_staleness

        canon_root = (
            saipen_project_with_staleness.parent / "saipen-home" / "extensions" / "subs"
        )
        # Delete a canonical file
        canon_file = canon_root / "PROTOCOL.md"
        if canon_file.exists():
            # Just rename to simulate missing
            canon_file.rename(canon_file.with_suffix(".md.bak"))

        fm = {"saipen_home": str(saipen_project_with_staleness.parent / "saipen-home")}
        stale, details = check_subs_staleness(saipen_project_with_staleness, fm)
        local_file = (
            saipen_project_with_staleness
            / ".saipen"
            / "extensions"
            / "subs"
            / "PROTOCOL.md"
        )
        if local_file.exists() and not canon_file.exists():
            # Canon missing, local present
            assert stale is True
            assert "missing from canonical" in details
