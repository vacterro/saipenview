"""Single-instance guard — ensures only one SAIPENVIEW process runs at a time.

Second launch detects the existing TCP listener and sends "SHOW" to bring the
existing window to front, then exits. No dependency on pywebview or any GUI
library — purely socket + threading, so tests can import it freely.
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import tempfile
import threading
import time
from ctypes import wintypes

SINGLE_INSTANCE_PORT = 47189
SINGLE_INSTANCE_NAME = "Global\\SAIPENVIEW_SINGLE_INSTANCE"
_SHOW_MAGIC = b"SAIPENVIEW-SHOW\n"
_SHOW_ACK = b"SAIPENVIEW-ACK\n"
_LEGACY_SHOW = b"SHOW\n"
_FRAME_MAX = max(len(_SHOW_MAGIC), len(_SHOW_ACK), len(_LEGACY_SHOW))

# A socket left behind by a killed process clears on its own, but not
# instantly. Short, bounded retries -- long enough to outlast the usual
# lingering close, short enough that a real launch never feels stalled.
_STALE_BIND_RETRIES = 4
_STALE_BIND_DELAY = 0.25


def _acquire_named_mutex(name):
    """Windows named mutex as the primary ownership signal.

    Returns the mutex handle if WE own it, ``False`` if another instance
    already holds it, or ``None`` when named mutexes are unavailable
    (non-Windows). A named mutex is immune to the stale-socket failure mode
    that pure TCP detection suffers: a killed process leaves a TIME_WAIT /
    CLOSE_WAIT socket behind, but the kernel releases the mutex the instant
    the owning process dies.
    """
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        return None
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    return handle


def _release_named_mutex(handle):
    if not handle:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(handle)
    except OSError:
        pass


def _acquire_process_lock():
    if sys.platform == "win32":
        return _acquire_named_mutex(SINGLE_INSTANCE_NAME)
    try:
        import fcntl

        path = os.path.join(tempfile.gettempdir(), "saipenview-single-instance.lock")
        handle = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(handle)
            return False
        return handle
    except (ImportError, OSError):
        return None


def _release_process_lock(handle):
    if handle is None:
        return
    if sys.platform == "win32":
        _release_named_mutex(handle)
        return
    try:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_UN)
    except (ImportError, OSError):
        pass
    try:
        os.close(handle)
    except OSError:
        pass


class SingleInstanceGuard:
    """Ensures only one instance runs at a time. Second launch brings existing window to front."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT):
        self.port = port
        self._server_sock: socket.socket | None = None
        self._server_socks: list[socket.socket] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._threads: list[threading.Thread] = []
        self._mutex = None
        self._mutex_owned = False
        self._mutex_name = SINGLE_INSTANCE_NAME
        self._ownership = None

    def _try_bind(self, port: int) -> socket.socket | None:
        """Bind + listen, or None if the port is not available."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            # Backlog of 1 meant a single unaccepted connection filled the
            # queue and the OS started REFUSING new ones. Combined with a
            # handler that stalls the accept loop, that turned "bring the
            # existing window to front" into "no launch ever works again".
            # Deliberately NOT SO_REUSEADDR -- on Windows that flag lets a
            # second process bind a port already in active use, which would
            # defeat the single-instance guarantee this class exists for.
            sock.listen(16)
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            return None
        return sock

    def _bind_owned_listeners(self) -> bool:
        socks = []
        for port in dict.fromkeys((self.port, SINGLE_INSTANCE_PORT)):
            sock = self._try_bind(port)
            if sock is not None:
                socks.append(sock)
        self._server_socks = socks
        self._server_sock = socks[0] if socks else None
        return bool(socks)

    def _handoff(self) -> bool:
        """Ask live instance to show itself. False if nobody answered."""
        ports = [SINGLE_INSTANCE_PORT]
        if self.port != SINGLE_INSTANCE_PORT:
            ports.append(self.port)
        for port in ports:
            try:
                with socket.create_connection(
                    ("127.0.0.1", port), timeout=2.0
                ) as client:
                    client.settimeout(2.0)
                    client.sendall(_SHOW_MAGIC)
                    ack = b""
                    while len(ack) <= _FRAME_MAX:
                        chunk = client.recv(_FRAME_MAX + 1 - len(ack))
                        if not chunk:
                            break
                        ack += chunk
                        if ack.endswith(b"\n"):
                            break
                    if ack == _SHOW_ACK:
                        return True
            except OSError:
                pass
        return False

    def acquire(self, on_show_request=None) -> bool:
        """Acquire application-wide ownership and optionally start SHOW listener."""
        handle = _acquire_process_lock()
        if handle:
            self._ownership = handle
            self._mutex = handle if sys.platform == "win32" else None
            self._mutex_owned = sys.platform == "win32"
            if not self._bind_owned_listeners():
                print(
                    f"SAIPENVIEW: port {self.port} is held but nothing answers "
                    "it. Starting without the single-instance listener -- a "
                    "second launch will not be able to raise this window.",
                    file=sys.stderr,
                )
            elif on_show_request:
                for sock in self._server_socks:
                    self._start_listen_loop(on_show_request, sock)
            return True
        if handle is False:
            self._handoff()
            return False
        return self._acquire_tcp(on_show_request)

    def _acquire_tcp(self, on_show_request) -> bool:
        """Legacy TCP-only single-instance detection (non-Windows fallback)."""

        sock = self._try_bind(self.port)

        if sock is None:
            if self._handoff():
                return False  # live instance woken -- correct quiet exit

            for _ in range(_STALE_BIND_RETRIES):
                time.sleep(_STALE_BIND_DELAY)
                sock = self._try_bind(self.port)
                if sock is not None:
                    break
                if self._handoff():
                    return False  # an instance finished starting up meanwhile

        if sock is None:
            print(
                f"SAIPENVIEW: port {self.port} is held but nothing answers it. "
                "Starting without the single-instance listener -- a second "
                "launch will not be able to raise this window.",
                file=sys.stderr,
            )
            return True

        self._server_socks = [sock]
        self._server_sock = sock
        if on_show_request:
            self._start_listen_loop(on_show_request, sock)
        return True

    def _start_listen_loop(self, on_show_request, server_sock=None):
        """Accept SHOW requests; reply with _SHOW_ACK and fire the callback."""
        server_sock = server_sock or self._server_sock
        if server_sock is None:
            return

        def listen_loop():
            while not self._stop_event.is_set():
                try:
                    server_sock.settimeout(1.0)
                    conn, _ = server_sock.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                fire = False
                try:
                    conn.settimeout(2.0)
                    data = b""
                    while len(data) <= _FRAME_MAX:
                        chunk = conn.recv(_FRAME_MAX + 1 - len(data))
                        if not chunk:
                            break
                        data += chunk
                        if data.endswith(b"\n"):
                            break
                    if data == _SHOW_MAGIC:
                        try:
                            conn.sendall(_SHOW_ACK)
                        except OSError:
                            pass
                        fire = True
                    elif data == _LEGACY_SHOW:
                        fire = True
                except OSError:
                    fire = False
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                if fire:
                    threading.Thread(target=on_show_request, daemon=True).start()

        thread = threading.Thread(target=listen_loop, daemon=True)
        self._threads.append(thread)
        if self._thread is None:
            self._thread = thread
        thread.start()

    def _close_listeners(self) -> None:
        for sock in self._server_socks:
            try:
                sock.close()
            except OSError:
                pass
        self._server_socks.clear()
        self._server_sock = None

    def release_listener(self) -> None:
        """Release TCP listener so another service can bind the port.

        CORE-004: after acquire() proves ownership (named mutex on Windows,
        or TCP bind on other platforms), TCP listener is no longer needed for
        single-instance detection. Releasing it frees port so HTTP service can
        bind user-specified port without collision. Named mutex (Windows)
        retains ownership signal.
        """
        self._close_listeners()
        self._stop_event.set()

    def stop(self):
        self._stop_event.set()
        if self._ownership is not None:
            _release_process_lock(self._ownership)
            self._ownership = None
            self._mutex = None
            self._mutex_owned = False
        self._close_listeners()
