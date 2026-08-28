"""Single-instance guard — ensures only one SAIPENVIEW process runs at a time.

Second launch detects the existing TCP listener and sends "SHOW" to bring the
existing window to front, then exits. No dependency on pywebview or any GUI
library — purely socket + threading, so tests can import it freely.
"""

from __future__ import annotations

import ctypes
import socket
import sys
import threading
import time
from ctypes import wintypes

SINGLE_INSTANCE_PORT = 47189
# Versioned SHOW handshake. A requesting instance sends _SHOW_MAGIC; the owner
# replies with _SHOW_ACK before raising its window. Lets the second launch tell
# the difference between "an instance heard me" and "the port is just dead".
_SHOW_MAGIC = b"SAIPENVIEW-SHOW\n"
_SHOW_ACK = b"SAIPENVIEW-ACK\n"

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


class SingleInstanceGuard:
    """Ensures only one instance runs at a time. Second launch brings existing window to front."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT):
        self.port = port
        self._server_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._mutex = None
        self._mutex_owned = False
        # Namespaced by port so the single-instance guarantee is scoped to the
        # port the app actually listens on, while still surviving stale /
        # lingering sockets that TCP-only detection would misread as "another
        # instance is already running".
        self._mutex_name = f"Global\\SAIPENVIEW_SINGLE_INSTANCE_{self.port}"

    def _try_bind(self) -> socket.socket | None:
        """Bind + listen, or None if the port is not available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", self.port))
            # Backlog of 1 meant a single unaccepted connection filled the
            # queue and the OS started REFUSING new ones. Combined with a
            # handler that stalls the accept loop, that turned "bring the
            # existing window to front" into "no launch ever works again".
            # Deliberately NOT SO_REUSEADDR -- on Windows that flag lets a
            # second process bind a port already in active use, which would
            # defeat the single-instance guarantee this class exists for.
            sock.listen(16)
        except OSError:
            return None
        return sock

    def _handoff(self) -> bool:
        """Ask a live instance to show itself. False if nobody answered."""
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(("127.0.0.1", self.port))
            client.sendall(_SHOW_MAGIC)
            # T-40/W2-030: must read the versioned ACK before closing so the
            # requester distinguishes "live owner heard us" from "port was open
            # but nothing answered". A bare send with no read returns True even
            # when the owner never processed the SHOW request.
            ack = client.recv(64)
            client.close()
            return bool(ack and _SHOW_ACK in ack)
        except OSError:
            return False

    def acquire(self, on_show_request=None) -> bool:
        """True = we own the instance and the app should run.

        False means, and ONLY means, that a live instance answered (via the
        named mutex / SHOW handshake) and was asked to show itself -- so this
        process can exit quietly.

        Ownership is decided by a Windows named mutex first: it is immune to the
        stale-socket failure mode that pure TCP detection suffers (a killed
        process leaves a TIME_WAIT/CLOSE_WAIT socket behind, but the kernel
        releases the mutex the instant the owner dies). On platforms without
        named mutexes we fall back to the original TCP-only detection.
        """
        handle = _acquire_named_mutex(self._mutex_name)
        if handle:
            # We own the instance via the named mutex. Stand up the SHOW
            # listener if the port is free; a stale socket holding the port is
            # no longer fatal -- the mutex already proves we are the owner.
            self._mutex = handle
            self._mutex_owned = True
            sock = self._try_bind()
            if sock is None:
                print(
                    f"SAIPENVIEW: port {self.port} is held but nothing answers "
                    "it. Starting without the single-instance listener -- a "
                    "second launch will not be able to raise this window.",
                    file=sys.stderr,
                )
            else:
                self._server_sock = sock
                if on_show_request:
                    self._start_listen_loop(on_show_request)
            return True
        if handle is False:
            # Another live instance owns the mutex: hand it the SHOW and exit
            # quietly. This is the canonical second-launch path.
            self._handoff()
            return False
        # Named mutexes unavailable (non-Windows): fall back to TCP-only.
        return self._acquire_tcp(on_show_request)

    def _acquire_tcp(self, on_show_request) -> bool:
        """Legacy TCP-only single-instance detection (non-Windows fallback)."""
        sock = self._try_bind()

        if sock is None:
            if self._handoff():
                return False  # live instance woken -- correct quiet exit

            for _ in range(_STALE_BIND_RETRIES):
                time.sleep(_STALE_BIND_DELAY)
                sock = self._try_bind()
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

        self._server_sock = sock
        if on_show_request:
            self._start_listen_loop(on_show_request)
        return True

    def _start_listen_loop(self, on_show_request):
        """Accept SHOW requests; reply with _SHOW_ACK and fire the callback."""

        def listen_loop():
            while not self._stop_event.is_set():
                try:
                    self._server_sock.settimeout(1.0)
                    conn, _ = self._server_sock.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                fire = False
                try:
                    conn.settimeout(2.0)
                    data = conn.recv(64)
                    if _SHOW_MAGIC in data or b"SHOW" in data:
                        # Acknowledge a versioned SHOW so the requester knows we
                        # heard it (only the v1 magic expects a reply).
                        if _SHOW_MAGIC in data:
                            try:
                                conn.sendall(_SHOW_ACK)
                            except OSError:
                                pass
                        fire = True
                except OSError:
                    fire = False
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                if fire:
                    # Off-thread on purpose: on_show_request is MainWindow.show,
                    # which touches the GUI and can block. Running it inline here
                    # meant one slow or deadlocked show wedged the accept loop
                    # forever, and with the queue full every subsequent launch
                    # was refused -- the app became unstartable until the
                    # process was killed. The loop must keep accepting no matter
                    # what a handler does.
                    threading.Thread(target=on_show_request, daemon=True).start()

        self._thread = threading.Thread(target=listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._mutex_owned and self._mutex:
            _release_named_mutex(self._mutex)
            self._mutex = None
            self._mutex_owned = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
