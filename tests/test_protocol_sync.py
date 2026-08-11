"""Proves `saipenview/protocol.py` still matches the protocol it copied from.

Every set in `protocol.py` is a duplicate of a list that is normative
somewhere else. Duplicates drift. This reads the canonical sources when the
SAIPEN repo is reachable on this machine and compares them field by field.

On a machine without the repo it SKIPS -- and the skip is the point of the
design, not a hole in it: the viewer is allowed to lag the protocol, it is not
allowed to lag it quietly, so `protocol.BASELINE_VERSION` is shown next to
every verdict the UI renders.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest

from saipenview import protocol

# Where the protocol repo lives on this machine. saipen_home in a STATE.md
# points at a deployed copy of `saipen/` only; the schema and the validator
# live one level up in the source repo, so those are searched separately.
# The engine modules moved the validator's phase/board/log vocabularies into
# tools/saipen_engine/ (NITRO M1) -- the 7.2xx cycle, after which the old
# "grep tools/validate.py for the constant" sync broke with a TypeError. The
# vocabulary's HOME is now the engine module; validate.py imports from it.
_CANDIDATE_ROOTS = [
    Path(r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN"),
    Path.home() / ".claude" / "skills" / "saipen",
]
if os.environ.get("SAIPEN_HOME"):
    _CANDIDATE_ROOTS.insert(0, Path(os.environ["SAIPEN_HOME"]))


def _find(*relative: str) -> Path | None:
    for root in _CANDIDATE_ROOTS:
        for rel in relative:
            candidate = root / rel
            if candidate.is_file():
                return candidate
    return None


@pytest.fixture(scope="module")
def schema():
    path = _find("extensions/schemas/state.schema.json")
    if path is None:
        pytest.skip("SAIPEN repo not on this machine: state.schema.json not found")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator_src():
    path = _find("tools/validate.py")
    if path is None:
        pytest.skip("SAIPEN repo not on this machine: tools/validate.py not found")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def engine_src():
    """The four engine modules the validator imports its vocabularies from."""
    names = {
        "phases": "tools/saipen_engine/phases.py",
        "board": "tools/saipen_engine/board.py",
        "log": "tools/saipen_engine/log.py",
    }
    out = {}
    for key, rel in names.items():
        path = _find(rel)
        if path is None:
            pytest.skip(f"SAIPEN repo not on this machine: {rel} not found")
        out[key] = path.read_text(encoding="utf-8")
    return out


def _literal(src: str, name: str):
    """Pull a module-level literal assignment out of the given source.

    Parsing beats importing: `tools/validate.py` runs its checks at import
    time against whatever `.saipen/` it is standing in.
    """
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            else:
                targets = node.targets
                value = node.value
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == name
                    and value is not None
                ):
                    if (
                        isinstance(value, ast.Call)
                        and getattr(value.func, "id", None) == "frozenset"
                    ):
                        return ast.literal_eval(value.args[0])
                    return ast.literal_eval(value)
    return None


def _nested_literal(src: str, name: str):
    """Same, but for a name assigned inside a function body -- several of the
    validator's vocabularies are local to the check that uses them."""
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        continue
    return None


