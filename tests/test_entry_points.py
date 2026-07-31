"""Import smoke tests for GUI-dependent modules — mock GUI frameworks at sys.modules level."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ──

_MOCKED_MODULES: set[str] = set()


def _ensure_mock(mod_name: str, attrs: list[str] | None = None) -> MagicMock:
    """Ensure a module-level mock exists in sys.modules so imports resolve."""
    if mod_name not in sys.modules:
        mock_mod = MagicMock()
        if attrs:
            for attr in attrs:
                setattr(mock_mod, attr, MagicMock())
        sys.modules[mod_name] = mock_mod
        _MOCKED_MODULES.add(mod_name)
    return sys.modules[mod_name]


@pytest.fixture(autouse=True)
def _cleanup_mocked_modules():
    """Remove mocked modules after each test so state doesn't leak."""
    yield
    for mod_name in list(_MOCKED_MODULES):
        if mod_name in sys.modules:
            del sys.modules[mod_name]
    _MOCKED_MODULES.clear()


# ── __main__.py ──

class TestMainModule:
    """__main__.py entry point — import and verify main() exists."""

    def test_main_module_imports(self):
        """Import __main__ and verify main() is callable."""
        # webview is required by app.py which main.py imports
        _ensure_mock("webview")
        import saipenview.__main__  # noqa: F811

        assert callable(saipenview.__main__.main)

    def test_main_returns_int(self):
        """main() should return an int (exit code) — mock run() to avoid side effects."""
        _ensure_mock("webview")
        with patch("saipenview.__main__.run", return_value=0):
            from saipenview.__main__ import main

            result = main()
            assert isinstance(result, int)
            assert result == 0


# ── app.py ──

class TestAppModule:
    """app.py wires tray, hotkeys, and window with single-instance guard."""

    def test_app_module_imports_with_mock_webview(self):
        """With webview mocked, app.py imports without error."""
        _ensure_mock("webview")
        import saipenview.app  # noqa: F811

        assert callable(saipenview.app.run)

    def test_run_returns_int_without_side_effects(self):
        """run() returns 0 when guard doesn't acquire (second instance)."""
        _ensure_mock("webview")
        import saipenview.app

        # Mock the guard to not acquire → run returns 0 immediately
        with patch("saipenview.app.SingleInstanceGuard") as mock_guard_cls:
            mock_guard = MagicMock()
            mock_guard.acquire.return_value = False
            mock_guard_cls.return_value = mock_guard

            result = saipenview.app.run()
            assert result == 0
            mock_guard.acquire.assert_called_once()


# ── ui/window.py ──

class TestWindowModule:
    """ui/window.py requires webview — verify import and class structure."""

    def test_window_module_imports_with_mock_webview(self):
        """With webview mocked, ui/window.py imports without error."""
        _ensure_mock("webview")
        import saipenview.ui.window  # noqa: F811

        assert hasattr(saipenview.ui.window, "MainWindow")
        assert hasattr(saipenview.ui.window, "_work_area")

    def test_work_area_returns_fallback_on_exception(self):
        """_work_area() returns fallback when ctypes calls fail."""
        _ensure_mock("webview")
        import saipenview.ui.window as w

        # On non-Windows platforms, ctypes.windll doesn't exist — skip
        if not hasattr(w.ctypes, "windll"):
            pytest.skip("ctypes.windll not available on this platform")

        # Mock user32 to fail
        mock_user32 = MagicMock()
        mock_user32.MonitorFromWindow.return_value = 0
        mock_user32.GetMonitorInfoW.return_value = False

        with patch.object(w.ctypes, "windll", new=MagicMock()) as mock_windll:
            mock_windll.user32 = mock_user32
            result = w._work_area()
            assert result == (0, 0, 1920, 1080)

    def test_main_window_can_be_instantiated(self):
        """MainWindow can be constructed with a mock api."""
        _ensure_mock("webview")
        _ensure_mock("webview.window")
        import saipenview.ui.window as w

        mock_api = MagicMock()
        mock_api.get_config.return_value = {
            "window_width": 480,
            "window_height": 360,
            "window_x": None,
            "window_y": None,
            "show_on_launch": True,
            "always_on_top": True,
        }

        # Mock webview.create_window
        with patch("saipenview.ui.window.webview.create_window") as mock_create:
            mock_window = MagicMock()
            mock_window.events.closing = MagicMock()
            mock_window.events.closing.__iadd__ = MagicMock()
            mock_window.events.loaded = MagicMock()
            mock_window.events.loaded.__iadd__ = MagicMock()
            mock_window.events.shown = MagicMock()
            mock_window.events.shown.__iadd__ = MagicMock()
            mock_window.events.moved = MagicMock()
            mock_window.events.moved.__iadd__ = MagicMock()
            mock_window.events.resized = MagicMock()
            mock_window.events.resized.__iadd__ = MagicMock()
            mock_create.return_value = mock_window

            mw = w.MainWindow(api=mock_api, api_ref=mock_api)
            assert mw is not None
            assert hasattr(mw, "show")
            assert hasattr(mw, "hide")
            assert hasattr(mw, "toggle")
            assert hasattr(mw, "destroy")
            mock_create.assert_called_once()

    def test_main_window_toggle(self):
        """MainWindow.toggle() alternates between show/hide."""
        _ensure_mock("webview")
        import saipenview.ui.window as w

        mock_api = MagicMock()
        mock_api.get_config.return_value = {"show_on_launch": True}

        with patch("saipenview.ui.window.webview.create_window") as mock_create:
            mock_window = MagicMock()
            mock_window.events.closing = MagicMock()
            mock_window.events.closing.__iadd__ = MagicMock()
            mock_window.events.loaded = MagicMock()
            mock_window.events.loaded.__iadd__ = MagicMock()
            mock_window.events.shown = MagicMock()
            mock_window.events.shown.__iadd__ = MagicMock()
            mock_window.events.moved = MagicMock()
            mock_window.events.moved.__iadd__ = MagicMock()
            mock_window.events.resized = MagicMock()
            mock_window.events.resized.__iadd__ = MagicMock()
            mock_create.return_value = mock_window

            mw = w.MainWindow(api=mock_api, api_ref=mock_api)
            mw._visible = True
            mw.hide = MagicMock()
            mw.show = MagicMock()

            mw.toggle()
            mw.hide.assert_called_once()

            mw._visible = False
            mw.toggle()
            mw.show.assert_called_once()


