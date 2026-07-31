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
        self._registered: list[str] = []
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
                keyboard.add_hotkey(combo, self._debounced_toggle)
            except (ValueError, ImportError) as e:
                print(
                    f"SAIPENVIEW: hotkey {combo!r} not registered: {e}",
                    file=sys.stderr,
                )
                continue
            self._registered.append(combo)

    def stop(self) -> None:
        for combo in self._registered:
            try:
                keyboard.remove_hotkey(combo)
            except KeyError:
                pass
        self._registered.clear()

    def set_hotkeys(self, hotkeys: Iterable[str]) -> None:
        self._hotkeys = list(hotkeys)
        self.start()
