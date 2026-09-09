"""SAIPENVIEW entry point.

`python -m saipenview` launches the GUI. `python -m saipenview --dry-run`
validates config + path-safety layers without starting a window (T-138).
`python -m saipenview --service --host 127.0.0.1 --port 0` starts the headless
backend (no window) for SAIWORK embedding; it prints a single structured
`SAIPENVIEW_SERVICE_READY {json}` line on stdout with the bound port and the
per-launch token, then serves the authenticated loopback surface described in
`saipenview/service.py`.
"""

import argparse
import os
import sys
from pathlib import Path

from saipenview.config import config_path, load_config
from saipenview.paths import canonical, validate_file_path


def _run_service(args: argparse.Namespace) -> int:
    from saipenview.guard import SINGLE_INSTANCE_PORT, SingleInstanceGuard
    from saipenview.service import run_service

    # CORE-004: the guard uses a FIXED global port for single-instance
    # detection (named mutex on Windows, TCP on other platforms). After
    # acquisition proves ownership, the TCP listener is released so the
    # user-specified service port is free for the HTTP server.
    guard = SingleInstanceGuard(port=SINGLE_INSTANCE_PORT)
    if not guard.acquire():
        print(
            "SAIPENVIEW: another instance already owns this service port; exiting.",
            file=sys.stderr,
        )
        return 1
    # CORE-004: release the guard's TCP listener now that ownership is
    # proven. The named mutex (Windows) retains the ownership signal; the
    # service can now bind args.port without EADDRINUSE.
    guard.release_listener()

    try:
        import signal

        service = run_service(host=args.host, port=args.port, token=args.token)

        def _stop(*_a, **_k) -> None:
            service.stop()
            guard.stop()

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        service.wait()
        service.stop()
        guard.stop()
        return 0
    except Exception as e:  # noqa: BLE001 - surface start failure on stderr, exit non-zero
        print(f"SAIPENVIEW service failed to start: {e}", file=sys.stderr)
        guard.stop()
        return 1


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


def _silence_windows_hard_errors() -> None:
    """Make failed drive access return an error instead of a modal dialog.

    The scanner walks whole drive roots, and Windows' default error mode
    answers an unreadable volume (empty card reader, disconnected network
    mapping, spun-down removable) with a system-modal "There is no disk in the
    drive" box. That box plays a system sound and BLOCKS the worker thread that
    triggered it until someone clicks it -- on a hidden-at-launch window there
    is nothing to click, so the scan stalls and the app looks both noisy and
    slow. SEM_FAILCRITICALERRORS turns those into ordinary OSErrors, which the
    scanner already handles per root; SEM_NOOPENFILEERRORBOX does the same for
    the open-file variant. Process-wide, so worker threads inherit it.
    """
    if os.name != "nt":
        return
    import ctypes

    SEM_FAILCRITICALERRORS = 0x0001
    SEM_NOOPENFILEERRORBOX = 0x8000
    try:
        ctypes.windll.kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX
        )
    except (AttributeError, OSError) as e:  # pragma: no cover - platform guard
        print(f"SAIPENVIEW: SetErrorMode failed: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(prog="saipenview")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config and path-safety layers, exit, no GUI",
    )
    parser.add_argument(
        "--service",
        action="store_true",
        help="headless backend mode (no window) for SAIWORK embedding",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind host (loopback only; default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="bind port (0 = ephemeral; default 0)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="per-launch session token (default: generated randomly)",
    )
    args = parser.parse_args()
    _silence_windows_hard_errors()
    if args.dry_run:
        return _dry_run()
    if args.service:
        return _run_service(args)

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

        # Deliberately no MessageBox: every icon-carrying Win32 dialog plays a
        # system sound, and the app must stay silent. The non-zero exit is the
        # visible signal instead -- run.bat polls the launched process and logs
        # the failure, which a modal dialog used to mask by keeping the process
        # alive past the launcher's 5s window.
        print(
            f"SAIPENVIEW failed to start: {e}\nSee {crash_log} for details.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
