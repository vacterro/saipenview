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

# The two characters that are both hotkey syntax and real keys.
_SEPARATORS = (",", "+")

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
    """Rewrite ``"ctrl+q"`` into a form ``keyboard.add_hotkey`` accepts, with
    the character keys pinned to their US positions.

    Returns one of three shapes, all of which `keyboard` parses correctly:

    * an ``int`` scan code, for a single pinned character key;
    * a ``tuple`` of key tokens -- names for modifiers and named keys, ``int``
      scan codes for pinned characters -- for a one-step combo;
    * the original ``str``, for a multi-step combo like ``"ctrl+a, b"``, where
      `keyboard`'s own parsing is used unchanged.

    Only character keys are pinned. Modifiers, F-keys, ``esc`` and ``space``
    keep going through `keyboard`, which is already layout-independent for
    those and knows about the left/right and numpad duplicates this table has
    no business restating.

    **Do not return `keyboard.parse_hotkey`'s output from here.** That was the
    v0.1.8 shape and it is silently wrong: `add_hotkey` re-parses whatever it
    is given with `parse_hotkey_combinations`, whose first branch is
    ``if _is_number(hotkey) or len(hotkey) == 1``. A parsed ONE-STEP hotkey is
    a 1-tuple, so it matched that branch and was read as a single key whose
    "alternatives" were the modifiers -- turning ctrl+shift+alt+q into "ctrl OR
    shift OR alt OR q". Every SAIPENVIEW hotkey then fired on a bare modifier
    press, including the kill hotkey, whose handler is `os._exit(0)`. The app
    shut itself down within seconds of any typing, with no crash and no log.
    The shapes above are the ones `parse_hotkey` handles as intended.

    Raises ValueError for a combo `keyboard` itself cannot parse, so the
    caller's per-combo error handling behaves exactly as it did before.
    """
    steps = _split_outside_keys(combo.lower(), ",")
    if len(steps) != 1:
        # Multi-step ("press this, then that"). Pinning would need a shape
        # `keyboard` has no unambiguous spelling for, and these are not
        # SAIPENVIEW hotkeys anyway -- hand the string back untouched.
        return combo

    tokens: list[str | int] = []
    for raw in _split_outside_keys(steps[0], "+"):
        name = raw.strip()
        if not name:
            # A trailing or doubled separator: let keyboard reject it, so the
            # error the caller sees is the one it always was.
            return combo
        scan = _US_SCAN_CODES.get(name)
        if scan is not None:
            tokens.append(scan)
        else:
            # Validate now rather than at registration, so a bad name raises
            # here and start() reports THIS combo instead of a later one.
            keyboard.key_to_scan_codes(name)
            tokens.append(name)

    # A 1-tuple would hit that same `len(hotkey) == 1` branch, so a lone key
    # goes back as the bare scan code, which is the documented spelling.
    return tokens[0] if len(tokens) == 1 else tuple(tokens)


def _split_outside_keys(text: str, sep: str) -> list[str]:
    """Split on ``sep``, except where ``sep`` IS the key being named.

    ``,`` and ``+`` are both separators in a hotkey string and both real keys
    on a keyboard, so a naive ``split`` cannot express either of them alone:
    ``","`` split on ``","`` is two empty strings, not the comma key, and
    ``"ctrl+,"`` loses its comma the same way. A separator only separates once
    a key has been read, so the character immediately after any separator --
    either separator, which is why both are named here -- is taken literally.
    """
    parts: list[str] = []
    buf = ""
    at_key_start = True
    for ch in text:
        if ch == sep and not at_key_start:
            parts.append(buf)
            buf = ""
            at_key_start = True
        else:
            buf += ch
            at_key_start = ch in _SEPARATORS
    parts.append(buf)
    return parts


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
