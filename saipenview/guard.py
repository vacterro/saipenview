"""Single-instance guard — ensures only one SAIPENVIEW process runs at a time.

Second launch detects the existing TCP listener and sends "SHOW" to bring the
existing window to front, then exits. No dependency on pywebview or any GUI
library — purely socket + threading, so tests can import it freely.
"""

from __future__ import annotations

import socket
import sys
import threading
import time

SINGLE_INSTANCE_PORT = 47189
# A socket left behind by a killed process clears on its own, but not
# instantly. Short, bounded retries -- long enough to outlast the usual
# lingering close, short enough that a real launch never feels stalled.
_STALE_BIND_RETRIES = 4
_STALE_BIND_DELAY = 0.25


class SingleInstanceGuard:
    """Ensures only one instance runs at a time. Second launch brings existing window to front."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT):
        self.port = port
        self._server_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

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
            client.sendall(b"SHOW\n")
            client.close()
        except OSError:
            return False
        return True

    def acquire(self, on_show_request=None) -> bool:
        """True = we own the instance and the app should run.

        False means, and ONLY means, that a live instance answered and was
        asked to show itself -- so this process can exit quietly.

        The distinction is the whole point. "Port is taken" covers two states
        that used to be collapsed into one silent `return False`:

          a) a healthy instance is listening -> hand it the SHOW, exit quietly.
             This class working as designed.
          b) the port is held by a socket nobody is serving -- a wedged accept
             loop whose backlog is full, or a lingering FIN_WAIT/CLOSE_WAIT
             from a killed process. Nothing will ever answer.

        Treating (b) as (a) is what made the app SILENTLY REFUSE TO START:
        bind refused, connect refused, exit code 0, no window, no error, and a
        user double-clicking a launcher that does nothing. So a failed handoff
        is never again accepted as proof another instance owns the port. We
        retry the bind (a lingering socket usually clears in seconds), and if
        the port stays unusable we start ANYWAY without the show-listener and
        say so on stderr. A running app with one missing convenience always
        beats no app at all.
        """
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

            def listen_loop():
                while not self._stop_event.is_set():
                    try:
                        self._server_sock.settimeout(1.0)
                        conn, _ = self._server_sock.accept()
                        try:
                            conn.settimeout(2.0)
                            data = conn.recv(64)
                        finally:
                            conn.close()
                        if b"SHOW" in data:
                            # Off-thread on purpose: on_show_request is
                            # MainWindow.show, which touches the GUI and can
                            # block. Running it inline here meant one slow or
                            # deadlocked show wedged the accept loop forever,
                            # and with the queue full every subsequent launch
                            # was refused -- the app became unstartable until
                            # the process was killed. The loop must keep
                            # accepting no matter what a handler does.
                            threading.Thread(
                                target=on_show_request, daemon=True
                            ).start()
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
