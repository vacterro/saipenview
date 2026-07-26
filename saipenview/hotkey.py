"""Global hotkey registration for show/hide toggle with debounce."""

from __future__ import annotations

import time
from typing import Callable, Iterable

import keyboard

from saipenview.config import DEFAULTS

DEFAULT_HOTKEYS = DEFAULTS["hotkeys"]
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
        self.stop()
        for combo in self._hotkeys:
            keyboard.add_hotkey(combo, self._debounced_toggle)
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
