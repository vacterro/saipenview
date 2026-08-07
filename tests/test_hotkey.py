"""Tests for saipenview.hotkey — global hotkey listener with debounce."""

from __future__ import annotations

import keyboard
import pytest

from saipenview.hotkey import _US_SCAN_CODES, HotkeyListener, to_layout_independent


def _combos(combo):
    """What `keyboard` will ACTUALLY match, for our form of a combo.

    This is the assertion the first version of these tests was missing. They
    checked what `to_layout_independent` returned and never what `add_hotkey`
    made of it -- and `add_hotkey` re-parses its argument, so the two are not
    the same question.
    """
    steps = keyboard.parse_hotkey_combinations(to_layout_independent(combo))
    return [set(c) for c in steps[0]]


def _flat(combo):
    """The scan codes every match of a one-step combo requires."""
    sets = _combos(combo)
    return [set.intersection(*sets)] if sets else []


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
        assert all(16 in c for c in _combos("ctrl+q"))

    def test_every_match_needs_the_modifier_AND_the_letter(self):
        """The v0.1.8 regression, stated as an assertion.

        `add_hotkey` re-parses with `parse_hotkey_combinations`, whose first
        branch is `if _is_number(hotkey) or len(hotkey) == 1`. A parsed
        one-step hotkey IS a 1-tuple, so it was read as a single key whose
        alternatives were the modifiers: ctrl+shift+alt+q became "ctrl OR
        shift OR alt OR q". The kill hotkey's handler is os._exit(0), so the
        app shut itself down within seconds of any typing, no crash, no log.
        """
        for combo, size in (("ctrl+q", 2), ("ctrl+alt+x", 3), ("ctrl+shift+alt+q", 4)):
            matches = _combos(combo)
            assert matches, combo
            for c in matches:
                assert len(c) == size, f"{combo} matches on {len(c)} key(s): {c}"

    def test_a_bare_modifier_never_matches(self):
        # The exact firing condition that killed the process.
        ctrl_codes = set(keyboard.key_to_scan_codes("ctrl"))
        for c in _combos("ctrl+shift+alt+q"):
            assert not c <= ctrl_codes, f"bare ctrl would fire the hotkey: {c}"

    def test_our_matches_are_a_subset_of_the_string_form(self):
        # Pinning may only ever NARROW what keyboard would have matched --
        # never add a combination of its own invention.
        for combo in ("ctrl+q", "ctrl+alt+x", "alt+f14", "ctrl+shift+alt+q"):
            ours = {frozenset(c) for c in _combos(combo)}
            theirs = {
                frozenset(c) for c in keyboard.parse_hotkey_combinations(combo)[0]
            }
            assert ours <= theirs, combo
            assert ours, combo

    def test_every_letter_and_digit_is_pinned(self):
        for name, scan in _US_SCAN_CODES.items():
            assert _flat(name) == [{scan}], name

    def test_case_is_irrelevant(self):
        assert to_layout_independent("Ctrl+Q") == to_layout_independent("ctrl+q")

    def test_modifiers_still_carry_their_left_right_variants(self):
        # Pinning is only for character keys; ctrl must keep matching either
        # side of the keyboard, which the US table has no business restating.
        assert len(_combos("ctrl+q")) > 1

    def test_function_keys_are_left_to_keyboard(self):
        # alt+f14 still maps through keyboard (no entry in the table); the
        # shipped snap default is ctrl+q (T-180), which is pinned instead.
        for c in _combos("alt+f14"):
            assert len(c) == 2

    def test_multi_step_combo_is_handed_back_to_keyboard(self):
        # Pinning a multi-step combo has no unambiguous spelling keyboard
        # accepts, and these are not SAIPENVIEW hotkeys. The string goes back
        # untouched, and keyboard still parses it into two steps.
        assert to_layout_independent("ctrl+shift+a, b") == "ctrl+shift+a, b"
        assert len(keyboard.parse_hotkey_combinations("ctrl+shift+a, b")) == 2

    def test_a_separator_can_also_be_a_key(self):
        # `,` and `+` are both hotkey syntax and real keys, so a naive split
        # cannot express either alone: "," split on "," is two empty strings.
        # Caught by test_every_letter_and_digit_is_pinned, but only once the
        # `keyboard` name tables had lazily filled in enough aliases for the
        # fallback to return something other than {51} -- i.e. intermittently,
        # depending on what ran before it.
        assert _flat(",") == [{_US_SCAN_CODES[","]}]
        assert all(_US_SCAN_CODES[","] in c for c in _combos("ctrl+,"))
        assert _combos("+")
        for c in _combos("ctrl++"):
            assert len(c) == 2

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
        listener = HotkeyListener(
            on_toggle=lambda: events.append("toggle"), hotkeys=["ctrl+alt+x"]
        )
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

        listener = HotkeyListener(
            on_toggle=lambda: None, hotkeys=["ctrl+alt+x", "alt+f15"]
        )
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
