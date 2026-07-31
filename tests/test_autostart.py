"""Tests for autostart.py pure functions — no winreg/registry dependency."""

from __future__ import annotations

from pathlib import Path


class TestRunVbsPath:
    """_run_vbs_path resolves to the project-root run.vbs."""

    def test_returns_path_below_project_root(self):
        from saipenview.autostart import _run_vbs_path

        result = _run_vbs_path()
        assert isinstance(result, Path)
        assert result.name == "run.vbs"
        # Path logic: __file__/../../run.vbs → project-root/run.vbs
        root = Path(__file__).resolve().parent.parent
        expected = root / "run.vbs"
        assert result == expected


class TestLaunchCommand:
    """_launch_command returns a wscript.exe command string."""

    def test_returns_wscript_command(self):
        from saipenview.autostart import _launch_command, _run_vbs_path

        cmd = _launch_command()
        assert cmd.startswith("wscript.exe ")
        assert _run_vbs_path().name in cmd

    def test_includes_quoted_path(self):
        from saipenview.autostart import _launch_command

        cmd = _launch_command()
        # The path should be double-quoted: wscript.exe "X:\path\to\run.vbs"
        assert '"' in cmd
        assert cmd.count('"') == 2  # exactly one pair of quotes

    def test_command_can_be_passed_to_registry(self):
        """The command format matches what Windows Run key expects."""
        from saipenview.autostart import _launch_command

        cmd = _launch_command()
        # Registry REG_SZ accepts strings like: wscript.exe "D:\path\to\run.vbs"
        assert '"' in cmd
        assert cmd.endswith('"')  # ends with closing quote


class TestIsEnabled:
    """is_enabled() reads from HKCU Run key."""

    def test_returns_true_when_key_matches(self):
        """If the registry value matches _launch_command(), is_enabled() returns True."""
        from unittest.mock import patch

        from saipenview.autostart import _launch_command, is_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            mock_winreg.QueryValueEx.return_value = (_launch_command(), 1)
            result = is_enabled()
            assert result is True

    def test_returns_false_when_key_missing(self):
        """If the registry key doesn't exist, is_enabled() returns False."""
        from unittest.mock import patch

        from saipenview.autostart import is_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            mock_winreg.OpenKey.side_effect = FileNotFoundError
            result = is_enabled()
            assert result is False

    def test_returns_false_when_value_differs(self):
        """If the registry value differs from _launch_command(), is_enabled() returns False."""
        from unittest.mock import patch

        from saipenview.autostart import is_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            mock_winreg.QueryValueEx.return_value = ("different_command", 1)
            result = is_enabled()
            assert result is False


class TestSetEnabled:
    """set_enabled() writes/deletes the HKCU Run key."""

    def test_enable_writes_registry(self):
        from unittest.mock import patch

        from saipenview.autostart import set_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            result = set_enabled(True)
            assert result is True
            mock_winreg.SetValueEx.assert_called_once()

    def test_disable_deletes_registry(self):
        from unittest.mock import patch

        from saipenview.autostart import set_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            result = set_enabled(False)
            assert result is True
            mock_winreg.DeleteValue.assert_called_once()

    def test_disable_when_key_missing_is_noop(self):
        """Disabling when the key doesn't exist doesn't crash."""
        from unittest.mock import patch

        from saipenview.autostart import set_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            mock_winreg.DeleteValue.side_effect = FileNotFoundError
            result = set_enabled(False)
            assert result is True

    def test_returns_false_on_oserror(self):
        from unittest.mock import patch

        from saipenview.autostart import set_enabled

        with patch("saipenview.autostart.winreg") as mock_winreg:
            mock_winreg.OpenKey.side_effect = OSError
            result = set_enabled(True)
            assert result is False
