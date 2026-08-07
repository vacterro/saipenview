"""Every rule gets a green baseline and a red mutation.

The rule this suite is built around (SAIPEN `phases/verify.md`): a gate stuck
red lies as loudly as one stuck green. So no test here asserts only that a
finding appears -- each one starts from a project the grader passes clean, then
breaks exactly one thing. If the baseline ever stops being clean the whole file
fails at `test_baseline_is_clean`, and every "it went red" assertion below is
worth nothing until that is fixed.
"""

from __future__ import annotations

import datetime

import pytest

from saipenview.conformance import check_project, parse_board_strict
from saipenview.parser import load_subs, parse_frontmatter
from saipenview.textio import read_doc

GOOD_STATE = """---
phase: BUILD
task: T-001
next_action: "RUN: finish the parser"
blocker: none
agent: claude-opus
saipen_version: 7
mode: full
goal_mode: false
updated: {updated}
transition_from: SCOUT
---
"""

GOOD_BOARD = """# Board
## DOING
- [/] T-001 wire the parser | owner: core

## TODO
- [ ] T-002 write the tests | needs: T-001

## DONE
- [x] T-000 bootstrap | verify: it booted

## BLOCKED
"""

GOOD_LOG = """# Log

- 27.07.26 10:00 [E-1] RUN: bootstrap
- 27.07.26 11:00 [E-2] [parent: E-1] RUN: wired the parser
"""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def project(tmp_path):
    """A project the grader passes clean. Mutate it, then re-grade."""
    saipen = tmp_path / ".saipen"
    saipen.mkdir()
    (saipen / "STATE.md").write_text(
        GOOD_STATE.format(updated=_now()), encoding="utf-8"
    )
    (saipen / "BOARD.md").write_text(GOOD_BOARD, encoding="utf-8")
    (saipen / "LOG.md").write_text(GOOD_LOG, encoding="utf-8")
    return tmp_path


def grade(root):
    state = parse_frontmatter(read_doc(root / ".saipen" / "STATE.md"))
    return check_project(root, state, load_subs(root))


def rules(report) -> set[str]:
    return {f.rule for f in report.findings}


