"""T-170/T-188: wheel version identity + installed-package smoke, run locally.

Builds the wheel from a CLEAN tracked checkout (git archive -- nothing
untracked can leak in), then verifies:

1. METADATA Version == the checkout's `saipenview.__version__` (the ONE
   source; pyproject derives it dynamically, so there is no static copy to
   compare against).
2. the installed wheel's `saipenview` resolves to the wheel, not the source tree
3. the core modules import from that installed copy
4. TAG identity: when HEAD carries a `v<X>` tag, the wheel MUST be version X.
   A wheel that triple-matches a stale version (the v0.1.18..v0.1.20 defect,
   where pyproject/__init__ agreed on 0.1.17 while the tag said v0.1.20) is a
   lie and must fail loudly.

An existing wheel may be verified directly (`verify_wheel.py <path>.whl`);
CI builds the wheel and hands it to this tool -- ONE implementation per
invariant, the workflow never reimplements the check inline.

This is the same contract the CI wheel job enforces; GitHub runners cannot be
executed from this machine, so the equivalent runs here and the results are
recorded. Exits non-zero on any mismatch.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _verify(wheel: Path, src_root: Path) -> int:
    with zipfile.ZipFile(wheel) as z:
        meta_name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        meta = z.read(meta_name).decode("utf-8", "replace")
    meta_match = re.search(r"^Version:\s*(.+)$", meta, re.MULTILINE)
    meta_ver = meta_match.group(1).strip()

    init = (src_root / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    src_match = VERSION_RE.search(init)
    if not src_match:
        print(
            "wheel verify FAIL: checkout __init__.py has no __version__",
            file=sys.stderr,
        )
        return 1
    src_ver = src_match.group(1)

    target = wheel.parent / f"_verify_inst_{wheel.stem}"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        check=True,
    )

    sys.path.insert(0, str(target))
    import saipenview  # noqa: E402

    pkg_ver = saipenview.__version__

    print(f"source __version__:  {src_ver}")
    print(f"wheel METADATA:      {meta_ver}")
    print(f"installed __version__: {pkg_ver}")

    if not (src_ver == meta_ver == pkg_ver):
        print("wheel verify FAIL: version mismatch", file=sys.stderr)
        return 1

    # TAG identity (T-188): a release tag at HEAD names the expected
    # version; a wheel that disagrees with it is stale-release evidence.
    tags = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tags_at_head = [t.strip() for t in (tags.stdout or "").splitlines() if t.strip()]
    expected = [t[1:] for t in tags_at_head if t.startswith("v")]
    if expected and src_ver not in expected:
        print(
            f"wheel verify FAIL: HEAD is tagged {tags_at_head} but the wheel "
            f"is version {src_ver}",
            file=sys.stderr,
        )
        return 1

    if not saipenview.__file__.startswith(str(target)):
        print(
            "wheel verify FAIL: imported from the source tree, not the wheel",
            file=sys.stderr,
        )
        return 1

    for mod in (
        "saipenview.config",
        "saipenview.parser",
        "saipenview.paths",
        "saipenview.conformance",
        "saipenview.protocol",
    ):
        __import__(mod)

    tag_note = f" tag=({'/'.join(tags_at_head) if tags_at_head else 'none'})"
    print(
        "wheel verify PASS: version identity matches, installed wheel "
        f"imports clean{tag_note}"
    )
    return 0


def main() -> int:
    given = [a for a in sys.argv[1:] if not a.startswith("-")]
    if given:
        wheel = Path(given[0])
        if not wheel.is_file():
            print(f"wheel verify FAIL: {wheel} not found", file=sys.stderr)
            return 1
        print(f"wheel: {wheel.name}")
        with tempfile.TemporaryDirectory(prefix="saipenview-wheel-verify-") as td:
            return _verify_with_target(wheel, ROOT, Path(td) / "inst")

    with tempfile.TemporaryDirectory(prefix="saipenview-wheel-") as td:
        base = Path(td)
        checkout = base / "src"
        checkout.mkdir()

        tar_path = base / "repo.tar"
        with tar_path.open("wb") as f:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=f, check=True)
        subprocess.run(["tar", "-xf", str(tar_path), "-C", str(checkout)], check=True)

        subprocess.run(
            [sys.executable, "-m", "build", "--wheel"], cwd=checkout, check=True
        )
        wheels = sorted((checkout / "dist").glob("*.whl"))
        if not wheels:
            print("wheel verify FAIL: no wheel produced", file=sys.stderr)
            return 1
        wheel = wheels[0]
        print(f"wheel: {wheel.name}")
        return _verify_with_target(wheel, checkout, base / "inst")


def _verify_with_target(wheel: Path, src_root: Path, target: Path) -> int:
    """The verification body, with the install target supplied by the caller
    so the given-wheel and built-wheel paths share ONE implementation."""
    with zipfile.ZipFile(wheel) as z:
        meta_name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        meta = z.read(meta_name).decode("utf-8", "replace")
    meta_match = re.search(r"^Version:\s*(.+)$", meta, re.MULTILINE)
    meta_ver = meta_match.group(1).strip()

    init = (src_root / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    src_match = VERSION_RE.search(init)
    if not src_match:
        print(
            "wheel verify FAIL: checkout __init__.py has no __version__",
            file=sys.stderr,
        )
        return 1
    src_ver = src_match.group(1)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        check=True,
    )

    sys.path.insert(0, str(target))
    import saipenview  # noqa: E402

    pkg_ver = saipenview.__version__

    print(f"source __version__:  {src_ver}")
    print(f"wheel METADATA:      {meta_ver}")
    print(f"installed __version__: {pkg_ver}")

    if not (src_ver == meta_ver == pkg_ver):
        print("wheel verify FAIL: version mismatch", file=sys.stderr)
        return 1

    # TAG identity (T-188): a release tag at HEAD names the expected
    # version; a wheel that disagrees with it is stale-release evidence.
    tags = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tags_at_head = [t.strip() for t in (tags.stdout or "").splitlines() if t.strip()]
    expected = [t[1:] for t in tags_at_head if t.startswith("v")]
    if expected and src_ver not in expected:
        print(
            f"wheel verify FAIL: HEAD is tagged {tags_at_head} but the wheel "
            f"is version {src_ver}",
            file=sys.stderr,
        )
        return 1

    if not saipenview.__file__.startswith(str(target)):
        print(
            "wheel verify FAIL: imported from the source tree, not the wheel",
            file=sys.stderr,
        )
        return 1

    for mod in (
        "saipenview.config",
        "saipenview.parser",
        "saipenview.paths",
        "saipenview.conformance",
        "saipenview.protocol",
    ):
        __import__(mod)

    tag_note = f" tag=({'/'.join(tags_at_head) if tags_at_head else 'none'})"
    print(
        "wheel verify PASS: version identity matches, installed wheel "
        f"imports clean{tag_note}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
