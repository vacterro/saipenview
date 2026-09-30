"""T-896: the freshness authority is the project's DECLARED home, not whatever
SAIPEN_HOME the ambient shell happens to export.

`saio.source_identity` resolves the project's `saipen_home` correctly, then
hands that home to `_freshness_module` as if it were a project ROOT. The SAIPEN
repo carries no `.saipen/STATE.md`, so the root-branch re-resolution failed,
control fell through to the env branch, and the identity was computed by a
different protocol version than the one the project is pinned to -- or, on a
machine with two installs, the second load raised MULTI-HOME CONTAMINATION and
broke every collect call.
"""

from __future__ import annotations

import pytest
from conftest import make_conformant_project

from saipenview import saio

# A second install that must never be consulted for this project.
_OTHER_HOME_FRESHNESS = """
def compute_source_identity(root):
    return "FROM-THE-OTHER-HOME"

def compute_role_revision(path):
    return "FROM-THE-OTHER-HOME"

def compute_generic_role_revision(path):
    return "FROM-THE-OTHER-HOME"
"""


@pytest.fixture
def other_home(tmp_path, monkeypatch):
    """Publish a second, reachable SAIPEN install via the environment.

    Deliberately NOT applied before the warm-up call: the defect is that a
    warm process re-resolves and follows the env, so the test must let the
    declared home win FIRST and then pull the env out from under it.
    """
    home = tmp_path / "other-install"
    (home / "tools").mkdir(parents=True)
    (home / "tools" / "freshness.py").write_text(_OTHER_HOME_FRESHNESS, encoding="utf-8")
    return home, lambda: monkeypatch.setenv("SAIPEN_HOME", str(home))


def test_source_identity_ignores_the_ambient_saipen_home(tmp_path, other_home):
    root = make_conformant_project(tmp_path)
    declared = saio.source_identity(root)
    assert getattr(declared, "source_head", declared)

    _home, expose = other_home
    expose()

    # Before the fix the second call re-resolved the home as a root, fell to the
    # env branch and raised MULTI-HOME CONTAMINATION.
    assert saio.source_identity(root) == declared


def test_role_revision_ignores_the_ambient_saipen_home(tmp_path, other_home):
    """The charter sits under the project, so its home is the declared one."""
    root = make_conformant_project(tmp_path)
    subs = root / ".saipen" / "extensions" / "subs"
    subs.mkdir(parents=True)
    charter = subs / "saihunt.md"
    charter.write_text(
        "# saihunt charter\n```yaml\nrole_revision: fixture\n```\n",
        encoding="utf-8",
    )
    declared = saio.role_revision(charter)
    assert declared and declared != "FROM-THE-OTHER-HOME"

    _home, expose = other_home
    expose()

    assert saio.role_revision(charter) == declared