import os
import shutil
import subprocess
import sys
from pathlib import Path

# T-831: index.lite.html is RUNTIME-GENERATED state, never canonical package
# data. It is gitignored, but gitignore is NOT a packaging mechanism: Nuitka's
# --include-data-dir snapshots the whole directory, so whichever generated page
# happened to exist locally would ride into the release. The build guarantees
# the generated file is absent from the build input before Nuitka consumes it.
GENERATED = Path("saipenview/ui/static/index.lite.html")


def _purge_generated() -> None:
    if GENERATED.is_file():
        GENERATED.unlink()
        print(f"build: removed generated {GENERATED} from build input")
    if GENERATED.exists():
        raise SystemExit(f"build: {GENERATED} still present after purge -- refusing")


def _verify_build_output() -> None:
    """No generated page may exist in Nuitka's data output.

    Onefile builds embed the data into the exe and normally leave no dist
    tree; when a dist tree exists (standalone), scan exactly those dirs so
    the check is bounded and cannot be defeated by repo clutter."""
    roots = [p for p in Path(".").glob("*.dist") if p.is_dir()]
    roots += [p for p in Path(".").glob("*.build") if p.is_dir()]
    leaked = [
        str(p)
        for root in roots
        for p in root.rglob(GENERATED.name)
        if p.is_file()
    ]
    if leaked:
        raise SystemExit(
            "build FAIL: generated index.lite.html leaked into the build "
            f"output: {leaked[:3]}"
        )


def main():
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    _purge_generated()

    print("Building SAIPENVIEW with Nuitka...")

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--onefile",
        "--windows-disable-console",
        "--windows-icon-from-ico=saipenview/ui/static/saipen_icon.ico",
        "--include-data-dir=saipenview/ui/static=saipenview/ui/static",
        "--include-data-dir=saipenview/assets=saipenview/assets",
        "--enable-plugin=pywebview",
        "saipenview/__main__.py",
        "-o",
        "SAIPENVIEW.exe",
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    _verify_build_output()
    print("Build complete: SAIPENVIEW.exe")


if __name__ == "__main__":
    main()
