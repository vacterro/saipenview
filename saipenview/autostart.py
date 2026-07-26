"""Windows autostart via the per-user HKCU Run key -- no admin rights needed,
no separate shortcut file to manage. Reuses run.vbs (already the hidden-launch
entry point run.bat/manual double-click use), so autostart bootstraps a
missing .venv exactly the same way a manual launch does."""

from __future__ import annotations

import winreg
from pathlib import Path

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "SAIPENVIEW"


def _run_vbs_path() -> Path:
    return Path(__file__).resolve().parent.parent / "run.vbs"


def _launch_command() -> str:
    return f'wscript.exe "{_run_vbs_path()}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return value == _launch_command()
    except (FileNotFoundError, OSError):
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
