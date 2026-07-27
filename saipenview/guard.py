"""Single-instance guard — ensures only one SAIPENVIEW process runs at a time.

Second launch detects the existing TCP listener and sends "SHOW" to bring the
existing window to front, then exits. No dependency on pywebview or any GUI
library — purely socket + threading, so tests can import it freely.
"""

from __future__ import annotations

import socket
import threading

SINGLE_INSTANCE_PORT = 47189


class SingleInstanceGuard:
    """Ensures only one instance runs at a time. Second launch brings existing window to front."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT):
        self.port = port
        self._server_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(self, on_show_request=None) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", self.port))
            sock.listen(1)
            self._server_sock = sock
        except OSError:
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect(("127.0.0.1", self.port))
                client.sendall(b"SHOW\n")
                client.close()
            except OSError:
                pass
            return False

        if on_show_request:

            def listen_loop():
                while not self._stop_event.is_set():
                    try:
                        self._server_sock.settimeout(1.0)
                        conn, _ = self._server_sock.accept()
                        data = conn.recv(64)
                        conn.close()
                        if b"SHOW" in data:
                            on_show_request()
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
