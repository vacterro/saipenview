import os
import subprocess
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    print("Building SAIPENVIEW with Nuitka...")
    
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--windows-disable-console",
        "--windows-icon-from-ico=saipenview/ui/static/saipen_icon.ico",
        "--include-data-dir=saipenview/ui/static=saipenview/ui/static",
        "--include-data-dir=saipenview/assets=saipenview/assets",
        "--enable-plugin=pywebview",
        "saipenview/__main__.py",
        "-o", "SAIPENVIEW.exe"
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("Build complete: SAIPENVIEW.exe")

if __name__ == "__main__":
    main()