def _taxonomy_read_allowance(src: str) -> frozenset[str]:
    """The validator's read-side taxonomy allowance.

    It is not a named constant -- it is the literal compared against in
    `if taxonomy not in ("RUN", "DEC", "H"):`. Extract that comparison so the
    viewer's LOG_READ_TAXONOMIES is mechanical, not re-typed.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not (
            isinstance(node.left, ast.Name)
            and node.left.id == "taxonomy"
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.NotIn)
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Tuple)
        ):
            continue
        return frozenset(
            elt.value
            for elt in node.comparators[0].elts
            if isinstance(elt, ast.Constant)
        )
    raise AssertionError("taxonomy-not-in allowance not found in validator")


def _checkbox_sections(src: str) -> dict[str, tuple[str, ...]]:
    """The checkbox-vs-section pairing from the validator's ticket loop.

    Same shape the protocol writes it in: ' ' -> (TODO, BLOCKED), '/' -> DOING,
    'x' -> DONE. Extracted mechanically from the three FAIL statements that
    own the rule.
    """
    pairs = {
        "x": re.search(r't\["checkbox"\] == "x" and t\["section"\] != "## DONE"', src),
        "/": re.search(r't\["checkbox"\] == "/" and t\["section"\] != "## DOING"', src),
        " ": re.search(
            r't\["checkbox"\] in \(" ", ""\) and t\["section"\] in '
            r'\("## DONE", "## DOING"\)',
            src,
        ),
    }
    missing = [k for k, m in pairs.items() if m is None]
    assert not missing, f"checkbox rule for {missing} not found in validator"
    return {
        "x": ("DONE",),
        "/": ("DOING",),
        " ": ("TODO", "BLOCKED"),
    }


class TestAgainstSchema:
    def test_phase_enum(self, schema):
        assert set(protocol.PHASES) == set(schema["properties"]["phase"]["enum"])

    def test_transition_from_enum(self, schema):
        assert set(protocol.PHASES) == set(
            schema["properties"]["transition_from"]["enum"]
        )

    def test_modes(self, schema):
        assert set(protocol.MODES) == set(schema["properties"]["mode"]["enum"])

    def test_execution_intents(self, schema):
        assert set(protocol.EXECUTION_INTENTS) == set(
            schema["properties"]["execution_intent"]["enum"]
        )

    def test_required_fields(self, schema):
        # The schema names eight; transition_from is the ninth and carries its
        # own fresh-INIT exception, so it is required by the RFC and by the
        # portable floor but cannot be a plain `required` entry here.
        assert set(schema["required"]) | {"transition_from"} == set(
            protocol.REQUIRED_STATE_FIELDS
        )

    def test_current_schema_version(self, schema):
        assert protocol.STATE_SCHEMA_VERSION == schema["x-current-schema-version"]


class TestAgainstValidator:
    def test_outbox_statuses(self, validator_src):
        assert set(protocol.OUTBOX_STATUSES) == set(
            _literal(validator_src, "OUTBOX_STATUSES")
        )

    def test_saipen_commands(self, validator_src):
        canon = _literal(validator_src, "SAIPEN_COMMANDS")
        assert canon is not None, "the § 1.10 command set not found in validator"
        assert protocol.SAIPEN_COMMANDS == frozenset(canon)

    def test_package_handoff_fields(self, validator_src):
        canon = _literal(validator_src, "PACKAGE_HANDOFF_FIELDS")
        assert canon is not None, "PACKAGE_HANDOFF_FIELDS not found in validator"
        assert set(protocol.PACKAGE_HANDOFF_FIELDS) == set(canon)

    def test_log_clock_slack(self, validator_src):
        canon = _nested_literal(validator_src, "LOG_CLOCK_SLACK")
        assert canon is not None, "LOG_CLOCK_SLACK not found in validator"
        assert protocol.LOG_CLOCK_SLACK_SECONDS == canon

    def test_log_read_taxonomies(self, validator_src):
        assert protocol.LOG_READ_TAXONOMIES == _taxonomy_read_allowance(validator_src)

    def test_checkbox_sections(self, validator_src):
        assert protocol.CHECKBOX_SECTIONS == _checkbox_sections(validator_src)


class TestAgainstEngine:
    def test_valid_transitions(self, engine_src):
        canon = _literal(engine_src["phases"], "VALID_TRANSITIONS")
        mine = {k: list(v) for k, v in protocol.VALID_TRANSITIONS.items()}
        assert {k: sorted(v) for k, v in mine.items()} == {
            k: sorted(v) for k, v in canon.items()
        }

    def test_any_from(self, engine_src):
        canon = _literal(engine_src["phases"], "ANY_FROM")
        assert canon is not None, "ANY_FROM not found in saipen_engine/phases.py"
        assert set(protocol.ANY_FROM) == set(canon)

    def test_ticket_bearing_phases(self, engine_src):
        canon = _literal(engine_src["phases"], "TICKET_BEARING_PHASES")
        assert canon is not None, "TICKET_BEARING_PHASES not found in phases.py"
        assert set(protocol.TICKET_PHASES) == set(canon)

    def test_ticket_fields(self, engine_src):
        canon = _literal(engine_src["board"], "KNOWN_FIELDS")
        assert canon is not None, "KNOWN_FIELDS not found in saipen_engine/board.py"
        assert set(protocol.TICKET_FIELDS) == set(canon)

    def test_board_headings(self, engine_src):
        canon = _literal(engine_src["board"], "REQUIRED_HEADINGS")
        assert canon is not None, "REQUIRED_HEADINGS not found in board.py"
        assert set(protocol.BOARD_HEADINGS) == {h.removeprefix("## ") for h in canon}

    def test_log_taxonomies(self, engine_src):
        canon = _literal(engine_src["log"], "VALID_TAXONOMIES")
        assert canon is not None, "VALID_TAXONOMIES not found in saipen_engine/log.py"
        assert set(protocol.LOG_TAXONOMIES) == set(canon)


class TestAgainstValidatorNested:
    """Vocabularies still local to a validator check body."""

    def test_read_only_banned_phases(self, validator_src):
        canon = _nested_literal(validator_src, "READ_ONLY_BANNED_PHASES")
        assert canon is not None, "READ_ONLY_BANNED_PHASES not found in validator"
        assert set(protocol.READ_ONLY_BANNED_PHASES) == set(canon)

    def test_wait_categories(self, validator_src):
        canon = _nested_literal(validator_src, "WAIT_CATEGORIES")
        assert canon is not None, "WAIT_CATEGORIES not found in validator"
        assert set(protocol.WAIT_CATEGORIES) == set(canon)

    def test_next_action_prefixes(self, validator_src):
        canon = _nested_literal(validator_src, "executable_prefixes")
        assert canon is not None, "executable_prefixes not found in validator"
        assert set(protocol.NEXT_ACTION_PREFIXES) == set(canon)

    def test_goal_caps(self, validator_src):
        assert protocol.GOAL_WAVE_CAP == _nested_literal(validator_src, "GOAL_WAVE_CAP")
        assert protocol.GOAL_TICKET_CAP == _nested_literal(
            validator_src, "GOAL_TICKET_CAP"
        )


class TestBaselineDeclared:
    def test_baseline_is_a_version(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", protocol.BASELINE_VERSION)

    def test_baseline_matches_the_repo_when_reachable(self):
        path = _find("VERSION")
        if path is None:
            pytest.skip("SAIPEN repo not on this machine: VERSION not found")
        repo = path.read_text(encoding="utf-8").strip()
        assert protocol.BASELINE_VERSION == repo, (
            f"viewer graded against {protocol.BASELINE_VERSION}, repo is at "
            f"{repo} -- re-read the vocabularies in saipenview/protocol.py "
            f"and bump BASELINE_VERSION"
        )
