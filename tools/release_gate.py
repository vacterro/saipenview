"""T-188 release identity gate.

The version has ONE source of truth -- `saipenview/__init__.py`, derived into
the wheel by pyproject's dynamic version -- and a release must not drift the
four places that can disagree. This tool checks, in this order:

1. pyproject declares the version as dynamic (single source, no static copy).
2. `saipenview.__version__` matches the CHANGELOG head heading.
3. The git tag identity: a release ships as `v<version>`; if HEAD already
   carries that exact tag the release is a re-tag (allowed only for a
   re-push), if the version is behind the newest tag it is a regression, and
   a version equal to the newest tag is an attempt to re-ship an old release.

Exit 0 = the release identity is truthful. Non-zero = a mismatch, named.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_HEAD_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")
VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']")


def _version() -> str:
    init = ROOT / "saipenview" / "__init__.py"
    m = VERSION_RE.match(init.read_text(encoding="utf-8"))
    if not m:
        print(f"FAIL: {init} carries no __version__")
        sys.exit(2)
    return m.group(1)


def _changelog_head() -> str | None:
    text = ROOT / "CHANGELOG.md"
    for line in text.read_text(encoding="utf-8").splitlines():
        m = CHANGELOG_HEAD_RE.match(line.strip())
        if m:
            return m.group(1)
    return None


def _git(args: list[str]) -> str:
    r = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return (r.stdout or "").strip()


def _tags() -> list[str]:
    return _git(["tag", "-l", "v[0-9]*"]).splitlines()


def main() -> int:
    version = _version()
    problems: list[str] = []

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    proj_block = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    if re.search(r"^\s*version\s*=\s*[\"']", proj_block, re.MULTILINE):
        problems.append("pyproject still declares a static version; use dynamic")
    if 'dynamic = ["version"]' not in proj_block:
        problems.append("pyproject does not declare version as dynamic")

    head = _changelog_head()
    if head is None:
        problems.append("CHANGELOG.md has no version heading")
    elif head != version:
        problems.append(f"CHANGELOG head [{head}] != __version__ [{version}]")

    # Tag identity. Normalise the tag list to plain versions.
    tag_versions = sorted(
        (t[1:] for t in _tags() if re.match(r"^v\d+\.\d+\.\d+$", t)),
        key=lambda v: [int(x) for x in v.split(".")],
    )
    current_tag = _git(["tag", "--points-at", "HEAD"]).splitlines()
    v_tags = [t for t in current_tag if t == f"v{version}"]
    newest_tag = tag_versions[-1] if tag_versions else None

    if v_tags:
        pass  # HEAD is tagged with exactly this version: identity holds
    elif newest_tag == version:
        problems.append(
            f"version {version} equals the newest tag -- re-shipping an old release"
        )
    elif newest_tag and _cmp(newest_tag, version) > 0:
        problems.append(f"version {version} is BEHIND newest tag {newest_tag}")

    if problems:
        print("Release identity FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        f"Release identity PASS: __version__={version} changelog=[{head}] "
        f"tag={'v' + version if v_tags else '<new release, tag pending>'}"
    )
    return 0


def _cmp(a: str, b: str) -> int:
    av, bv = [int(x) for x in a.split(".")], [int(x) for x in b.split(".")]
    return (av > bv) - (av < bv)


if __name__ == "__main__":
    sys.exit(main())
