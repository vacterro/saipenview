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


def _literal(src: str, name: str):
    """Pull a module-level literal assignment out of the validator source.

    Parsing beats importing: `tools/validate.py` runs its checks at import
    time against whatever `.saipen/` it is standing in.
    """
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(node.value, ast.Call) and getattr(node.value.func, "id", None) == "frozenset":
                        return ast.literal_eval(node.value.args[0])
                    return ast.literal_eval(node.value)
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


class TestAgainstSchema:
    def test_phase_enum(self, schema):
        assert set(protocol.PHASES) == set(schema["properties"]["phase"]["enum"])

    def test_transition_from_enum(self, schema):
        assert set(protocol.PHASES) == set(
            schema["properties"]["transition_from"]["enum"]
        )

    def test_modes(self, schema):
        assert set(protocol.MODES) == set(schema["properties"]["mode"]["enum"])

    def test_required_fields(self, schema):
        # The schema names eight; transition_from is the ninth and carries its
        # own fresh-INIT exception, so it is required by the RFC and by the
        # portable floor but cannot be a plain `required` entry here.
        assert set(schema["required"]) | {"transition_from"} == set(
            protocol.REQUIRED_STATE_FIELDS
        )


class TestAgainstValidator:
    def test_outbox_statuses(self, validator_src):
        assert set(protocol.OUTBOX_STATUSES) == set(
            _literal(validator_src, "OUTBOX_STATUSES")
        )

    def test_any_from(self, validator_src):
        assert set(protocol.ANY_FROM) == set(_literal(validator_src, "ANY_FROM"))

    def test_valid_transitions(self, validator_src):
        canon = _literal(validator_src, "VALID_TRANSITIONS")
        mine = {k: list(v) for k, v in protocol.VALID_TRANSITIONS.items()}
        assert {k: sorted(v) for k, v in mine.items()} == {
            k: sorted(v) for k, v in canon.items()
        }

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

    def test_saipen_commands(self, validator_src):
        canon = _literal(validator_src, "SAIPEN_COMMANDS")
        assert canon is not None, "the § 1.10 command set not found in validator"
        assert protocol.SAIPEN_COMMANDS == frozenset(canon)

    def test_goal_caps(self, validator_src):
        assert protocol.GOAL_WAVE_CAP == _nested_literal(validator_src, "GOAL_WAVE_CAP")
        assert protocol.GOAL_TICKET_CAP == _nested_literal(
            validator_src, "GOAL_TICKET_CAP"
        )

    def test_board_headings(self, validator_src):
        canon = _nested_literal(validator_src, "REQUIRED_HEADINGS")
        assert canon is not None
        assert set(protocol.BOARD_HEADINGS) == {
            h.removeprefix("## ") for h in canon
        }


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
