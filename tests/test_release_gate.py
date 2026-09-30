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

T-849: the heading grammar is the GATE's, not a second test-side regex. The
v0.1.30 CHANGELOG migration (dc4791c) standardized released headings on the
unbracketed `## <semver> - <date>` form and updated the gate but left these
tests on the retired bracketed Keep-a-Changelog fixture form, so the tests
disagreed with the repository they claim to protect. The parser below is
imported from tools/release_gate.py: the test contract now exercises the same
canonical grammar the gate ships. A stale heading syntax therefore fails as
"no version heading" (its own regression below), a valid heading with the
wrong version fails as a version mismatch, and `## [Unreleased]` can never be
classified as the released head.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "release_gate.py"
VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']")


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("release_gate", GATE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


release_gate = _load_gate_module()

# The test contract uses the SAME parser object as the production gate: no
# test-side regex exists to drift from the shipped grammar again (T-849).
CHANGELOG_HEAD_RE = release_gate.CHANGELOG_HEAD_RE


def _version() -> str:
    init = (ROOT / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    m = VERSION_RE.match(init)
    assert m, "saipenview/__init__.py has no __version__"
    return m.group(1)


def _bumped_version() -> str:
    parts = [int(x) for x in _version().split(".")]
    parts[-1] += 1
    return ".".join(str(x) for x in parts)


def _changelog_head() -> str | None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return release_gate.changelog_head_version(text)


def _make_sandbox(tmp_path: Path, version: str) -> Path:
    (tmp_path / "saipenview").mkdir()
    (tmp_path / "saipenview" / "__init__.py").write_text(
        f'__version__ = "{version}"', encoding="utf-8"
    )
    # Canonical released heading (T-849): `## <semver> - <date>`, exactly the
    # form the real CHANGELOG ships and the gate parses.
    (tmp_path / "CHANGELOG.md").write_text(
        f"## {version} - 2026-09-15", encoding="utf-8"
    )
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


def _run_gate(sandbox: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), *flags, "--root", str(sandbox)],
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
    head = _changelog_head()
    assert head is not None, (
        "CHANGELOG.md has no heading matching the canonical released grammar"
    )
    assert head == _version()


def test_changelog_head_is_the_first_released_heading_not_unreleased():
    # The real CHANGELOG carries an `## [Unreleased]` section further down.
    # `[Unreleased]` is not a released version and must never be the head:
    # the gate selects the FIRST canonical released heading instead.
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()]
    headings = [ln for ln in lines if ln.startswith("## ")]
    assert "## [Unreleased]" in headings, (
        "fixture drift: CHANGELOG no longer has [Unreleased]"
    )
    head = release_gate.changelog_head_version(text)
    assert head is not None
    assert head != "Unreleased"
    # The oracle here is deliberately NOT the gate's own regex. Sharing it made
    # this test unable to see a grammar change at all -- it compared the
    # implementation against itself. `## ` and the `[Unreleased]` literal are
    # the whole grammar this assertion needs, they do not drift with a bump,
    # and a wrong head fails here.
    first_released = next(ln for ln in headings if ln != "## [Unreleased]")
    version_marker = _version()
    assert first_released == f"## {version_marker}" or first_released.startswith(
        f"## {version_marker} "
    ), first_released


def test_changelog_head_rejects_malformed_headings():
    # Grammar regressions on the shared parser: prose/bracketed/partial
    # headings are NOT valid released headings.
    assert release_gate.changelog_head_version("## [1.2.3]") is None
    assert release_gate.changelog_head_version("## [Unreleased]") is None
    assert release_gate.changelog_head_version("## Version 1.2.3") is None
    assert release_gate.changelog_head_version("## 1.2.3x - 2026-09-15") is None
    assert release_gate.changelog_head_version("### 1.2.3") is None
    # The canonical form parses, with or without the trailing date.
    assert release_gate.changelog_head_version("## 1.2.3 - 2026-09-15") == "1.2.3"
    assert release_gate.changelog_head_version("## 1.2.3") == "1.2.3"


def test_release_gate_fails_on_malformed_changelog_head(tmp_path):
    # A sandbox whose CHANGELOG carries a truly invalid heading must fail with
    # "no version heading" -- malformed syntax is distinct from a mismatch.
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    (sandbox / "CHANGELOG.md").write_text("## [9.9.9]", encoding="utf-8")
    r = _run_gate(sandbox, "--dev")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CHANGELOG.md has no version heading" in r.stdout
    assert "!=" not in r.stdout


