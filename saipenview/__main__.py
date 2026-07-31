"""SAIPENVIEW entry point."""

import ctypes
import sys
import traceback
from pathlib import Path

from saipenview.app import run


def main() -> int:
    try:
        return run()
    except Exception as e:  # noqa: BLE001 - top-level crash handler
        # Write crash to crash.log alongside the executable/script
        crash_log = (
            Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
            / "crash.log"
        )
        error_text = traceback.format_exc()
        try:
            crash_log.write_text(error_text, encoding="utf-8")
        except OSError:
            pass

        # Display MessageBoxW so silent failures don't happen
        msg = (
            f"SAIPENVIEW failed to start.\\n\\n{str(e)}\\n\\nSee crash.log for details."
        )
        ctypes.windll.user32.MessageBoxW(
            0, msg, "SAIPENVIEW Fatal Error", 0x10
        )  # 0x10 = MB_ICONERROR
        return 1


if __name__ == "__main__":
    sys.exit(main())
