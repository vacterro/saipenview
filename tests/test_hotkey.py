"""Tests for saipenview.hotkey — global hotkey listener with debounce."""

from __future__ import annotations


class TestHotkeyListener:
    def test_create_and_stop(self):
        """Creating and stopping a HotkeyListener doesn't crash."""
        from saipenview.hotkey import HotkeyListener

        events = []
        listener = HotkeyListener(on_toggle=lambda: events.append("toggle"), hotkeys=["ctrl+alt+x"])
        listener.start()
        listener.stop()
        # No assertion on events — hotkey won't fire without actual keypress

    def test_stop_before_start(self):
        """Stopping a listener that was never started is safe."""
        from saipenview.hotkey import HotkeyListener

        listener = HotkeyListener(on_toggle=lambda: None)
        listener.stop()  # Should not raise

    def test_set_hotkeys(self):
        """Changing hotkeys stops old listener and starts new one."""
        from saipenview.hotkey import HotkeyListener

        listener = HotkeyListener(on_toggle=lambda: None)
        listener.set_hotkeys(["ctrl+alt+z"])  # Should not crash
        listener.stop()

    def test_multiple_hotkeys(self):
        """Listener can accept multiple hotkey combos."""
        from saipenview.hotkey import HotkeyListener

        listener = HotkeyListener(on_toggle=lambda: None, hotkeys=["ctrl+alt+x", "alt+f15"])
        assert listener._hotkeys == ["ctrl+alt+x", "alt+f15"]
        listener.start()
        listener.stop()

    def test_default_hotkeys(self):
        """Default hotkeys come from DEFAULTS."""
        from saipenview.hotkey import DEFAULT_HOTKEYS

        assert "ctrl+alt+x" in DEFAULT_HOTKEYS

    def test_debounce_rate(self):
        """Debounce timer should prevent rapid re-fires."""
        import time

        from saipenview.hotkey import HotkeyListener

        call_count = 0

        def track():
            nonlocal call_count
            call_count += 1

        listener = HotkeyListener(on_toggle=track, hotkeys=["ctrl+alt+9"])

        # Simulate rapid calls through _debounced_toggle
        listener._debounced_toggle()  # First call — fires
        listener._debounced_toggle()  # Within debounce window — blocked
        time.sleep(0.35)  # Wait past debounce
        listener._debounced_toggle()  # After debounce — fires

        assert call_count == 2  # First and third should fire, second blocked
