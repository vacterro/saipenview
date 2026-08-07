"""T-168: generic CLI shell contract + engine_overrides.

The docs promised a full shell command (quotes, pipes, &&); the
implementation did `instruction.split()` -- a quoted path with spaces became
four argv elements. The contract is now explicit shell semantics on Windows:
`cmd.exe /d /s /c <command>` with the project root as cwd, the command string
untouched, and the root never interpolated into the command text.

`engine_overrides` was a documented-but-dead config key; it is now the real
override surface (path / extra_args / env), validated before launch.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from saipenview.api import _apply_engine_overrides
from saipenview.engines.generic_cli import GenericCLIEngine
from saipenview.runtime import ProcessManager
from saipenview.sessions import SessionStore


def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def pm(tmp_path):
    manager = ProcessManager()
    manager.sessions = SessionStore(base_dir=tmp_path / "sessions")
    yield manager
    manager.stop_all()


def _run(pm, root, command):
    res = pm.launch(GenericCLIEngine(), str(root), command)
    assert res["ok"] is True, res
    assert _wait_for(lambda: pm.get_status(str(root))["status"] == "done"), (
        "command did not finish: " + repr(pm.get_output(str(root))["lines"])
    )
    return pm.get_output(str(root))["lines"]


class TestShellContract:
    def test_quoted_argument_survives(self, pm, tmp_path):
        lines = _run(pm, tmp_path, 'echo "hello world"')
        assert any("hello world" in line for line in lines), lines

    def test_quoted_path_with_spaces(self, pm, tmp_path):
        lines = _run(pm, tmp_path, 'if exist "C:\\Program Files" echo PF_OK')
        assert any("PF_OK" in line for line in lines), lines

    def test_pipe(self, pm, tmp_path):
        lines = _run(pm, tmp_path, "echo pipe_ok | findstr pipe_ok")
        assert any("pipe_ok" in line for line in lines), lines

    def test_and_and(self, pm, tmp_path):
        lines = _run(pm, tmp_path, "echo aaa && echo bbb")
        assert any("aaa" in line for line in lines), lines
        assert any("bbb" in line for line in lines), lines

    def test_unicode(self, pm, tmp_path):
        # A Unicode filename in the project root: the command text (Cyrillic)
        # must survive argv -> cmd parsing; the output proves cmd found the file.
        (tmp_path / "проект.txt").write_text("x", encoding="utf-8")
        lines = _run(pm, tmp_path, 'if exist "проект.txt" echo UNICODE_OK')
        assert any("UNICODE_OK" in line for line in lines), lines

    def test_project_root_with_ampersand(self, pm, tmp_path):
        root = tmp_path / "a & b"
        root.mkdir()
        lines = _run(pm, root, "echo amp_ok")
        assert any("amp_ok" in line for line in lines), lines

    def test_project_root_with_apostrophe(self, pm, tmp_path):
        root = tmp_path / "it's"
        root.mkdir()
        lines = _run(pm, root, "echo apost_ok")
        assert any("apost_ok" in line for line in lines), lines

    def test_invalid_command_reports_failed(self, pm, tmp_path):
        res = pm.launch(GenericCLIEngine(), str(tmp_path), "nonexistent_cmd_zzz")
        assert res["ok"] is True
        assert _wait_for(lambda: pm.get_status(str(tmp_path))["status"] == "failed")

    def test_empty_command_rejected(self, pm, tmp_path):
        res = pm.launch(GenericCLIEngine(), str(tmp_path), "   ")
        assert res["ok"] is False
        assert "empty" in res["error"]

    def test_root_never_interpolated_into_command(self, tmp_path):
        engine = GenericCLIEngine()
        cmd = engine.build_command(str(tmp_path), "echo hi")
        assert cmd == "cmd.exe /d /s /c echo hi", cmd
        assert str(tmp_path) not in cmd


class TestEngineOverrides:
    def test_path_replaces_executable(self, tmp_path):
        engine = GenericCLIEngine()
        wrapped, err = _apply_engine_overrides(engine, {"path": "C:\\custom\\cmd.exe"})
        assert err is None
        cmd = wrapped.build_command(str(tmp_path), "echo hi")
        assert cmd.startswith("C:\\custom\\cmd.exe")
        assert cmd.endswith("echo hi")

    def test_extra_args_appended(self, tmp_path):
        engine = GenericCLIEngine()
        wrapped, err = _apply_engine_overrides(engine, {"extra_args": ["--verbose"]})
        assert err is None
        cmd = wrapped.build_command(str(tmp_path), "echo hi")
        assert "echo hi --verbose" in cmd

    def test_env_merges_into_default_env(self, tmp_path):
        engine = GenericCLIEngine()
        wrapped, err = _apply_engine_overrides(engine, {"env": {"FOO": "bar"}})
        assert err is None
        env = wrapped.default_env or {}
        assert env.get("FOO") == "bar"

    def test_invalid_overrides_rejected(self):
        engine = GenericCLIEngine()
        assert _apply_engine_overrides(engine, {"path": 42})[0] is None
        assert _apply_engine_overrides(engine, {"extra_args": "nope"})[0] is None
        assert _apply_engine_overrides(engine, {"env": {"K": 1}})[0] is None
        assert _apply_engine_overrides(engine, "nope")[0] is None

    def test_validate_engine_overrides_shape(self):
        from saipenview.api import validate_engine_overrides

        assert validate_engine_overrides({"path": "C:\\x.exe"})[0] is True
        assert validate_engine_overrides({"extra_args": ["--v"]})[0] is True
        assert validate_engine_overrides({"env": {"K": "v"}})[0] is True
        assert validate_engine_overrides({"path": 7})[0] is False
        assert validate_engine_overrides({"extra_args": "no"})[0] is False
        assert validate_engine_overrides({"env": {"K": 1}})[0] is False
        assert validate_engine_overrides("nope")[0] is False

    def test_set_engine_overrides_persists_valid(self, tmp_path):
        from saipenview.api import Api
        from saipenview.config import DEFAULTS

        with (
            patch("saipenview.api.config_path"),
            patch("saipenview.api.load_config", return_value=dict(DEFAULTS)),
            patch("saipenview.api.save_config") as mock_save,
            patch("saipenview.api.BackgroundScanner"),
        ):
            a = Api()
            res = a.set_engine_overrides(
                {"generic-cli": {"path": "C:\\custom\\cmd.exe"}}
            )
            assert res["ok"] is True
            assert (
                a._config["engine_overrides"]["generic-cli"]["path"]
                == "C:\\custom\\cmd.exe"
            )
            mock_save.assert_called_once()
            a.stop()

    def test_set_engine_overrides_rejects_invalid(self, tmp_path):
        from saipenview.api import Api
        from saipenview.config import DEFAULTS

        with (
            patch("saipenview.api.config_path"),
            patch("saipenview.api.load_config", return_value=dict(DEFAULTS)),
            patch("saipenview.api.save_config") as mock_save,
            patch("saipenview.api.BackgroundScanner"),
        ):
            a = Api()
            a._config["engine_overrides"] = {"good": {"path": "C:\\x.exe"}}
            res = a.set_engine_overrides({"generic-cli": {"path": 42}})
            assert res["ok"] is False
            assert "path" in res["error"]
            assert a._config["engine_overrides"] == {"good": {"path": "C:\\x.exe"}}, (
                "an invalid override must not clobber the saved value"
            )
            mock_save.assert_not_called()
            a.stop()
