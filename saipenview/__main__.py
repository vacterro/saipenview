"""SAIPENVIEW entry point.

`python -m saipenview` launches the GUI. `python -m saipenview --dry-run`
validates config + path-safety layers without starting a window (T-138).
"""

import argparse
import os
import sys
from pathlib import Path

from saipenview.config import config_path, load_config
from saipenview.paths import canonical, validate_file_path


def _dry_run() -> int:
    """Validate config and persisted paths; no GUI. Exit 0 on clean config."""
    cfg = load_config()
    problems = 0
    print(f"config: {config_path()}")

    scan_roots = cfg.get("scan_roots")
    if scan_roots is None:
        print("scan_roots: auto (all local drives)")
    else:
        print(f"scan_roots: {len(scan_roots)} root(s)")
        for r in scan_roots:
            c = canonical(r)
            state = "ok" if os.path.exists(c) else "MISSING (quarantined)"
            if state != "ok":
                problems += 1
            print(f"  {c}  {state}")
            if c != r:
                print(f"    canonical form differs from stored {r!r}")
                problems += 1

    for key in ("pinned_roots", "hidden_roots"):
        vals = cfg.get(key) or []
        print(f"{key}: {len(vals)} root(s)")
        for r in vals:
            c = canonical(r)
            state = "ok" if os.path.exists(c) else "MISSING (quarantined, non-fatal)"
            print(f"  {c}  {state}")

    selected = cfg.get("selected_root")
    if selected:
        print(f"selected_root: {canonical(selected)}")

    # Frontend file-op boundary must accept its own doc set (regression guard).
    if scan_roots:
        allowed = validate_file_path(
            str(Path(scan_roots[0]) / ".saipen" / "STATE.md"), scan_roots
        )
        if not allowed[0]:
            print(f"  BOUNDARY SELF-CHECK FAIL: {allowed[1]}")
            problems += 1

    if problems:
        print(f"dry-run: FAIL ({problems} problem(s))")
        return 1
    print("dry-run: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="saipenview")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config and path-safety layers, exit, no GUI",
    )
    args = parser.parse_args()
    if args.dry_run:
        return _dry_run()

    import ctypes
    import traceback
    from pathlib import Path

    from saipenview.app import run

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
