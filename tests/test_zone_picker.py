"""Smoke tests for zone_picker.py — module imports and constants."""

from __future__ import annotations


class TestZonePickerImport:
    """zone_picker module can be imported without crashing."""

    def test_module_imports(self):
        """Verifying the module imports without tkinter-init errors."""
        import saipenview.zone_picker  # noqa: F811

        assert saipenview.zone_picker.PICKER_SIZE == 200
        assert saipenview.zone_picker.ZONE_PAD == 4

    def test_import_show_function(self):
        """The public show() function can be accessed."""
        from saipenview.zone_picker import show

        assert callable(show)

    def test_import_ensure_tk_thread(self):
        """Internal _ensure_tk_thread function exists."""
        from saipenview.zone_picker import _ensure_tk_thread

        assert callable(_ensure_tk_thread)

    def test_helpers_import(self):
        """Helper functions can be accessed."""
        from saipenview.zone_picker import (
            RECT,
            MONITORINFO,
            _get_cursor_pos,
            _get_monitor_work_area,
        )

        # ctypes structures
        assert RECT._fields_ is not None
        assert len(RECT._fields_) == 4
        assert MONITORINFO._fields_ is not None
        assert any(name == "cbSize" for name, _ in MONITORINFO._fields_)

        # Functions are callable
        assert callable(_get_cursor_pos)
        assert callable(_get_monitor_work_area)

    def test_constants(self):
        """Zone picker constants have expected values."""
        import saipenview.zone_picker

        assert saipenview.zone_picker.PICKER_SIZE == 200
        assert saipenview.zone_picker.ZONE_PAD == 4

    def test_snap_function(self):
        """_snap calls resize/move on the window object."""
        from unittest.mock import MagicMock

        from saipenview.zone_picker import _snap

        mock_window = MagicMock()
        mock_window._window = MagicMock()
        _snap(mock_window, 100, 200, 800, 600)
        mock_window._window.resize.assert_called_once_with(800, 600)
        mock_window._window.move.assert_called_once_with(100, 200)