def set_state(root, **fields):
    """Rewrite named STATE fields, dropping any whose value is None."""
    path = root / ".saipen" / "STATE.md"
    out = []
    for line in read_doc(path).splitlines():
        key = line.partition(":")[0].strip()
        if key in fields:
            value = fields.pop(key)
            if value is None:
                continue
            out.append(f"{key}: {value}")
        else:
            out.append(line)
    # Anything not already present gets appended inside the frontmatter.
    for key, value in fields.items():
        if value is not None:
            out.insert(len(out) - 1, f"{key}: {value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


class TestBaseline:
    def test_baseline_is_clean(self, project):
        """The control. Every red assertion below is meaningless without it."""
        report = grade(project)
        assert report.verdict == "pass", [f.message for f in report.findings]
        assert report.fails == 0
        assert report.warns == 0

    def test_baseline_names_its_edition(self, project):
        assert grade(project).to_dict()["baseline"]


class TestStateShape:
    def test_missing_state(self, tmp_path):
        (tmp_path / ".saipen").mkdir()
        assert "state.missing" in rules(check_project(tmp_path, {}))

    def test_no_frontmatter(self, project):
        (project / ".saipen" / "STATE.md").write_text(
            "nothing here\n", encoding="utf-8"
        )
        assert "state.frontmatter" in rules(grade(project))

    @pytest.mark.parametrize(
        "field",
        [
            "phase",
            "task",
            "next_action",
            "blocker",
            "agent",
            "updated",
            "mode",
            "saipen_version",
            "transition_from",
        ],
    )
    def test_each_required_field_is_actually_required(self, project, field):
        set_state(project, **{field: None})
        assert f"state.missing.{field}" in rules(grade(project))

    def test_transition_from_exempt_on_fresh_init(self, project):
        set_state(
            project,
            phase="INIT",
            transition_from=None,
            task="none",
            next_action='"saipen plan"',
        )
        assert "state.missing.transition_from" not in rules(grade(project))

    def test_unknown_phase(self, project):
        set_state(project, phase="REFACTOR")
        assert "state.phase.enum" in rules(grade(project))

    def test_unknown_mode(self, project):
        set_state(project, mode="yolo")
        assert "state.mode.enum" in rules(grade(project))

    def test_saipen_version_must_be_an_integer(self, project):
        set_state(project, saipen_version="v7.103.0")
        assert "state.saipen_version.type" in rules(grade(project))


class TestTransitions:
    def test_illegal_transition(self, project):
        # INIT allows only PLAN/BLOCKED; INIT -> BUILD is not in the table.
        set_state(project, transition_from="INIT")
        assert "state.transition.illegal" in rules(grade(project))

    def test_from_any_phase_command_is_not_a_transition(self, project):
        # VALIDATE is entered by command from anywhere, so no FROM row applies.
        set_state(project, phase="VALIDATE", transition_from="REVIEW", task="none")
        assert "state.transition.illegal" not in rules(grade(project))

    def test_ship_is_not_from_any_phase(self, project):
        # `saipen ship` is a command from anywhere; `phase: SHIP` is reachable
        # only from REVIEW. A command is not a transition.
        set_state(project, phase="SHIP", transition_from="INIT")
        assert "state.transition.illegal" in rules(grade(project))

    def test_review_to_ship_is_legal(self, project):
        set_state(project, phase="SHIP", transition_from="REVIEW")
        assert "state.transition.illegal" not in rules(grade(project))


class TestReadOnly:
    @pytest.mark.parametrize(
        "phase", ["INIT", "PLAN", "ADD", "BUILD", "SHIP", "CLEAN", "TRANSLATE"]
    )
    def test_read_only_cannot_write(self, project, phase):
        set_state(project, mode="read-only", phase=phase, transition_from=phase)
        assert "state.readonly.phase" in rules(grade(project))

    def test_read_only_may_hunt(self, project):
        set_state(
            project,
            mode="read-only",
            phase="HUNT",
            transition_from="HUNT",
            task="none",
        )
        assert "state.readonly.phase" not in rules(grade(project))


class TestNextAction:
    @pytest.mark.parametrize(
        "value",
        [
            "continue work",
            "fix the thing",
            "ship it",
            "look at the board",
            "just keep going",
        ],
    )
    def test_prefixless_next_action(self, project, value):
        # The blacklist of vague phrases was always evadable; the whitelist of
        # five prefixes is the check that carries the weight.
        set_state(project, next_action=f'"{value}"')
        assert "next_action.prefix" in rules(grade(project))

    @pytest.mark.parametrize(
        "value",
        [
            '"WAIT: user brake -- decide the next goal"',
            '"saipen plan"',
            '"PHASE VERIFY"',
            '"RUN: pytest -q"',
            '"RESUME: T-001"',
        ],
    )
    def test_each_legal_prefix_passes(self, project, value):
        set_state(project, next_action=value)
        assert not {"next_action.prefix", "next_action.command"} & rules(grade(project))

    def test_wait_without_category(self, project):
        set_state(project, next_action='"WAIT: need more context"')
        assert "next_action.wait.category" in rules(grade(project))

    @pytest.mark.parametrize(
        "cat",
        [
            "manual-verify",
            "destructive-op",
            "first-publish",
            "user brake",
            "blocked",
            "safety valve",
            "init",
        ],
    )
    def test_each_category_is_accepted(self, project, cat):
        set_state(project, next_action=f'"WAIT: {cat} -- why"')
        assert "next_action.wait.category" not in rules(grade(project))

    def test_question_outside_wait(self, project):
        set_state(project, next_action='"RUN: should we ship?"')
        assert "next_action.question" in rules(grade(project))

    def test_undefined_saipen_command(self, project):
        # Passes the `saipen ` prefix rule while naming something § 1.10 does
        # not define. The example used to be `saipen hunt`, on the reasoning
        # that HUNT was reached autonomously and never invoked -- true until
        # SAIPEN 7.148.0 made it a real command (the shortcut table had `hh`
        # routing to a phase with nothing behind it). Picked a word the
        # protocol has no plans for instead, so the case tests the rule rather
        # than a snapshot of the command list.
        set_state(project, next_action='"saipen refactor"')
        assert "next_action.command" in rules(grade(project))


class TestGoalMode:
    def test_counters_required(self, project):
        set_state(project, goal_mode="true")
        found = rules(grade(project))
        assert "goal.goal_waves" in found
        assert "goal.goal_tickets" in found

    def test_counters_present_is_clean(self, project):
        set_state(project, goal_mode="true", goal_waves="1", goal_tickets="4")
        assert not {"goal.goal_waves", "goal.goal_tickets"} & rules(grade(project))

    def test_wave_cap(self, project):
        set_state(project, goal_mode="true", goal_waves="4", goal_tickets="4")
        assert "goal.waves.cap" in rules(grade(project))

    def test_ticket_cap(self, project):
        set_state(project, goal_mode="true", goal_waves="1", goal_tickets="21")
        assert "goal.tickets.cap" in rules(grade(project))


class TestUpdated:
    def test_bad_format(self, project):
        set_state(project, updated="2026-07-28 10:00")
        assert "state.updated.format" in rules(grade(project))

    def test_future_clock(self, project):
        ahead = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=6
        )
        set_state(project, updated=ahead.strftime("%Y-%m-%dT%H:%M:%SZ"))
        assert "state.updated.future" in rules(grade(project))

    def test_stale_is_a_warning_not_a_failure(self, project):
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
        set_state(project, updated=old.strftime("%Y-%m-%dT%H:%M:%SZ"))
        report = grade(project)
        assert "state.updated.stale" in rules(report)
        assert report.verdict == "warn"


