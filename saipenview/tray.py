"""System tray icon: toggle window, quit."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pystray
from PIL import Image

ICON_PATH = Path(__file__).parent / "assets" / "tray_icon.png"


def build_tray_icon(on_toggle: Callable[[], None], on_quit: Callable[[], None]) -> pystray.Icon:
    image = Image.open(ICON_PATH)
    menu = pystray.Menu(
        pystray.MenuItem("Show/Hide", lambda icon, item: on_toggle(), default=True),
        pystray.MenuItem("Quit", lambda icon, item: on_quit()),
    )
    return pystray.Icon("saipenview", image, "SAIPENVIEW", menu)
