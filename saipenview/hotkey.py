"""Global hotkey registration for show/hide toggle."""

from __future__ import annotations

from typing import Callable, Iterable

import keyboard

from saipenview.config import DEFAULTS

DEFAULT_HOTKEYS = DEFAULTS["hotkeys"]


class HotkeyListener:
    """Registers one or more global hotkeys that all call the same callback."""

    def __init__(
        self, on_toggle: Callable[[], None], hotkeys: Iterable[str] = DEFAULT_HOTKEYS
    ):
        self._on_toggle = on_toggle
        self._hotkeys = list(hotkeys)
        self._registered: list[str] = []

    def start(self) -> None:
        self.stop()
        for combo in self._hotkeys:
            keyboard.add_hotkey(combo, self._on_toggle)
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