class TestEncoding:
    def test_utf16_state_is_a_failure(self, project):
        path = project / ".saipen" / "STATE.md"
        path.write_bytes(read_doc(path).encode("utf-16"))
        report = grade(project)
        # Still graded -- the viewer can read it. Everything else cannot.
        assert "state.encoding" in rules(report)
        assert "state.frontmatter" not in rules(report)

    def test_bom_utf8_state_is_a_failure(self, project):
        path = project / ".saipen" / "STATE.md"
        path.write_bytes(b"\xef\xbb\xbf" + read_doc(path).encode("utf-8"))
        assert "state.encoding" in rules(grade(project))

    def test_utf16_board_is_a_failure(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_bytes(read_doc(path).encode("utf-16"))
        assert "board.encoding" in rules(grade(project))


class TestBoard:
    def test_missing_board(self, project):
        (project / ".saipen" / "BOARD.md").unlink()
        assert "board.missing" in rules(grade(project))

    @pytest.mark.parametrize("heading", ["DOING", "TODO", "DONE", "BLOCKED"])
    def test_each_heading_is_required(self, project, heading):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(read_doc(path).replace(f"## {heading}\n", ""), encoding="utf-8")
        assert "board.heading.missing" in rules(grade(project))

    def test_duplicate_heading(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(read_doc(path) + "\n## TODO\n", encoding="utf-8")
        assert "board.heading.duplicate" in rules(grade(project))

    def test_duplicate_ticket(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace(
                "## BLOCKED\n", "## BLOCKED\n- [ ] T-001 copied not moved\n"
            ),
            encoding="utf-8",
        )
        assert "board.duplicate" in rules(grade(project))

    def test_two_tickets_in_doing(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace(
                "- [/] T-001 wire the parser | owner: core\n",
                "- [/] T-001 wire the parser | owner: core\n- [/] T-003 also claimed\n",
            ),
            encoding="utf-8",
        )
        assert "board.doing.multiple" in rules(grade(project))

    def test_checkbox_disagrees_with_section(self, project):
        # `[x]` under ## TODO: exactly what move_ticket produced when its
        # replacement targeted the checkbox it expected rather than the one
        # actually on the line.
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace("- [ ] T-002", "- [x] T-002"), encoding="utf-8"
        )
        assert "board.checkbox.section" in rules(grade(project))

    def test_blocked_keeps_an_empty_box(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace("## BLOCKED\n", "## BLOCKED\n- [ ] T-004 waiting\n"),
            encoding="utf-8",
        )
        assert "board.checkbox.section" not in rules(grade(project))

    def test_dangling_needs(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace("needs: T-001", "needs: T-999"), encoding="utf-8"
        )
        assert "board.needs.dangling" in rules(grade(project))

    def test_cyclic_needs(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path)
            .replace(
                "- [/] T-001 wire the parser | owner: core",
                "- [/] T-001 wire the parser | needs: T-002",
            )
            .replace("needs: T-001", "needs: T-001"),
            encoding="utf-8",
        )
        assert "board.needs.cycle" in rules(grade(project))

    def test_unknown_ticket_field(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace("| owner: core", "| assignee: core"),
            encoding="utf-8",
        )
        assert "board.ticket.field" in rules(grade(project))

    def test_escaped_pipe_is_not_a_field(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path)
            .replace("| owner: core", "")
            .replace("T-001 wire the parser", r"T-001 wire the parser a \| b"),
            encoding="utf-8",
        )
        assert "board.ticket.field" not in rules(grade(project))

    def test_ticket_without_t_number(self, project):
        path = project / ".saipen" / "BOARD.md"
        path.write_text(
            read_doc(path).replace("## BLOCKED\n", "## BLOCKED\n- [ ] fixme later\n"),
            encoding="utf-8",
        )
        assert "board.ticket.id" in rules(grade(project))


