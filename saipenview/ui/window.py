"""Main window: single toggleable pywebview window, vintage-themed shell."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

import webview

from saipenview import zone_picker

STATIC_DIR = Path(__file__).parent / "static"

_GA = ctypes.windll.user32.GetActiveWindow
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010

_GEOMETRY_COOLDOWN = 2.0


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def _work_area() -> tuple[int, int, int, int]:
    """Usable desktop rect (excludes taskbar) of the monitor under this window.

    GetMonitorInfoW REQUIRES cbSize to be filled in before the call; without it
    the call just returns FALSE and leaves the buffer zeroed -- no exception, so
    the old version silently returned (0,0,0,0) and every caller computed a
    0x0 "quarter". Harmless while geometry writes were themselves broken
    (T-061), instantly visible as a tiny window once they started working.
    Hence: set cbSize, check the return value, and sanity-check the rect.
    """
    fallback = (0, 0, 1920, 1080)
    try:
        mon = ctypes.windll.user32.MonitorFromWindow(_GA(), 2)  # NEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            print(
                "SAIPENVIEW: GetMonitorInfoW failed, using 1920x1080 fallback",
                file=sys.stderr,
            )
            return fallback
        r = mi.rcWork
        if r.right - r.left <= 0 or r.bottom - r.top <= 0:
            print(
                f"SAIPENVIEW: degenerate work area {(r.left, r.top, r.right, r.bottom)}, using fallback",
                file=sys.stderr,
            )
            return fallback
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
        print(
            f"SAIPENVIEW: work-area query failed, using 1920x1080 fallback: {e}",
            file=sys.stderr,
        )
        return fallback


class MainWindow:
    def __init__(self, api=None, api_ref=None):
        self._api = api
        cfg = api.get_config() if api else {}
        width = cfg.get("window_width") or 480
        height = cfg.get("window_height") or 360
        x = cfg.get("window_x")
        y = cfg.get("window_y")
        show_on_launch = cfg.get("show_on_launch", True)

        kwargs = {
            "title": "SAIPENVIEW",
            "url": str(STATIC_DIR / "index.html"),
            "js_api": api_ref or api,
            "width": width,
            "height": height,
            "hidden": not show_on_launch,
            "on_top": cfg.get("always_on_top", True),
        }
        if x is not None and y is not None:
            kwargs["x"] = x
            kwargs["y"] = y

        self._icon_path = STATIC_DIR / "saipen_icon.ico"
        self._window = webview.create_window(**kwargs)
        self._visible = show_on_launch
        self._allow_close = False
        self._frameless = False
        self._window.events.closing += self._on_closing
        self._window.events.loaded += self._set_window_icon
        self._window.events.shown += self._set_window_icon
        self._window.events.shown += self._on_shown
        self._window.events.moved += self._on_moved_or_resized
        self._window.events.resized += self._on_moved_or_resized
        self._snap_idx = 0
        self._last_geometry_save = 0.0
        self._geometry_stop = threading.Event()
        self._geometry_thread: threading.Thread | None = None

    def _on_moved_or_resized(self) -> None:
        now = time.monotonic()
        if now - self._last_geometry_save >= _GEOMETRY_COOLDOWN:
            self._last_geometry_save = now
            self._save_geometry()

    def _geometry_periodic(self) -> None:
        while not self._geometry_stop.wait(15):
            self._save_geometry()

    def _save_geometry(self) -> None:
        if not self._api:
            return
        try:
            w = self._window.width
            h = self._window.height
            x = self._window.x
            y = self._window.y
            if w and h:
                self._api.save_view_config(
                    {
                        "window_width": w,
                        "window_height": h,
                        "window_x": x,
                        "window_y": y,
                    }
                )
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: window geometry save failed: {e}", file=sys.stderr)

    def _set_window_icon(self) -> None:
        if not self._icon_path.exists():
            return
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if not hwnd:
                return
            ico = str(self._icon_path)
            hSmall = ctypes.windll.user32.LoadImageW(
                None, ico, _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE
            )
            hBig = ctypes.windll.user32.LoadImageW(
                None, ico, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE
            )
            if hSmall:
                ctypes.windll.user32.SendMessageW(
                    hwnd, _WM_SETICON, _ICON_SMALL, hSmall
                )
            if hBig:
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, hBig)
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: taskbar icon set failed: {e}", file=sys.stderr)

    def _on_closing(self):
        self._save_geometry()
        if self._allow_close:
            return None
        self.hide()
        return False

    def _on_shown(self) -> None:
        # WinForms `Form.Shown` fires exactly ONCE, on first display -- it does
        # NOT re-fire on a later Show() after Hide(). So this is only good for
        # one-time startup work (the geometry thread); `_visible` MUST be
        # maintained by show()/hide() themselves. Driving `_visible` from here
        # was T-049's regression: after the first hide it stayed False forever,
        # so toggle() always took the show branch and the window never hid
        # again -- exactly the "works once then stops" report (T-068).
        self._visible = True
        self._start_geometry_thread()

    def _start_geometry_thread(self) -> None:
        if self._geometry_thread is None:
            self._geometry_stop.clear()
            self._geometry_thread = threading.Thread(
                target=self._geometry_periodic, daemon=True
            )
            self._geometry_thread.start()

    def _stop_geometry_thread(self) -> None:
        """Signal the periodic saver to exit and let show() start a fresh one.

        Deliberately does NOT join: this runs on the UI/hotkey path and the
        thread is a daemon sitting in a 15s `wait()`, so joining would stall a
        hide by up to 15 seconds. Dropping the reference is what lets
        _start_geometry_thread's `is None` guard build a new one on show.
        """
        self._geometry_stop.set()
        self._geometry_thread = None

    def minimize(self) -> None:
        """Minimize window to taskbar."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: minimize failed: {e}", file=sys.stderr)

    def maximize(self) -> None:
        """Maximize window."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: maximize failed: {e}", file=sys.stderr)

    def restore(self) -> None:
        """Restore from minimized or maximized."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: restore failed: {e}", file=sys.stderr)

    def _force_foreground(self) -> None:
        """Restore from minimized and genuinely take the foreground.

        Plain SetForegroundWindow SILENTLY NO-OPS when the calling process
        doesn't already own the foreground -- which is exactly the hotkey case,
        since the user is in some other app when they press it. Windows only
        grants the change if the calling thread shares an input queue with the
        current foreground thread, so attach to it for the duration of the
        call, then detach. That's the documented way; no focus-stealing hack.
        """
        u = ctypes.windll.user32
        try:
            hwnd = u.FindWindowW(None, "SAIPENVIEW")
            if not hwnd:
                return
            if u.IsIconic(hwnd):
                u.ShowWindow(hwnd, 9)  # SW_RESTORE
            else:
                u.ShowWindow(hwnd, 5)  # SW_SHOW

            fg = u.GetForegroundWindow()
            cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            fg_tid = u.GetWindowThreadProcessId(fg, None) if fg else 0

            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(u.AttachThreadInput(fg_tid, cur_tid, True))
            try:
                u.BringWindowToTop(hwnd)
                u.SetForegroundWindow(hwnd)
                u.SetActiveWindow(hwnd)
            finally:
                if attached:
                    u.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: force_foreground failed: {e}", file=sys.stderr)

    def _toggle_frameless_style(self, frameless: bool) -> None:
        """Remove or restore the window titlebar via Windows API.

        When frameless: strips WS_CAPTION|WS_SYSMENU for no titlebar and
        adds WS_EX_TOOLWINDOW for a clean floating-panel look (no taskbar
        entry — the tray icon is still the primary access point). When
        restoring, re-adds the titlebar styles and removes TOOLWINDOW."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if not hwnd:
                return
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_CAPTION = 0x00C00000  # WS_BORDER | WS_DLGFRAME
            WS_SYSMENU = 0x00080000
            WS_EX_TOOLWINDOW = 0x00000080
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            if frameless:
                style &= ~(WS_CAPTION | WS_SYSMENU)
                ex |= WS_EX_TOOLWINDOW
            else:
                style |= WS_CAPTION | WS_SYSMENU
                ex &= ~WS_EX_TOOLWINDOW

            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER,
            )
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(
                f"SAIPENVIEW: toggle_frameless({frameless}) failed: {e}",
                file=sys.stderr,
            )

    def toggle_frameless(self) -> bool:
        self._frameless = not self._frameless
        self._toggle_frameless_style(self._frameless)
        return self._frameless

    def _notify_visibility(self, visible: bool) -> None:
        """Tell the page whether anyone can actually see it.

        SAIPENVIEW is a tray app: it spends most of its life hidden, and until
        this existed the page kept polling on its 5s timer the whole time --
        re-reading every known project's `.saipen/` files and rebuilding the
        detail pane's innerHTML for nobody. `document.hidden` does NOT cover
        this: a pywebview `hide()` is a native window hide, and the Page
        Visibility API never fires for it, so the page has no way to find out
        on its own.

        Best-effort by design. A failed notify must never break show/hide --
        the worst case is the page keeps polling, which is exactly the old
        behaviour.

        Dispatched on a throwaway daemon thread, and THAT IS LOAD-BEARING.
        `evaluate_js` is synchronous: it marshals onto the WebView2 UI thread
        and waits for a result. Called inline it put a blocking call on the
        hotkey thread and, worse, inside SingleInstanceGuard's accept loop
        (which runs on_show_request -> show() inline). A just-hidden window
        could stall that call indefinitely, wedging the listener; with its
        listen(1) backlog then full, every later launch had its connection
        refused, could not bind either, and exited 0 in silence -- the app
        stopped starting at all. Never block a caller for a notification that
        is only ever an optimization.
        """

        def _push() -> None:
            try:
                self._window.evaluate_js(
                    f"window.__saipenSetVisible && window.__saipenSetVisible({str(visible).lower()})"
                )
            except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
                print(
                    f"SAIPENVIEW: visibility notify({visible}) failed: {e}",
                    file=sys.stderr,
                )

        threading.Thread(target=_push, daemon=True).start()

    def show(self) -> None:
        self._window.show()
        # Set here, NOT in the `shown` event -- that only fires once (see
        # _on_shown). This is what makes toggle() keep alternating (T-068).
        self._visible = True
        self._start_geometry_thread()
        self._save_geometry()
        self._force_foreground()
        # After _force_foreground, so the page's catch-up poll starts against a
        # window that is already up: the refresh lands as the user is looking.
        self._notify_visibility(True)

    def focus(self) -> None:
        """Bring window to foreground even if minimized, pywebview-independent."""
        self.show()

    def hide(self) -> None:
        self._save_geometry()
        self._window.hide()
        self._visible = False
        self._notify_visibility(False)
        # The 15s geometry autosave exists to catch moves/resizes; a hidden
        # window has none, so leaving the thread running just rewrites the same
        # config.json values to disk forever. show() restarts it.
        self._stop_geometry_thread()

    def toggle(self) -> None:
        self.hide() if self._visible else self.show()

    def set_always_on_top(self, enabled: bool) -> None:
        try:
            self._window.on_top = enabled
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(
                f"SAIPENVIEW: set_always_on_top({enabled}) failed: {e}", file=sys.stderr
            )

    def destroy(self) -> None:
        self._geometry_stop.set()
        self._geometry_thread = None
        self._save_geometry()
        self._allow_close = True
        self._window.destroy()

    def force_destroy(self) -> None:
        self._save_geometry()
        import os

        os._exit(0)

    def move_by(self, dx: int, dy: int) -> None:
        # pywebview 6.x: x/y/width/height are READ-ONLY properties -- assigning
        # to them raises "property 'x' of 'Window' object has no setter".
        # move()/resize() are the real API. (This was silently swallowed by a
        # bare `except: pass` until T-027 made it log; window dragging, Ctrl+Q
        # snap and the zone picker were all dead the whole time.)
        try:
            self._window.move(self._window.x + dx, self._window.y + dy)
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: move_by({dx},{dy}) failed: {e}", file=sys.stderr)

    def _is_in_quarter(self, x, y, w, h, qx, qy, qw, qh, tol=20) -> bool:
        return (
            abs(x - qx) <= tol
            and abs(y - qy) <= tol
            and abs(w - qw) <= tol
            and abs(h - qh) <= tol
        )

    def show_zone_picker(self) -> None:
        zone_picker.show(self, self._api)

    def cycle_snap_corner(self) -> None:
        if not self._visible:
            self.show()
        left, top, right, bottom = _work_area()
        aw = right - left
        ah = bottom - top
        qw = aw // 2
        qh = ah // 2

        # Labels MUST match the geometry on the same row: `top + ah//2` is the
        # LOWER half and `left + aw//2` is the RIGHT half. Every label used to
        # be rotated one step ahead of its own rect, so the toast confidently
        # named the wrong corner on all four presses (T-073).
        rects = [
            (left + aw // 2, top + ah // 2, qw, qh, "Bottom-Right"),
            (left, top + ah // 2, qw, qh, "Bottom-Left"),
            (left, top, qw, qh, "Top-Left"),
            (left + aw // 2, top, qw, qh, "Top-Right"),
        ]

        try:
            cx = self._window.x
            cy = self._window.y
            cw = self._window.width
            ch = self._window.height

            cur = -1
            for i, (rx, ry, rw, rh, _) in enumerate(rects):
                if self._is_in_quarter(cx, cy, cw, ch, rx, ry, rw, rh, 30):
                    cur = i
                    break

            if cur < 0:
                nxt = 0
            else:
                nxt = (cur + 1) % 4

            nx, ny, nw, nh, nxtLabel = rects[nxt]
            self._window.resize(nw, nh)
            self._window.move(nx, ny)
            self._snap_idx = nxt
            self._save_geometry()

            # Show feedback toast — runs in background thread but evaluate_js
            # queues execution on the webview's main thread.
            self._window.evaluate_js(f'showToast("Snapped {nxtLabel}", "info", 1500)')
        except Exception as e:  # noqa: BLE001 - defensive catch for pywebview window operations
            print(f"SAIPENVIEW: cycle_snap_corner failed: {e}", file=sys.stderr)
            try:
                self._window.evaluate_js('showToast("Snap failed", "error", 3000)')
            except Exception as toast_err:  # noqa: BLE001 - defensive catch for pywebview window operations
                # Best-effort UI notice about an error already printed above;
                # still say so rather than vanish, per T-027's policy.
                print(
                    f"SAIPENVIEW: could not show snap-failure toast: {toast_err}",
                    file=sys.stderr,
                )
