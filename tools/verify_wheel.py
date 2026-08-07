"""T-170: wheel version-triple + installed-package smoke, run locally.

Builds the wheel from a CLEAN tracked checkout (git archive -- nothing
untracked can leak in), then verifies:

1. METADATA Version == pyproject.toml `version` == saipenview.__version__
2. the installed wheel's `saipenview` resolves to the wheel, not the source tree
3. the core modules import from that installed copy

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


def main() -> int:
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

        with zipfile.ZipFile(wheel) as z:
            meta_name = next(
                n for n in z.namelist() if n.endswith(".dist-info/METADATA")
            )
            meta = z.read(meta_name).decode("utf-8", "replace")
        meta_match = re.search(r"^Version:\s*(.+)$", meta, re.MULTILINE)
        meta_ver = meta_match.group(1).strip()

        pyproj = (checkout / "pyproject.toml").read_text(encoding="utf-8")
        pyproj_ver = re.search(r'^version\s*=\s*"([^"]+)"', pyproj, re.MULTILINE).group(1)

        target = base / "inst"
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

        print(f"pyproject.toml:  {pyproj_ver}")
        print(f"wheel METADATA:  {meta_ver}")
        print(f"__version__:     {pkg_ver}")

        if not (pyproj_ver == meta_ver == pkg_ver):
            print("wheel verify FAIL: version triple mismatch", file=sys.stderr)
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

        print("wheel verify PASS: version triple matches, installed wheel imports clean")
        return 0


if __name__ == "__main__":
    sys.exit(main())