class TestParseBoardStrict:
    def test_line_numbers_are_reported(self):
        tickets, headings, problems = parse_board_strict(GOOD_BOARD)
        assert tickets["T-001"].line_no == 3
        assert tickets["T-001"].section == "DOING"
        assert tickets["T-002"].needs == ["T-001"]
        assert headings == ["DOING", "TODO", "DONE", "BLOCKED"]
        assert problems == []


class TestCross:
    def test_task_names_a_ticket_that_does_not_exist(self, project):
        set_state(project, task="T-777")
        assert "cross.task.unknown" in rules(grade(project))

    def test_task_not_in_doing_is_a_failure(self, project):
        set_state(project, task="T-002")
        report = grade(project)
        assert "cross.task.doing.once" in rules(report)
        assert report.verdict == "fail"

    def test_done_ticket_as_active_task_is_a_failure(self, project):
        set_state(project, task="T-000")
        report = grade(project)
        assert "cross.task.done" in rules(report)
        assert report.verdict == "fail"

    def test_empty_doing_with_active_task_is_a_failure(self, project):
        board = project / ".saipen" / "BOARD.md"
        board.write_text(
            "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n",
            encoding="utf-8",
        )
        report = grade(project)
        assert "cross.task.doing.empty" in rules(report)
        assert report.verdict == "fail"

    def test_ship_naming_a_done_ticket_is_a_failure(self, project):
        set_state(project, phase="REVIEW", transition_from="VERIFY")
        set_state(project, next_action='"PHASE SHIP T-000"')
        report = grade(project)
        assert "cross.ship.done" in rules(report)
        assert report.verdict == "fail"

    def test_ship_naming_a_claimed_ticket_is_clean(self, project):
        set_state(project, phase="REVIEW", transition_from="VERIFY")
        set_state(project, next_action='"PHASE SHIP T-001"')
        report = grade(project)
        assert "cross.ship.done" not in rules(report)

    def test_done_with_empty_todo_must_not_wait(self, project):
        board = project / ".saipen" / "BOARD.md"
        board.write_text(
            "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
        )
        set_state(
            project,
            phase="DONE",
            transition_from="SHIP",
            task="none",
            next_action='"WAIT: blocked -- what next"',
        )
        assert "cross.done.wait" in rules(grade(project))

    @pytest.mark.parametrize("cat", ["user brake", "safety valve"])
    def test_the_two_legal_waits_at_done(self, project, cat):
        board = project / ".saipen" / "BOARD.md"
        board.write_text(
            "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
        )
        set_state(
            project,
            phase="DONE",
            transition_from="SHIP",
            task="none",
            next_action=f'"WAIT: {cat} -- the human decides"',
        )
        assert "cross.done.wait" not in rules(grade(project))

    def test_markhunt_blocked_keeps_the_board_alive(self, project):
        board = project / ".saipen" / "BOARD.md"
        board.write_text(
            "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n"
            "## BLOCKED\n- [ ] T-005 [MARKHUNT] triage me\n",
            encoding="utf-8",
        )
        set_state(
            project,
            phase="DONE",
            transition_from="SHIP",
            task="none",
            next_action='"WAIT: blocked -- triage the MARKHUNT tickets"',
        )
        assert "cross.done.wait" not in rules(grade(project))


