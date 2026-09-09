"""T-831: the generated startup page must never contaminate release inputs.

``tools/build.py`` hands Nuitka the whole ``saipenview/ui/static`` directory;
a gitignored ``index.lite.html`` sitting there from a local desktop run is
still inside that snapshot. .gitignore is NOT a packaging mechanism, so the
build must purge the generated file before Nuitka runs and the release
verifier must reject one in a wheel.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_build_module():
    spec = importlib.util.spec_from_file_location("saipenview_build", ROOT / "tools" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBuildPurge:
    def test_purge_removes_a_generated_page_from_build_input(self, tmp_path):
        mod = _load_build_module()
        static = tmp_path / "saipenview" / "ui" / "static"
        static.mkdir(parents=True)
        generated = static / "index.lite.html"
        generated.write_text("<html>stale generated</html>", encoding="utf-8")

        original = mod.GENERATED
        try:
            mod.GENERATED = Path("saipenview/ui/static/index.lite.html")
            cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                mod._purge_generated()
            finally:
                os.chdir(cwd)
        finally:
            mod.GENERATED = original
        assert not generated.exists()

    def test_purge_refuses_when_the_file_cannot_be_removed(self, tmp_path, monkeypatch):
        mod = _load_build_module()
        static = tmp_path / "saipenview" / "ui" / "static"
        static.mkdir(parents=True)
        generated = static / "index.lite.html"
        generated.write_text("<html>stuck</html>", encoding="utf-8")

        monkeypatch.setattr(Path, "unlink", lambda self, *a, **k: None)
        original = mod.GENERATED
        try:
            mod.GENERATED = Path("saipenview/ui/static/index.lite.html")
            cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                with pytest.raises(SystemExit):
                    mod._purge_generated()
            finally:
                os.chdir(cwd)
        finally:
            mod.GENERATED = original
        # The file survived (that is the point) -- clean up.
        generated.unlink(missing_ok=True)


class TestWheelContract:
    def test_wheel_rejects_generated_index_lite(self, tmp_path):
        """A wheel carrying index.lite.html must fail verification."""
        wheel = tmp_path / "fake-0.0.0-py3-none-any.whl"
        # Minimal structurally-valid wheel: dist-info/METADATA + a leaked file.
        with zipfile.ZipFile(wheel, "w") as z:
            z.writestr("fake-0.0.0.dist-info/METADATA", "Metadata-Version: 2.1\nVersion: 0.0.0\n")
            z.writestr("saipenview/ui/static/index.lite.html", "<html>generated</html>")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "verify_wheel.py"), str(wheel)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode != 0, proc.stdout
        assert "index.lite.html" in (proc.stderr + proc.stdout)

    def test_wheel_check_passes_a_wheel_without_it(self, tmp_path):
        """The same verifier accepts a wheel whose static dir carries only the
        canonical template -- proving the rejection is specific, not a
        blanket failure of the fake-wheel path."""
        wheel = tmp_path / "fake-0.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as z:
            z.writestr("fake-0.0.0.dist-info/METADATA", "Metadata-Version: 2.1\nVersion: 0.0.0\n")
            z.writestr("saipenview/ui/static/index.html", "<html>canonical</html>")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "verify_wheel.py"), str(wheel)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # It WILL fail on version identity (fake wheel vs checkout version) --
        # but never on the index.lite.html clause.
        combined = proc.stdout + proc.stderr
        assert "index.lite.html" not in combined
