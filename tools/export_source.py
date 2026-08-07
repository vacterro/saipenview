"""Deterministic source export (T-171).

Builds a release archive from a CLEAN git archive -- tracked files only, so
.venv/, build/, dist/, egg-info/, pytest/ruff caches, runtime _data and any
stale wheels never enter it by construction -- and writes a MANIFEST.txt of
exactly what went in. Canonical SAIPEN memory is layered in per the
persistence contract (T-172). Run: python tools/export_source.py
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _version() -> str:
    import re

    init = (ROOT / "saipenview" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', init).group(1)


def _add_saipen_memory(checkout: Path) -> None:
    """Copy the canonical .saipen memory into the export (T-172 contract).

    Canonical memory travels; machine-local state does not. saipen_home and
    anything under kitchen/logs/cache are deliberately absent.
    """
    src_saipen = ROOT / ".saipen"
    dst_saipen = checkout / ".saipen"
    dst_saipen.mkdir(exist_ok=True)
    for name in ("BOARD.md", "LOG.md"):
        src = src_saipen / name
        if src.is_file():
            (dst_saipen / name).write_bytes(src.read_bytes())
    knowledge = src_saipen / "KNOWLEDGE"
    if knowledge.is_dir():
        for p in knowledge.rglob("*"):
            if p.is_file():
                rel = p.relative_to(knowledge)
                target = dst_saipen / "KNOWLEDGE" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(p.read_bytes())
    digest = src_saipen / "kitchen" / "digest.md"
    if digest.is_file():
        target = dst_saipen / "kitchen"
        target.mkdir(exist_ok=True)
        (target / "digest.md").write_bytes(digest.read_bytes())


def main() -> int:
    version = _version()
    out = ROOT / "dist" / f"saipenview-src-{version}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="saipenview-export-") as td:
        base = Path(td)
        tar_path = base / "repo.tar"
        with tar_path.open("wb") as f:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=f, check=True)
        checkout = base / "src"
        checkout.mkdir()
        subprocess.run(["tar", "-xf", str(tar_path), "-C", str(checkout)], check=True)

        _add_saipen_memory(checkout)

        manifest = sorted(
            str(p.relative_to(checkout)).replace("\\", "/")
            for p in checkout.rglob("*")
            if p.is_file()
        )
        (checkout / "MANIFEST.txt").write_text(
            "\n".join(manifest) + "\n", encoding="utf-8"
        )

        out.parent.mkdir(exist_ok=True)
        with tarfile.open(out, "w:gz") as t:
            t.add(checkout, arcname=f"saipenview-src-{version}")

    size = out.stat().st_size
    print(f"exported {out} ({size} bytes, {len(manifest)} files)")
    bad = [
        m
        for m in manifest
        if any(
            seg in m
            for seg in (
                ".venv",
                "build/",
                "dist/",
                "egg-info",
                "__pycache__",
                "_data",
                ".pytest_cache",
                ".ruff_cache",
            )
        )
    ]
    if bad:
        print("export FAIL: unwanted content in manifest:", bad, file=sys.stderr)
        return 1
    print("export PASS: no local runtime/cache/build content in the archive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
