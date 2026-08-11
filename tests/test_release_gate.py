"""T-188/T-197: the release identity gate and the single version source.

v0.1.18..v0.1.20 shipped tags while pyproject/__init__ stayed at 0.1.17, so a
wheel carried METADATA that named the wrong release. These tests pin the
replacement: one version source (saipenview.__version__, derived dynamically)
and a gate that fails whenever the four identity surfaces disagree.

T-197: test_release_gate_passes used to assert exit 0 against the LIVE repo,
which is state-dependent -- at any untagged commit after a shipped release the
version equals the newest tag and the gate correctly refuses ("re-shipping an
old release"), so the test went red until the next bump. The pass assertion
now runs the gate against a sandboxed tree with a bumped version, so it is
green at every HEAD; the two failure modes are pinned by their own sandboxed
tests.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "release_gate.py"
VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']")
CHANGELOG_HEAD_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")


def _version() -> str:
    init = (ROOT / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    m = VERSION_RE.match(init)
    assert m, "saipenview/__init__.py has no __version__"
    return m.group(1)


def _bumped_version() -> str:
    parts = [int(x) for x in _version().split(".")]
    parts[-1] += 1
    return ".".join(str(x) for x in parts)


def _changelog_head() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        m = CHANGELOG_HEAD_RE.match(line.strip())
        if m:
            return m.group(1)
    raise AssertionError("CHANGELOG.md has no version heading")


def _make_sandbox(tmp_path: Path, version: str) -> Path:
    (tmp_path / "saipenview").mkdir()
    (tmp_path / "saipenview" / "__init__.py").write_text(
        f'__version__ = "{version}"', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(f"## [{version}]", encoding="utf-8")
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def _git_init_and_tag(path: Path, tag: str) -> None:
    for args in (
        ["init", "-q"],
        ["config", "user.email", "saipenview@test"],
        ["config", "user.name", "saipenview"],
        ["add", "-A"],
        ["commit", "-q", "-m", "sandbox"],
        ["tag", tag],
    ):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _run_gate(sandbox: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(sandbox)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


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


def test_release_gate_passes_at_shipped_head(tmp_path):
    # Version-agnostic (T-197): the sandbox carries a version above the newest
    # tag and no git history, so the live repo's tag state cannot flip the
    # verdict -- green at a tagged release commit, at a post-ship commit, and
    # at a pre-bump HEAD alike.
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    r = _run_gate(sandbox)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_release_gate_fails_when_version_behind_newest_tag(tmp_path):
    # Sandbox is its own git repo tagged far above the declared version, so
    # the gate must refuse regardless of the real repo's tags.
    sandbox = _make_sandbox(tmp_path, _version())
    _git_init_and_tag(sandbox, "v999.0.0")
    r = _run_gate(sandbox)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "BEHIND" in r.stdout


def test_release_gate_fails_when_identity_surfaces_disagree(tmp_path):
    sandbox = _make_sandbox(tmp_path, "1.2.3")
    (sandbox / "CHANGELOG.md").write_text("## [9.9.9]", encoding="utf-8")
    r = _run_gate(sandbox)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CHANGELOG head [9.9.9] != __version__ [1.2.3]" in r.stdout


def test_new_release_must_not_be_behind_newest_tag():
    tags = subprocess.run(
        ["git", "tag", "-l", "v[0-9]*"], capture_output=True, text=True, cwd=ROOT
    ).stdout.split()
    versions = [t[1:] for t in tags if re.match(r"^v\d+\.\d+\.\d+$", t)]
    if not versions:
        # A shallow CI checkout (actions/checkout@v4 without fetch-depth: 0)
        # has no tags at all, so there is no "newest tag" to be behind --
        # nothing to assert. Local clones carry the full tag history.
        pytest.skip("no release tags in this checkout (shallow CI clone)")

    def key(v):
        return [int(x) for x in v.split(".")]

    newest = max(versions, key=key)
    assert key(_version()) >= key(newest), (
        f"__version__ {_version()} is behind the newest tag {newest}"
    )
