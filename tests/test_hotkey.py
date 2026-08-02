"""Tests for saipenview.hotkey — global hotkey listener with debounce."""

from __future__ import annotations

import pytest

from saipenview.hotkey import _US_SCAN_CODES, HotkeyListener, to_layout_independent


def _flat(parsed):
    """All scan codes in a parsed hotkey, in order, as a list of sets."""
    return [set(key) for step in parsed for key in step]


class TestLayoutIndependence:
    """Global hotkeys must bind to physical key POSITIONS, not to whatever the
    active Windows layout happens to print on the cap.

    The bug: `keyboard.add_hotkey("ctrl+q")` resolves "q" through the active
    layout, so with a Russian layout selected the combo binds to the wrong
    physical key -- and on a machine with no Latin layout installed at all it
    raises ValueError and the hotkey silently never registers.
    """

    def test_letter_pins_to_the_us_position(self):
        # 16 is the physical key labelled Q on a US board. Nothing else.
        assert _flat(to_layout_independent("ctrl+q"))[-1] == {16}

    def test_every_letter_and_digit_is_pinned(self):
        for name, scan in _US_SCAN_CODES.items():
            assert _flat(to_layout_independent(name)) == [{scan}], name

    def test_case_is_irrelevant(self):
        assert to_layout_independent("Ctrl+Q") == to_layout_independent("ctrl+q")

    def test_modifiers_still_carry_their_left_right_variants(self):
        # Pinning is only for character keys; ctrl must keep matching either
        # side of the keyboard, which the US table has no business restating.
        assert len(_flat(to_layout_independent("ctrl+q"))[0]) > 1

    def test_function_keys_are_left_to_keyboard(self):
        # alt+f14 is the shipped snap default and has no entry in the table.
        assert len(_flat(to_layout_independent("alt+f14"))) == 2

    def test_multi_step_combo_keeps_its_steps(self):
        parsed = to_layout_independent("ctrl+shift+a, b")
        assert len(parsed) == 2
        assert _flat(parsed)[-1] == {_US_SCAN_CODES["b"]}

    def test_unknown_key_still_raises(self):
        # start() relies on this to report a bad combo and keep the others.
        with pytest.raises(ValueError):
            to_layout_independent("ctrl+nosuchkey")


class TestListenerRegistration:
    """stop() must be able to undo what start() did.

    The registered hotkey is a parsed scan-code tuple now, so the combo STRING
    is no longer a key `keyboard.remove_hotkey` can look anything up by -- the
    listener has to hold the remover `add_hotkey` returns.
    """

    def test_start_registers_every_combo_and_stop_removes_them(self, monkeypatch):
        import saipenview.hotkey as hk

        added, removed = [], []

        def fake_add(parsed, _cb):
            added.append(parsed)
            return lambda: None

        monkeypatch.setattr(hk.keyboard, "add_hotkey", fake_add)
        monkeypatch.setattr(hk.keyboard, "remove_hotkey", removed.append)

        listener = HotkeyListener(lambda: None, ["ctrl+q", "alt+f15"])
        listener.start()
        assert len(added) == 2
        assert added[0] == to_layout_independent("ctrl+q")

        listener.stop()
        assert len(removed) == 2
        assert all(callable(r) for r in removed)

    def test_one_bad_combo_does_not_take_out_the_others(self, monkeypatch, capsys):
        import saipenview.hotkey as hk

        added = []

        def fake_add(parsed, _cb):
            added.append(parsed)
            return lambda: None

        monkeypatch.setattr(hk.keyboard, "add_hotkey", fake_add)

        listener = HotkeyListener(lambda: None, ["nosuchkey", "ctrl+q"])
        listener.start()

        assert added == [to_layout_independent("ctrl+q")]
        assert "not registered" in capsys.readouterr().err


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
