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

Tag evidence is REQUIRED in release mode (the default): a release cannot be
proven not-behind with missing evidence, so a git failure and a valid repo
with no tags are both FAILs -- reported differently. Dev/sandbox runs pass
`--dev` to operate without tag evidence explicitly selected.

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


def _version(root: Path) -> str:
    init = root / "saipenview" / "__init__.py"
    m = VERSION_RE.match(init.read_text(encoding="utf-8"))
    if not m:
        print(f"FAIL: {init} carries no __version__")
        sys.exit(2)
    return m.group(1)


def _changelog_head(root: Path) -> str | None:
    text = root / "CHANGELOG.md"
    for line in text.read_text(encoding="utf-8").splitlines():
        m = CHANGELOG_HEAD_RE.match(line.strip())
        if m:
            return m.group(1)
    return None


def _git(root: Path, args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, (r.stdout or "").strip()


def _tags(root: Path) -> list[str] | None:
    """Tag versions, or None when the git tag command itself FAILED (as
    opposed to a valid repo that happens to carry no tags, which is [])."""
    rc, out = _git(root, ["tag", "-l", "v[0-9]*"])
    if rc != 0:
        return None
    return out.splitlines()


def main() -> int:
    argv = sys.argv[1:]
    dev_mode = "--dev" in argv
    argv = [a for a in argv if a != "--dev"]
    if len(argv) == 2 and argv[0] == "--root":
        root = Path(argv[1])
    elif argv:
        print(f"usage: {sys.argv[0]} [--dev] [--root <repo-path>]")
        return 2
    else:
        root = ROOT

    version = _version(root)
    problems: list[str] = []

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    proj_block = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    if re.search(r"^\s*version\s*=\s*[\"']", proj_block, re.MULTILINE):
        problems.append("pyproject still declares a static version; use dynamic")
    if 'dynamic = ["version"]' not in proj_block:
        problems.append("pyproject does not declare version as dynamic")

    head = _changelog_head(root)
    if head is None:
        problems.append("CHANGELOG.md has no version heading")
    elif head != version:
        problems.append(f"CHANGELOG head [{head}] != __version__ [{version}]")

    # Tag identity. Release mode (default) REQUIRES tag evidence: a release
    # whose behind/equal status cannot be decided against shipped tags is not
    # provable, and "can't tell" is the one answer a gate must never give.
    # `--dev` explicitly selects the dev/sandbox reading that may run without
    # tags. git command failure and "valid repo, zero tags" are DIFFERENT
    # findings: one means no git, the other means first-release territory.
    tags = _tags(root)
    if tags is None:
        if not dev_mode:
            problems.append(
                "git tag evidence unavailable (git command failed) -- release "
                "mode cannot prove this version is not behind a shipped tag"
            )
    elif not tags:
        if not dev_mode:
            problems.append(
                "git tag evidence unavailable (valid repo, zero v* tags) -- "
                "release mode cannot prove this version is not behind a "
                "shipped tag"
            )
    else:
        tag_versions = sorted(
            (t[1:] for t in tags if re.match(r"^v\d+\.\d+\.\d+$", t)),
            key=lambda v: [int(x) for x in v.split(".")],
        )
        newest_tag = tag_versions[-1] if tag_versions else None
        current_tag_rc, current_tag = _git(root, ["tag", "--points-at", "HEAD"])
        v_tags = (
            [t for t in current_tag.splitlines() if t == f"v{version}"]
            if current_tag_rc == 0
            else []
        )

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
        f"tag={'v' + version if not dev_mode and tags and v_tags else '<release, tag pending>'}"
    )
    return 0


def _cmp(a: str, b: str) -> int:
    av, bv = [int(x) for x in a.split(".")], [int(x) for x in b.split(".")]
    return (av > bv) - (av < bv)


if __name__ == "__main__":
    sys.exit(main())