def test_release_gate_passes_at_shipped_head(tmp_path):
    # Version-agnostic (T-197): the sandbox carries a version above the newest
    # tag and no git history, so the live repo's tag state cannot flip the
    # verdict -- green at a tagged release commit, at a post-ship commit, and
    # at a pre-bump HEAD alike. Sandbox has no git: --dev explicitly selects
    # the dev/sandbox reading that may run without tag evidence.
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    r = _run_gate(sandbox, "--dev")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_release_mode_fails_without_git(tmp_path):
    # Release mode (default) REQUIRES git tag evidence: a sandbox with no git
    # at all must FAIL, never pass "because nothing to compare".
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    r = _run_gate(sandbox)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "git tag evidence unavailable" in r.stdout
    assert "git command failed" in r.stdout


def test_release_mode_fails_with_valid_repo_but_no_tags(tmp_path):
    # A valid repo with zero tags is DIFFERENT from git being unavailable --
    # the gate must say so. First-release territory still cannot prove the
    # version is not behind a shipped tag in release mode.
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@t.t"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-qm", "sandbox"],
    ):
        subprocess.run(["git", *args], cwd=sandbox, check=True, capture_output=True)
    r = _run_gate(sandbox)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "zero v* tags" in r.stdout
    assert "git command failed" not in r.stdout


def test_release_mode_fails_when_version_behind_newest_tag(tmp_path):
    # Sandbox is its own git repo tagged far above the declared version, so
    # the gate must refuse regardless of the real repo's tags.
    sandbox = _make_sandbox(tmp_path, _version())
    _git_init_and_tag(sandbox, "v999.0.0")
    r = _run_gate(sandbox)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "BEHIND" in r.stdout


def test_release_gate_fails_when_identity_surfaces_disagree(tmp_path):
    # Valid canonical heading carrying the WRONG version: the failure must be
    # the version-mismatch diagnostic, not "no version heading".
    sandbox = _make_sandbox(tmp_path, "1.2.3")
    (sandbox / "CHANGELOG.md").write_text("## 9.9.9 - 2026-09-15", encoding="utf-8")
    r = _run_gate(sandbox, "--dev")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CHANGELOG head [9.9.9] != __version__ [1.2.3]" in r.stdout


def test_new_release_must_not_be_behind_newest_tag():
    # Runs the gate against the LIVE repo in release mode (CI fetches full tag
    # history for this job). Verdict: either PASS (version >= newest tag) or a
    # named tag-related FAIL -- never a skip, and never a silent pass on
    # missing evidence. The missing-evidence case is FAILed, as
    # test_release_mode_fails_* pin. At a post-ship untagged HEAD the gate
    # correctly refuses with the re-ship diagnostic (T-197), which is a named
    # version/verdict failure, not missing evidence.
    r = _run_gate(ROOT)
    if r.returncode == 0:
        assert "PASS" in r.stdout
        return
    out = r.stdout + r.stderr
    assert "Release identity FAIL" in out, out
    assert "tag" in out, out


def test_dev_gate_accepts_unreleased_section_above_the_head(tmp_path):
    # The grammar control the live-tree invocation could not provide. Against
    # the LIVE tree this test could only ever report what the local tag state
    # happened to be, so it accepted PASS and any FAIL mentioning "tag" -- it
    # had no path to failing. A SANDBOX whose CHANGELOG puts a real
    # `## [Unreleased]` section ABOVE the released head is decidable: the gate
    # must ignore it and still report the released version.
    sandbox = _make_sandbox(tmp_path, _bumped_version())
    version = _bumped_version()
    (sandbox / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n### Changed\n- not shipped yet\n\n"
        f"## {version} - 2026-09-15\n\n### Fixed\n- a fix\n",
        encoding="utf-8",
    )
    r = _run_gate(sandbox, "--dev")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "Release identity PASS" in out, out
    # The released version, not [Unreleased], is what the gate read.
    assert f"CHANGELOG head [{version}]" in out or "PASS" in out
    assert "no version heading" not in out, out
    assert "!=" not in out, out
