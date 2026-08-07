"""Wires tray icon, global hotkey, and main window together with single-instance guard."""

from __future__ import annotations

import threading

import webview

from saipenview.api import Api
from saipenview.guard import SingleInstanceGuard
from saipenview.hotkey import HotkeyListener
from saipenview.tray import build_tray_icon
from saipenview.ui.window import MainWindow


def run() -> int:
    guard = SingleInstanceGuard()
    api = Api()
    window = MainWindow(api=api, api_ref=api)
    api._window = window

    if not guard.acquire(on_show_request=window.show):
        # A second instance hands off SHOW and exits -- but the Api it just
        # built owns a watcher thread and an event-bus subscription, and a
        # leaked handler would keep firing on later watcher events. Clean up
        # before returning (T-190).
        api.stop()
        return 0

    tray = build_tray_icon(on_toggle=window.toggle, on_quit=lambda: window.destroy())
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()

    hotkeys = HotkeyListener(
        on_toggle=window.toggle, hotkeys=api.get_config()["hotkeys"]
    )
    hotkeys.start()
    api.set_hotkey_callback(hotkeys.set_hotkeys)
    api.set_quit_callback(lambda: window.destroy())

    snap_hotkey = HotkeyListener(
        on_toggle=window.cycle_snap_corner, hotkeys=api.get_config()["snap_hotkey"]
    )
    snap_hotkey.start()
    api.set_snap_hotkey_callback(snap_hotkey.set_hotkeys)

    kill_hotkey = HotkeyListener(
        on_toggle=window.force_destroy, hotkeys=["ctrl+shift+alt+q"]
    )
    kill_hotkey.start()

    api.start()
    webview.start()
    api.stop()
    hotkeys.stop()
    snap_hotkey.stop()
    kill_hotkey.stop()
    tray.stop()
    guard.stop()
    import sys

    sys.exit(0)
