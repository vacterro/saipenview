"""Main window: single toggleable pywebview window, vintage-themed shell."""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

import webview

import saipenview.zone_picker as zone_picker

STATIC_DIR = Path(__file__).parent / "static"

_GA = ctypes.windll.user32.GetActiveWindow
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010

_GEOMETRY_COOLDOWN = 2.0


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


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
            print("SAIPENVIEW: GetMonitorInfoW failed, using 1920x1080 fallback", file=sys.stderr)
            return fallback
        r = mi.rcWork
        if r.right - r.left <= 0 or r.bottom - r.top <= 0:
            print(f"SAIPENVIEW: degenerate work area {(r.left, r.top, r.right, r.bottom)}, using fallback", file=sys.stderr)
            return fallback
        return (r.left, r.top, r.right, r.bottom)
    except Exception as e:
        print(f"SAIPENVIEW: work-area query failed, using 1920x1080 fallback: {e}", file=sys.stderr)
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
                self._api.save_view_config({
                    "window_width": w,
                    "window_height": h,
                    "window_x": x,
                    "window_y": y,
                })
        except Exception as e:
            print(f"SAIPENVIEW: window geometry save failed: {e}", file=sys.stderr)

    def _set_window_icon(self) -> None:
        if not self._icon_path.exists():
            return
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "SAIPENVIEW")
            if not hwnd:
                return
            ico = str(self._icon_path)
            hSmall = ctypes.windll.user32.LoadImageW(None, ico, _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE)
            hBig = ctypes.windll.user32.LoadImageW(None, ico, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
            if hSmall:
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, hSmall)
            if hBig:
                ctypes.windll.user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, hBig)
        except Exception as e:
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
            self._geometry_thread = threading.Thread(target=self._geometry_periodic, daemon=True)
            self._geometry_thread.start()

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
                u.ShowWindow(hwnd, 9)      # SW_RESTORE
            else:
                u.ShowWindow(hwnd, 5)      # SW_SHOW

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
        except Exception as e:
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
                style |= (WS_CAPTION | WS_SYSMENU)
                ex &= ~WS_EX_TOOLWINDOW

            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
            )
        except Exception as e:
            print(f"SAIPENVIEW: toggle_frameless({frameless}) failed: {e}", file=sys.stderr)

    def toggle_frameless(self) -> bool:
        self._frameless = not self._frameless
        self._toggle_frameless_style(self._frameless)
        return self._frameless

    def show(self) -> None:
        self._window.show()
        # Set here, NOT in the `shown` event -- that only fires once (see
        # _on_shown). This is what makes toggle() keep alternating (T-068).
        self._visible = True
        self._start_geometry_thread()
        self._save_geometry()
        self._force_foreground()

    def focus(self) -> None:
        """Bring window to foreground even if minimized, pywebview-independent."""
        self.show()

    def hide(self) -> None:
        self._save_geometry()
        self._window.hide()
        self._visible = False

    def toggle(self) -> None:
        self.hide() if self._visible else self.show()

    def set_always_on_top(self, enabled: bool) -> None:
        try:
            self._window.on_top = enabled
        except Exception as e:
            print(f"SAIPENVIEW: set_always_on_top({enabled}) failed: {e}", file=sys.stderr)

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
        except Exception as e:
            print(f"SAIPENVIEW: move_by({dx},{dy}) failed: {e}", file=sys.stderr)

    def _is_in_quarter(self, x, y, w, h, qx, qy, qw, qh, tol=20) -> bool:
        return abs(x - qx) <= tol and abs(y - qy) <= tol and abs(w - qw) <= tol and abs(h - qh) <= tol

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
            (left,           top + ah // 2, qw, qh, "Bottom-Left"),
            (left,           top,           qw, qh, "Top-Left"),
            (left + aw // 2, top,           qw, qh, "Top-Right"),
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
        except Exception as e:
            err_msg = f"SAIPENVIEW: cycle_snap_corner failed: {e}"
            print(err_msg, file=sys.stderr)
            try:
                self._window.evaluate_js(f'showToast("Snap failed", "error", 3000)')
            except Exception:
                pass
