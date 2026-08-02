"""Global hotkey registration for show/hide toggle with debounce."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterable
from typing import cast

import keyboard

from saipenview.config import DEFAULTS

DEFAULT_HOTKEYS: list[str] = cast(list[str], DEFAULTS["hotkeys"])
_DEBOUNCE_SECS = 0.3

# Physical key positions on a US QWERTY keyboard, by scan code. Scan codes are
# what the hardware sends; the letter printed on the cap is whatever the ACTIVE
# Windows layout decides to paint on it afterwards. `keyboard.add_hotkey("ctrl+q")`
# resolves "q" through that layout table, so with a Russian layout selected the
# combo either binds to the wrong physical key or -- when no Latin layout is
# installed at all -- raises ValueError and the hotkey silently never registers.
# Binding the position instead means ctrl+q is the key labelled Q on a US board
# regardless of what the user is currently typing in, which is the only reading
# of "ctrl+q" that makes sense for a GLOBAL hotkey.
_US_SCAN_CODES: dict[str, int] = {
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
    "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "-": 12, "=": 13,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20,
    "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
    "[": 26, "]": 27,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34,
    "h": 35, "j": 36, "k": 37, "l": 38, ";": 39, "'": 40,
    "`": 41, "\\": 43,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48,
    "n": 49, "m": 50, ",": 51, ".": 52, "/": 53,
}


def to_layout_independent(combo: str):
    """Turn ``"ctrl+q"`` into the parsed scan-code form ``keyboard`` accepts.

    Only the character keys are pinned to their US positions. Everything else
    -- modifiers, F-keys, ``esc``, ``space`` -- keeps going through
    ``keyboard.key_to_scan_codes``, which is already layout-independent for
    those and knows about left/right and numpad duplicates this table has no
    business restating.

    Raises ValueError for a combo ``keyboard`` itself cannot parse, so the
    caller's per-combo error handling behaves exactly as it did before.
    """
    steps = []
    for step in combo.lower().split(","):
        keys = []
        for name in step.split("+"):
            name = name.strip()
            if not name:
                # A literal "+" or a trailing separator: hand the whole thing
                # back to keyboard rather than guessing at what was meant.
                return keyboard.parse_hotkey(combo)
            scan = _US_SCAN_CODES.get(name)
            keys.append((scan,) if scan is not None else tuple(keyboard.key_to_scan_codes(name)))
        steps.append(tuple(keys))
    return tuple(steps)


class HotkeyListener:
    """Registers one or more global hotkeys that all call the same callback.

    Holds the key repeat from OS typematic (the "disco" effect) by
    debouncing: the callback won't fire more than once per
    ``_DEBOUNCE_SECS`` seconds, even if the keyboard library delivers
    repeated key-down events while the user holds the hotkey.
    """

    def __init__(
        self, on_toggle: Callable[[], None], hotkeys: Iterable[str] = DEFAULT_HOTKEYS
    ):
        self._on_toggle = on_toggle
        self._hotkeys = list(hotkeys)
        # The remover callables add_hotkey hands back, not the combo strings:
        # the registered hotkey is now a parsed scan-code tuple, so the string
        # is no longer a key `keyboard.remove_hotkey` can look anything up by.
        self._registered: list[Callable[[], None]] = []
        self._last_fire: float = 0.0

    def _debounced_toggle(self) -> None:
        now = time.monotonic()
        if now - self._last_fire < _DEBOUNCE_SECS:
            return
        self._last_fire = now
        self._on_toggle()

    def start(self) -> None:
        """Register every combo, and keep going when one of them won't take.

        Previously a single bad combo aborted the loop: `keyboard.add_hotkey`
        raises ValueError on an unparseable name, so one stale or mistyped
        entry left every LATER binding unregistered and propagated the error
        into whatever called start() -- including set_hotkeys() from the
        Settings save path, where it took out the working bindings the user
        already had. Now each combo stands alone: the good ones register, the
        bad one is reported, and the app keeps a usable toggle.
        """
        self.stop()
        for combo in self._hotkeys:
            try:
                remover = keyboard.add_hotkey(
                    to_layout_independent(combo), self._debounced_toggle
                )
            except (ValueError, ImportError) as e:
                print(
                    f"SAIPENVIEW: hotkey {combo!r} not registered: {e}",
                    file=sys.stderr,
                )
                continue
            self._registered.append(remover)

    def stop(self) -> None:
        for remover in self._registered:
            try:
                keyboard.remove_hotkey(remover)
            except KeyError:
                pass
        self._registered.clear()

    def set_hotkeys(self, hotkeys: Iterable[str]) -> None:
        self._hotkeys = list(hotkeys)
        self.start()