class TestLog:
    def test_out_of_order_events(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-9] RUN: a\n- 27.07.26 11:00 [E-4] RUN: b\n",
            encoding="utf-8",
        )
        assert "log.event.order" in rules(grade(project))

    def test_duplicate_event(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-3] RUN: a\n- 27.07.26 11:00 [E-3] RUN: b\n",
            encoding="utf-8",
        )
        assert "log.event.duplicate" in rules(grade(project))

    def test_undated_entry_warns(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- [E-1] RUN: no stamp at all\n", encoding="utf-8"
        )
        report = grade(project)
        assert "log.timestamp.missing" in rules(report)
        assert report.verdict == "warn"

    def test_future_timestamp(self, project):
        ahead = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            days=2
        )
        (project / ".saipen" / "LOG.md").write_text(
            f"# Log\n\n- {ahead.strftime('%d.%m.%y %H:%M')} [E-1] RUN: tomorrow\n",
            encoding="utf-8",
        )
        assert "log.timestamp.future" in rules(grade(project))

    def test_line_that_is_not_an_entry_at_all(self, project):
        # The gap that let this grader pass a project `tools/validate.py`
        # FAILed: it only looked at lines already carrying an [E-###], so a
        # line that was not an entry was invisible rather than wrong. Found
        # when a stray newline split one of this project's own LOG entries.
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-1] RUN: fine\n"
            "- and then the rest of that entry ended up on its own line\n",
            encoding="utf-8",
        )
        assert "log.skeleton" in rules(grade(project))

    def test_html_comment_is_an_annotation_not_a_malformed_entry(self, project):
        # An HTML comment is a note ABOUT the log, not an entry in it. Demanding
        # the Event Graph skeleton from one is a grader bug: FastPrompter's LOG
        # carries a 16-line `<!-- RECOVERY SPLICE ... -->` block explaining that
        # a saitranslate INIT bootstrap had overwritten BOARD/LOG/STATE, and the
        # grader reported all 16 lines as failures for having the wrong shape --
        # punishing exactly the kind of note a human most needs to leave.
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n"
            "<!-- ====================================== -->\n"
            "<!-- RECOVERY SPLICE 25.07.26 -- a bootstrap -->\n"
            "<!-- overwrote BOARD.md, LOG.md and STATE.md -->\n"
            "<!-- ====================================== -->\n"
            "- 27.07.26 10:00 [E-1] RUN: fine\n",
            encoding="utf-8",
        )
        assert "log.skeleton" not in rules(grade(project))

    def test_multi_line_html_comment_body_is_skipped_too(self, project):
        # The body lines of a block comment carry no marker of their own, so an
        # opener must suppress until its `-->` or the middle lines get flagged.
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n"
            "<!--\n"
            "- 27.07.26 this looks like an entry but is inside a comment\n"
            "-->\n"
            "- 27.07.26 10:00 [E-1] RUN: fine\n",
            encoding="utf-8",
        )
        assert "log.skeleton" not in rules(grade(project))

    def test_a_real_bad_line_after_a_comment_still_fails(self, project):
        # The skip must not swallow the rest of the file: closing the comment
        # has to re-arm the check, or this fix would blind the grader entirely.
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n"
            "<!-- a note -->\n"
            "- 27.07.26 10:00 [E-1] RUN: fine\n"
            "- and then a stray fragment\n",
            encoding="utf-8",
        )
        assert "log.skeleton" in rules(grade(project))

    def test_prose_bullet_is_not_an_entry(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- just some notes I left here\n", encoding="utf-8"
        )
        assert "log.skeleton" in rules(grade(project))

    def test_headings_and_blanks_are_not_entries(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n## 2026\n\n- 27.07.26 10:00 [E-1] RUN: fine\n", encoding="utf-8"
        )
        assert "log.skeleton" not in rules(grade(project))

    def test_nonstandard_taxonomy_warns(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-1] DONE: closed a ticket\n", encoding="utf-8"
        )
        report = grade(project)
        assert "log.taxonomy" in rules(report)
        assert report.verdict == "warn"

    @pytest.mark.parametrize("verb", ["RUN", "DEC", "H"])
    def test_the_three_legal_verbs(self, project, verb):
        (project / ".saipen" / "LOG.md").write_text(
            f"# Log\n\n- 27.07.26 10:00 [E-1] {verb}: something\n", encoding="utf-8"
        )
        assert "log.taxonomy" not in rules(grade(project))

    def test_bad_ticket_reference_warns(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-1] [T-039,T-040] RUN: two at once\n",
            encoding="utf-8",
        )
        assert "log.ticket_ref" in rules(grade(project))

    def test_t_none_is_a_legal_reference(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-1] [T-none] RUN: maintenance\n",
            encoding="utf-8",
        )
        assert "log.ticket_ref" not in rules(grade(project))

    def test_replacement_character(self, project):
        (project / ".saipen" / "LOG.md").write_text(
            "# Log\n\n- 27.07.26 10:00 [E-1] RUN: corrupted � text\n",
            encoding="utf-8",
        )
        assert "log.replacement_char" in rules(grade(project))

    def test_missing_log_is_a_warning(self, project):
        (project / ".saipen" / "LOG.md").unlink()
        report = grade(project)
        assert "log.missing" in rules(report)
        assert report.verdict == "warn"


class TestReportShape:
    def test_fails_sort_above_warns(self, project):
        set_state(project, next_action='"do whatever"', task="T-002")
        report = grade(project)
        severities = [f.severity for f in report.findings]
        assert severities == sorted(severities, key=lambda s: s != "fail")

    def test_dict_is_json_shaped(self, project):
        import json

        d = grade(project).to_dict()
        assert set(d) == {"verdict", "fails", "warns", "baseline", "findings"}
        json.dumps(d)  # must survive the pywebview bridge