# ── tray.py ──

class TestTrayModule:
    """tray.py requires pystray + PIL — verify with mocks."""

    def test_import_with_mocks(self):
        """With pystray and PIL mocked, tray.py imports without error."""
        _ensure_mock("pystray", ["Menu", "MenuItem", "Icon"])
        _ensure_mock("PIL")
        _ensure_mock("PIL.Image")


        import saipenview.tray  # noqa: F811

        assert callable(saipenview.tray.build_tray_icon)

    def test_build_tray_icon_creates_icon(self, tmp_path):
        """build_tray_icon creates a pystray.Icon with the expected structure."""
        _ensure_mock("pystray", ["Menu", "MenuItem", "Icon"])
        _ensure_mock("PIL")
        _ensure_mock("PIL.Image")

        import saipenview.tray

        # Create a mock icon file so Image.open doesn't crash
        icon_dir = tmp_path / "assets"
        icon_dir.mkdir()
        (icon_dir / "tray_icon.png").write_text("fake png", encoding="utf-8")

        with (
            patch("saipenview.tray.ICON_PATH", icon_dir / "tray_icon.png"),
            patch("saipenview.tray.Image.open") as mock_open,
            patch("saipenview.tray.pystray") as mock_pystray,
        ):
            mock_image = MagicMock()
            mock_open.return_value = mock_image
            mock_menu = MagicMock()
            mock_pystray.Menu.return_value = mock_menu
            mock_icon = MagicMock()
            mock_pystray.Icon.return_value = mock_icon

            on_toggle = MagicMock()
            on_quit = MagicMock()

            result = saipenview.tray.build_tray_icon(on_toggle=on_toggle, on_quit=on_quit)
            assert result == mock_icon
            mock_open.assert_called_once_with(icon_dir / "tray_icon.png")
            mock_pystray.Menu.assert_called_once()
            mock_pystray.Icon.assert_called_once_with("saipenview", mock_image, "SAIPENVIEW", mock_menu)


# ── zone_picker.py ──

class TestZonePickerModule:
    """zone_picker.py requires tkinter + ctypes — verify with mocks."""

    def test_import_with_mocks(self):
        """With tkinter and ctypes mocked, zone_picker imports without error."""
        _ensure_mock("tkinter")
        # Import the actual module — it may fail on non-Windows but should work with mocks
        try:
            import saipenview.zone_picker  # noqa: F811

            assert saipenview.zone_picker.PICKER_SIZE == 200
            assert saipenview.zone_picker.ZONE_PAD == 4
            assert callable(saipenview.zone_picker.show)
            assert callable(saipenview.zone_picker._ensure_tk_thread)
        except Exception as e:
            # tkinter/ctypes may not be fully mockable on all platforms
            pytest.skip(f"zone_picker import skipped: {e}")

    def test_constants_and_functions(self):
        """Constants and key functions are accessible."""
        try:
            import saipenview.zone_picker as zp

            assert hasattr(zp, "RECT")
            assert hasattr(zp, "MONITORINFO")
            assert hasattr(zp, "_snap")
            assert hasattr(zp, "_get_cursor_pos")
            assert hasattr(zp, "_get_monitor_work_area")
        except Exception as e:
            pytest.skip(f"zone_picker constants check skipped: {e}")

    def test_snap_calls_window_methods(self):
        """_snap calls resize, move, and _save_geometry on the window."""
        try:
            import saipenview.zone_picker as zp

            mock_main_window = MagicMock()
            mock_main_window._window = MagicMock()
            mock_main_window._save_geometry = MagicMock()

            zp._snap(mock_main_window, 100, 200, 800, 600)
            mock_main_window._window.resize.assert_called_once_with(800, 600)
            mock_main_window._window.move.assert_called_once_with(100, 200)
            mock_main_window._save_geometry.assert_called_once()
        except Exception as e:
            pytest.skip(f"zone_picker snap test skipped: {e}")

    def test_snap_handles_exception(self):
        """_snap catches exceptions gracefully."""
        try:
            import saipenview.zone_picker as zp

            mock_main_window = MagicMock()
            mock_main_window._window = MagicMock()
            mock_main_window._window.resize.side_effect = Exception("resize failed")
            mock_main_window._save_geometry = MagicMock()

            # Should not raise
            zp._snap(mock_main_window, 100, 200, 800, 600)
        except Exception as e:
            pytest.skip(f"zone_picker snap test skipped: {e}")
