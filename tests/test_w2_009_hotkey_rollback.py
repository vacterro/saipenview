"""T-19 / W2-009: HotkeyListener.set_hotkeys strict rollback preserves old state."""
import pytest
from unittest.mock import MagicMock, patch


def test_strict_rollback_restores_old_combo_not_new():
    """When strict=True and registration fails, rollback must use the OLD
    hotkey definitions (captured before _hotkeys was overwritten), not the
    new ones that set_hotkeys installed ahead of time.
    """
    from saipenview.hotkey import HotkeyListener

    listener = HotkeyListener(on_toggle=MagicMock(), hotkeys=["ctrl+a", "ctrl+b"])
    # Simulate: ctrl+a registers, ctrl+b fails.
    with patch("saipenview.hotkey.keyboard") as mock_kb:
        mock_kb.add_hotkey.side_effect = [
            MagicMock(),  # ctrl+a succeeds
            ValueError("bad combo"),  # ctrl+b fails
        ]
        mock_kb.remove_hotkey.side_effect = KeyError("not found")

        with pytest.raises(ValueError):
            listener.set_hotkeys(["ctrl+a", "ctrl+b"])

        # After failure, the old combo (ctrl+a) must be re-registered.
        add_calls = [c.args[0] for c in mock_kb.add_hotkey.call_args_list]
        # The rollback should have re-registered ctrl+a (the first old combo),
        # not tried ctrl+b which is the new failing combo.
        added_combos = [str(c) for c in add_calls]
        # ctrl+a scan code is ('ctrl', 30)
        assert any("('ctrl', 30)" in c for c in added_combos), f"expected ctrl+a in {added_combos}"


def test_repeated_failed_replacements_preserve_prior_set():
    """Calling set_hotkeys with a bad combo repeatedly must leave the
    listener's registered handles identical to the original set -- zero
    accumulation of leaked handles.
    """
    from saipenview.hotkey import HotkeyListener

    listener = HotkeyListener(on_toggle=MagicMock(), hotkeys=["ctrl+a"])
    listener.start()  # register initial hotkey
    call_count = [0]

    def track_add(*args, **kwargs):
        call_count[0] += 1
        raise ValueError("always fails")

    with patch("saipenview.hotkey.keyboard") as mock_kb:
        mock_kb.add_hotkey.side_effect = track_add
        mock_kb.remove_hotkey.side_effect = KeyError("not found")

        with pytest.raises(ValueError):
            listener.set_hotkeys(["ctrl+x"])  # bad combo

        # The total add_hotkey calls should not accumulate beyond what is
        # needed: initial registration (1) + rollback re-register (1) = 2.
        assert call_count[0] <= 2
        # The listener's internal _registered list must match the original.
        assert len(listener._registered) == 1
        # And _hotkeys must be restored to the original set.
        assert listener._hotkeys == ["ctrl+a"]
