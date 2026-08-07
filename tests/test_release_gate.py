"""T-188: the release identity gate and the single version source.

v0.1.18..v0.1.20 shipped tags while pyproject/__init__ stayed at 0.1.17, so a
wheel carried METADATA that named the wrong release. These tests pin the
replacement: one version source (saipenview.__version__, derived dynamically)
and a gate that fails whenever the four identity surfaces disagree.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']")
CHANGELOG_HEAD_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")


def _version() -> str:
    init = (ROOT / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    m = VERSION_RE.match(init)
    assert m, "saipenview/__init__.py has no __version__"
    return m.group(1)


def _changelog_head() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        m = CHANGELOG_HEAD_RE.match(line.strip())
        if m:
            return m.group(1)
    raise AssertionError("CHANGELOG.md has no version heading")


def test_version_has_one_source():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    proj_block = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    assert 'dynamic = ["version"]' in proj_block
    assert not re.search(r"^\s*version\s*=\s*[\"']", proj_block, re.MULTILINE), (
        "pyproject still declares a static version"
    )
    assert "[tool.setuptools.dynamic]" in pyproject
    assert 'version = {attr = "saipenview.__version__"}' in pyproject


def test_changelog_head_matches_version():
    assert _changelog_head() == _version()


def test_release_gate_passes():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "release_gate.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_new_release_must_not_be_behind_newest_tag():
    tags = subprocess.run(
        ["git", "tag", "-l", "v[0-9]*"], capture_output=True, text=True, cwd=ROOT
    ).stdout.split()
    versions = [t[1:] for t in tags if re.match(r"^v\d+\.\d+\.\d+$", t)]

    def key(v):
        return [int(x) for x in v.split(".")]

    newest = max(versions, key=key)
    assert key(_version()) >= key(newest), (
        f"__version__ {_version()} is behind the newest tag {newest}"
    )
