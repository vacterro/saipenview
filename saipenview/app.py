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
    # W2-005: Api's constructor already starts a live SaipenWatcher, so the
    # api is registered for cleanup IMMEDIATELY -- before MainWindow or the
    # guard -- so any failure after this point unwinds it.
    api = Api()
    # CORE-015/W2-005: track started components so the finally-style cleanup
    # can unwind them in reverse order, even if an exception fires mid-startup.
    _started: list[str] = ["api"]
    tray = None
    hotkeys = None
    snap_hotkey = None
    kill_hotkey = None

    def _cleanup():
        """Stop every started component in reverse order, logging but never
        re-raising each individual cleanup failure so later cleanups always
        run. api.stop() and guard.stop() are idempotent."""
        for name in reversed(_started):
            try:
                if name == "kill_hotkey" and kill_hotkey:
                    kill_hotkey.stop()
                elif name == "snap_hotkey" and snap_hotkey:
                    snap_hotkey.stop()
                elif name == "hotkeys" and hotkeys:
                    hotkeys.stop()
                elif name == "api":
                    api.stop()
                elif name == "tray" and tray:
                    tray.stop()
                elif name == "guard":
                    guard.stop()
            except Exception as e:  # noqa: BLE001
                import sys

                print(f"SAIPENVIEW: cleanup {name} failed: {e}", file=sys.stderr)

    try:
        window = MainWindow(api=api, api_ref=api)
        api._window = window

        if not guard.acquire(on_show_request=window.show):
            _cleanup()
            return 0
        # W2-005: guard ownership is registered the instant acquire() returns
        # True, never deferred until after api.start().
        _started.insert(0, "guard")

        tray = build_tray_icon(
            on_toggle=window.toggle, on_quit=lambda: window.destroy()
        )
        tray_thread = threading.Thread(target=tray.run, daemon=True)
        tray_thread.start()
        _started.append("tray")

        hotkeys = HotkeyListener(
            on_toggle=window.toggle, hotkeys=api.get_config()["hotkeys"]
        )
        hotkeys.start()
        _started.append("hotkeys")
        api.set_hotkey_callback(hotkeys.set_hotkeys)
        api.set_quit_callback(lambda: window.destroy())

        snap_hotkey = HotkeyListener(
            on_toggle=window.cycle_snap_corner, hotkeys=api.get_config()["snap_hotkey"]
        )
        snap_hotkey.start()
        _started.append("snap_hotkey")
        api.set_snap_hotkey_callback(snap_hotkey.set_hotkeys)

        kill_hotkey = HotkeyListener(
            on_toggle=window.force_destroy, hotkeys=["ctrl+shift+alt+q"]
        )
        kill_hotkey.start()
        _started.append("kill_hotkey")

        api.start()
        webview.start()
    except Exception:  # noqa: BLE001
        _cleanup()
        raise
    else:
        _cleanup()
    import sys

    sys.exit(0)
