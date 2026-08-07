"""T-176: a saved off-screen window geometry must never restore verbatim.

The config carried `window_x/y = -32000` (Windows' off-screen sentinel, left
behind by a window parked after a monitor was removed). The app launched, the
guard handed off, the window existed -- at (-32000,-32000), invisible. The
user saw "it does not start". Restore now validates the position against the
virtual screen and drops it when it intersects no visible monitor.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from saipenview.ui import window as w


def _stub_window():
    mock_window = MagicMock()
    for name in ("closing", "loaded", "shown", "moved", "resized"):
        ev = MagicMock()
        ev.__iadd__ = MagicMock()
        setattr(mock_window.events, name, ev)
    return mock_window


class TestPositionIsOnScreen:
    def test_offscreen_sentinel_is_rejected(self):
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}  # virtual screen (0,0,1920,1080)

        def fake(metric):
            return metrics[metric]

        with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=fake):
            assert w._position_is_on_screen(-32000, -32000, 216, 268) is False

    def test_on_screen_position_is_accepted(self):
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}

        def fake(metric):
            return metrics[metric]

        with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=fake):
            assert w._position_is_on_screen(100, 100, 800, 600) is True

    def test_position_beyond_virtual_screen_is_rejected(self):
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}

        def fake(metric):
            return metrics[metric]

        with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=fake):
            # entirely to the right of every monitor
            assert w._position_is_on_screen(2000, 100, 800, 600) is False

    def test_metric_failure_degrades_to_keep(self):
        with patch(
            "ctypes.windll.user32.GetSystemMetrics", side_effect=OSError("boom")
        ):
            assert w._position_is_on_screen(-32000, -32000, 216, 268) is True


class TestMainWindowRestore:
    def _make(self, cfg):
        mock_api = MagicMock()
        mock_api.get_config.return_value = cfg
        with patch("saipenview.ui.window.webview.create_window") as mock_create:
            mock_create.return_value = _stub_window()
            mw = w.MainWindow(api=mock_api, api_ref=mock_api)
            return mw, mock_create

    def test_offscreen_saved_position_is_dropped(self):
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}

        def fake(metric):
            return metrics[metric]

        with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=fake):
            mw, mock_create = self._make(
                {
                    "window_x": -32000,
                    "window_y": -32000,
                    "window_width": 720,
                    "window_height": 450,
                    "show_on_launch": True,
                    "always_on_top": True,
                    "frameless": True,
                }
            )
        kwargs = mock_create.call_args.kwargs
        assert "x" not in kwargs, "the off-screen x survived the restore"
        assert "y" not in kwargs, "the off-screen y survived the restore"

    def test_on_screen_saved_position_is_kept(self):
        metrics = {76: 0, 77: 0, 78: 1920, 79: 1080}

        def fake(metric):
            return metrics[metric]

        with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=fake):
            mw, mock_create = self._make(
                {
                    "window_x": 120,
                    "window_y": 80,
                    "window_width": 720,
                    "window_height": 450,
                    "show_on_launch": True,
                    "always_on_top": True,
                    "frameless": True,
                }
            )
        kwargs = mock_create.call_args.kwargs
        assert kwargs["x"] == 120
        assert kwargs["y"] == 80
