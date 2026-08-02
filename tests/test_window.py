"""Tests for saipenview.ui.window — the show/hide/minimize state machine.

`MainWindow.__init__` builds a real pywebview window, so these construct the
instance with `object.__new__` and set only the attributes under test. That is
deliberate: the bug these cover is pure state logic (which branch `toggle()`
takes), and driving a native window would test the OS, not the branch.
"""

from __future__ import annotations

import pytest

from saipenview.ui.window import MainWindow


def _window(*, visible: bool, minimized: bool) -> MainWindow:
    """A MainWindow stub whose show/hide only record that they were called."""
    win = object.__new__(MainWindow)
    win._visible = visible
    win.calls = []
    win._is_minimized = lambda: minimized
    win.show = lambda: win.calls.append("show")
    win.hide = lambda: win.calls.append("hide")
    return win


class TestToggle:
    def test_minimized_window_is_shown_not_hidden(self):
        """The T-120 bug: minimize() never clears `_visible`, so a minimized
        window still read as visible and the hotkey hid it into the tray
        instead of raising it. One press must raise it."""
        win = _window(visible=True, minimized=True)
        MainWindow.toggle(win)
        assert win.calls == ["show"]

    def test_visible_window_hides(self):
        win = _window(visible=True, minimized=False)
        MainWindow.toggle(win)
        assert win.calls == ["hide"]

    def test_hidden_window_shows(self):
        win = _window(visible=False, minimized=False)
        MainWindow.toggle(win)
        assert win.calls == ["show"]

    def test_alternates_across_repeated_presses(self):
        """T-068's regression was a toggle that stopped alternating. Drive the
        real flag through several presses to keep that closed."""
        win = object.__new__(MainWindow)
        win._visible = True
        win.calls = []
        win._is_minimized = lambda: False

        def _show() -> None:
            win.calls.append("show")
            win._visible = True

        def _hide() -> None:
            win.calls.append("hide")
            win._visible = False

        win.show = _show
        win.hide = _hide

        for _ in range(4):
            MainWindow.toggle(win)
        assert win.calls == ["hide", "show", "hide", "show"]


class TestIsMinimized:
    def test_returns_false_when_the_query_raises(self):
        """`_is_minimized` guards toggle(), so a failure there must degrade to
        the old flag-only behaviour, never to a window that will not hide."""
        win = object.__new__(MainWindow)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "saipenview.ui.window.ctypes.windll.user32.FindWindowW",
                _raise,
                raising=False,
            )
            assert MainWindow._is_minimized(win) is False

    def test_reports_a_real_answer_for_a_missing_window(self):
        """No window by that title means nothing is iconic."""
        win = object.__new__(MainWindow)
        assert MainWindow._is_minimized(win) is False


def _raise(*args, **kwargs):
    raise OSError("FindWindowW unavailable")
