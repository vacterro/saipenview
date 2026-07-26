"""Ctrl+Q zone picker -- visual screen zone selector at cursor position.

Runs on a single persistent Tk root owned by one dedicated thread, created
once and kept alive for the process lifetime. Tkinter is not thread-safe:
the previous version called `tk.Tk()` fresh from whatever thread happened to
fire the hotkey (the `keyboard` library's own hook thread, itself not the
main thread) on every single press. Creating a new Tcl interpreter from a
different OS thread each time corrupts Tcl's Windows notifier window state
and crashes pythonw.exe with "A breakpoint has been reached" (a DebugBreak
trap) -- exactly the symptom Ctrl+Q was producing. Fix: one Tk() root, one
thread, forever; each request opens a `Toplevel` on that same root via a
thread-safe queue instead of spinning up a new interpreter.
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import tkinter as tk
from ctypes import wintypes

PICKER_SIZE = 200
ZONE_PAD = 4

_request_q: queue.Queue = queue.Queue()
_tk_thread: threading.Thread | None = None
_tk_thread_lock = threading.Lock()


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def _get_cursor_pos():
    pt = wintypes.POINT(0, 0)
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _get_monitor_work_area(cursor_x, cursor_y):
    pt = wintypes.POINT(cursor_x, cursor_y)
    hMon = ctypes.windll.user32.MonitorFromPoint(pt, 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    ctypes.windll.user32.GetMonitorInfoW(hMon, ctypes.byref(mi))
    r = mi.rcWork
    return r.left, r.top, r.right, r.bottom


def _snap(main_window, x, y, w, h):
    # pywebview 6.x: x/y/width/height are read-only -- must use move()/resize().
    # Same latent break as MainWindow.move_by/cycle_snap_corner (see window.py).
    try:
        main_window._window.resize(w, h)
        main_window._window.move(x, y)
        main_window._save_geometry()
    except Exception as e:
        print(f"SAIPENVIEW: zone snap failed: {e}", file=sys.stderr)


def _draw_zones(canvas, pw, ph, toplevel, main_window, zones):
    half = pw // 2
    pad = ZONE_PAD
    rects = [
        (pad, pad, half - pad, half - pad),
        (half + pad, pad, pw - pad, half - pad),
        (pad, half + pad, half - pad, ph - pad),
        (half + pad, half + pad, pw - pad, ph - pad),
    ]
    colors = ["#3a3a2a", "#4a3a2a", "#2a3a3a", "#2a2a3a"]
    hover_colors = ["#5a5a3a", "#6a5a3a", "#3a5a5a", "#3a3a5a"]
    labels = ["TL", "TR", "BL", "BR"]

    for i, (x1, y1, x2, y2) in enumerate(rects):
        tag = f"z{i}"
        canvas.create_rectangle(
            x1 + 2,
            y1 + 2,
            x2 - 2,
            y2 - 2,
            fill=colors[i],
            outline="#c8a84e",
            width=1,
            tags=tag,
        )
        canvas.create_text(
            (x1 + x2) // 2,
            (y1 + y2) // 2,
            text=labels[i],
            fill="#c8a84e",
            font=("Verdana", 18, "bold"),
            tags=tag,
        )
        canvas.tag_bind(
            tag,
            "<Button-1>",
            lambda e, idx=i: _on_pick(idx, toplevel, main_window, zones),
        )
        canvas.tag_bind(
            tag,
            "<Enter>",
            lambda e, t=tag, idx=i: canvas.itemconfig(t, fill=hover_colors[idx]),
        )
        canvas.tag_bind(
            tag,
            "<Leave>",
            lambda e, t=tag, idx=i: canvas.itemconfig(t, fill=colors[idx]),
        )


def _on_pick(idx, toplevel, main_window, zones):
    _, zx, zy, zw, zh = zones[idx]
    _snap(main_window, zx, zy, zw, zh)
    try:
        toplevel.destroy()
    except Exception as e:
        print(f"SAIPENVIEW: zone picker window destroy failed: {e}", file=sys.stderr)


def _open_picker(root, main_window):
    """Runs on the persistent Tk thread only -- opens one Toplevel per request."""
    cx, cy = _get_cursor_pos()
    left, top, right, bottom = _get_monitor_work_area(cx, cy)
    aw = right - left
    ah = bottom - top

    zones = [
        ("TL", left, top, aw // 2, ah // 2),
        ("TR", left + aw // 2, top, aw // 2, ah // 2),
        ("BL", left, top + ah // 2, aw // 2, ah // 2),
        ("BR", left + aw // 2, top + ah // 2, aw // 2, ah // 2),
    ]

    toplevel = tk.Toplevel(root)
    toplevel.overrideredirect(True)
    toplevel.attributes("-topmost", True)
    toplevel.attributes("-alpha", 0.92)

    pw = PICKER_SIZE
    ph = PICKER_SIZE
    px = max(left, min(cx - pw // 2, right - pw))
    py = max(top, min(cy - ph // 2, bottom - ph))
    toplevel.geometry(f"{pw}x{ph}+{px}+{py}")

    canvas = tk.Canvas(
        toplevel, width=pw, height=ph, bg="#1a1a1a", highlightthickness=0
    )
    canvas.pack(fill="both", expand=True)

    _draw_zones(canvas, pw, ph, toplevel, main_window, zones)

    toplevel.bind("<Escape>", lambda e: toplevel.destroy())
    toplevel.bind("<Key-1>", lambda e: _on_pick(0, toplevel, main_window, zones))
    toplevel.bind("<Key-2>", lambda e: _on_pick(1, toplevel, main_window, zones))
    toplevel.bind("<Key-3>", lambda e: _on_pick(2, toplevel, main_window, zones))
    toplevel.bind("<Key-4>", lambda e: _on_pick(3, toplevel, main_window, zones))

    toplevel.focus_force()
    toplevel.grab_set()


def _poll_queue(root):
    """Runs on the Tk thread via root.after -- drains requests from other threads."""
    try:
        while True:
            main_window = _request_q.get_nowait()
            _open_picker(root, main_window)
    except queue.Empty:
        pass
    root.after(50, _poll_queue, root)


def _tk_thread_main():
    root = tk.Tk()
    root.withdraw()
    root.after(50, _poll_queue, root)
    root.mainloop()


def _ensure_tk_thread():
    global _tk_thread
    with _tk_thread_lock:
        if _tk_thread is None or not _tk_thread.is_alive():
            _tk_thread = threading.Thread(target=_tk_thread_main, daemon=True)
            _tk_thread.start()


def show(main_window, api):
    """Called from any thread (typically the global-hotkey listener thread).
    Queues the request instead of creating a new tk.Tk() here -- see module
    docstring for why a fresh interpreter per call crashed the app."""
    _ensure_tk_thread()
    _request_q.put(main_window)
