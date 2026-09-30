"""Repository hygiene: no scratch twins of shipped package sources.

``saipenview/git_diff.py.fixed`` shipped beside a byte-identical
``saipenview/git_diff.py``. Nothing imported it, but it lived inside the
installed package next to the real module, so it invited editing the wrong file
and would be picked up by any wildcard packaging or import rule. A copy of a
source file is not a source file: this assertion keeps the next one from
surviving review.

Two rules, deliberately different in strength:

1. A scratch copy of a **Python module** inside the package is always a defect.
   It is the one shape that can shadow or be shadowed by real import machinery,
   and no integration legitimately parks one there.
2. Any other scratch-suffixed file is tolerated only when the repository
   explicitly ignores it. ``.gitignore`` documents exactly one such case --
   ``*.bak``, because Wintage's installer parks a superseded
   ``ui/static/style.css.bak`` when it refreshes one (``.gitignore`` line 71,
   SAIPEN T-142). An *unignored* leftover is a defect; an ignored, documented
   external artifact is not this repository's to delete.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "saipenview"
ROOT = PACKAGE.parent

SCRATCH_SUFFIXES = (".fixed", ".orig", ".rej", ".bak", ".save", ".old", ".new")
SCRATCH_PREFIXES = (".#", "#")
SKIP_DIRS = {"__pycache__"}


def _scratch_artifacts() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        name = path.name
        if (
            name.endswith(SCRATCH_SUFFIXES)
            or name.endswith("~")
            or name.startswith(SCRATCH_PREFIXES)
        ):
            found.append(path)
    return found


def _is_ignored(path: pathlib.Path) -> bool:
    if shutil.which("git") is None:  # pragma: no cover - git is a suite dependency
        pytest.skip("git not available")
    r = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", "--", str(path)],
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


def test_python_module_scratch_twins_never_ship():
    """``module.py.fixed`` next to ``module.py``: the CORE-001 hygiene defect."""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _scratch_artifacts()
        if ".py." in path.name or path.name.endswith(".py~")
    ]
    assert offenders == [], (
        "a scratch copy of a Python module must never live inside saipenview/: "
        + ", ".join(offenders)
    )


def test_other_scratch_artifacts_are_explicitly_ignored():
    """Tolerate only what the repository documents as externally produced."""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _scratch_artifacts()
        if not (".py." in path.name or path.name.endswith(".py~"))
        and not _is_ignored(path)
    ]
    assert offenders == [], (
        "unignored scratch artifacts inside saipenview/ (delete them, or "
        "document why an external tool parks them here): " + ", ".join(offenders)
    )


def test_git_diff_has_no_fixed_twin():
    """The specific artifact CORE-001 was closed over."""
    assert not (PACKAGE / "git_diff.py.fixed").exists()
    assert (PACKAGE / "git_diff.py").is_file()
