"""Wires tray icon, global hotkey, and main window together with single-instance guard."""

from __future__ import annotations

import socket
import threading

import webview

from saipenview.api import Api
from saipenview.hotkey import HotkeyListener
from saipenview.tray import build_tray_icon
from saipenview.ui.window import MainWindow

SINGLE_INSTANCE_PORT = 47189


class SingleInstanceGuard:
    """Ensures only one instance runs at a time. Second launch brings existing window to front."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT):
        self.port = port
        self._server_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(self, on_show_request=None) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", self.port))
            sock.listen(1)
            self._server_sock = sock
        except OSError:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect(("127.0.0.1", self.port))
                client.sendall(b"SHOW\n")
                client.close()
            except OSError:
                pass
            return False

        if on_show_request:

            def listen_loop():
                while not self._stop_event.is_set():
                    try:
                        self._server_sock.settimeout(1.0)
                        conn, _ = self._server_sock.accept()
                        data = conn.recv(64)
                        conn.close()
                        if b"SHOW" in data:
                            on_show_request()
                    except TimeoutError:
                        continue
                    except OSError:
                        break

            self._thread = threading.Thread(target=listen_loop, daemon=True)
            self._thread.start()

        return True

    def stop(self):
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None


def run() -> int:
    guard = SingleInstanceGuard()
    api = Api()
    window = MainWindow(api=api, api_ref=api)
    api._window = window

    if not guard.acquire(on_show_request=window.show):
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
