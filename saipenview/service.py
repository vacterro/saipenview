"""Headless SAIPENVIEW service mode (SAIWORK embedding).

Runs the existing `Api` backend with NO pywebview window, tray, hotkeys or
desktop shell. Exposes a small authenticated HTTP surface on 127.0.0.1 so
SAIWORK can mount the SAIPENVIEW UI as an internal tab:

    GET  /health          -> deterministic liveness/identity, no auth
    POST /api/rpc         -> { method, args } -> { ok, result } | { ok:false, error }
    GET  /api/events      -> SSE stream of backend push events (token in query)

Security contract:
  * binds ONLY to 127.0.0.1
  * a per-launch secret token guards every RPC/SSE request
  * ONLY an explicit allowlist of `Api` methods is callable — arbitrary Python
    method invocation is impossible by construction
  * the existing `Api` methods retain all path validation, the protocol write
    coordinator, per-root locking and fingerprint/CAS checks untouched
  * startup prints ONE structured handshake line to stdout (the selected port
    and token); all backend logs go to stderr so they never corrupt it

CLI:
    python -m saipenview --service --host 127.0.0.1 --port 0
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from saipenview.api import Api
from saipenview.events import event_bus

# ── RPC allowlist ──────────────────────────────────────────────────────────
# The ONLY methods the service will dispatch. Every entry exists on `Api`.
# Everything else — including any future method or any private/dunder name —
# is rejected before the handler is ever touched.
ALLOWED_RPC_METHODS: frozenset[str] = frozenset(
    {
        # project scanning / discovery
        "get_projects",
        "refresh_known",
        "rescan",
        "get_status",
        "get_scan_progress",
        "get_scan_errors",
        "get_scan_error_log",
        "get_local_drives",
        "get_linked_worktrees",
        "get_hidden_projects",
        # project detail / state
        "get_project_detail",
        "get_config",
        "update_project_state",
        "toggle_pin",
        "hide_project",
        "unhide_project",
        # files
        "read_file_text",
        "write_file_text",
        "quick_search",
        # tickets / manual work / outbox
        "collect_outbox",
        "reorder_ticket",
        "toggle_ticket_status",
        "record_manual_work",
        "add_human_note",
        # agent lifecycle / status
        "launch_agent",
        "stop_agent",
        "send_agent_input",
        "get_agent_status",
        "get_agent_output",
        "get_agent_history",
        "get_agent_transcript",
        "get_last_agent_transcript",
        "list_running_agents",
        "run_command",
        # diff / commit / revert
        "get_diff",
        "commit_agent_work",
        "revert_agent_work",
        "delete_untracked_files",
        # config / ui preferences
        "save_view_config",
        "set_scan_roots",
        "set_exclude_dirs",
        "set_auto_scan",
        "set_sort_order",
        "set_locale",
        "set_theme",
        "set_zoom_level",
        "set_engine_overrides",
        "get_themes",
        "get_theme_tokens",
        "get_engines",
        "get_wiki_pages",
        "get_wiki_page",
        "get_locales",
    }
)

# Methods that exist on the desktop `Api` but MUST NOT cross the service
# boundary — they are desktop-shell responsibilities (SAIWORK owns them when
# embedded) or would open a native dialog in a headless process.
_DESKTOP_ONLY_METHODS = frozenset(
    {
        "quit",
        "minimize_window",
        "maximize_window",
        "close_window",
        "restore_window",
        "move_by",
        "set_frameless",
        "set_always_on_top",
        "set_hotkeys",
        "set_snap_hotkey",
        "set_autostart_enabled",
        "get_autostart_enabled",
        "browse_folder",
        "open_folder",
        "open_terminal",
        "open_editor",
        "clipboard_copy",
    }
)


class _ServiceError(Exception):
    """Reject an RPC before it reaches the backend."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class SaipenViewService:
    """Owns the `Api` backend + loopback HTTP server for embedded mode."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        auto_scan: bool = True,
    ) -> None:
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError(
                f"SAIPENVIEW service refuses to bind {host!r}: loopback only"
            )
        self._host = "127.0.0.1"
        self._port = port
        self._token = token or secrets.token_urlsafe(24)
        self._auto_scan = auto_scan
        self._api: Api | None = None
        self._server: ThreadingHTTPServer | None = None
        self._event_subscribers: set[threading.Condition] = set()
        self._subscriber_lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    # ── public lifecycle ────────────────────────────────────────────────────

    @property
    def token(self) -> str:
        return self._token

    @property
    def bound_port(self) -> int:
        return self._server.server_address[1] if self._server else -1

    def start(self) -> None:
        """Create the Api, wire the event bridge, start the HTTP server."""
        if self._api is None:
            self._api = Api()
            if not self._auto_scan:
                self._api._auto_scan = False
                self._api._config["auto_scan"] = False
            event_bus.subscribe("saipen.file_changed", self._on_file_changed)
            self._api.start()

        server = ThreadingHTTPServer((self._host, self._port), self._make_handler())
        server.handle_error = self._handle_server_error
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="saipenview-service", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Graceful shutdown: stop the HTTP server then the Api backend."""
        self._stopping.set()
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except OSError:
                pass
            self._server = None
        if self._api is not None:
            event_bus.unsubscribe("saipen.file_changed", self._on_file_changed)
            self._api.stop()
            self._api = None
        with self._subscriber_lock:
            for cond in list(self._event_subscribers):
                try:
                    with cond:
                        cond.notify_all()
                except RuntimeError:
                    pass
            self._event_subscribers.clear()
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=5)
        self._thread = None

    def _handle_server_error(self, request, client_address) -> None:
        """A client aborting mid-request (shutdown, navigation, tab close) is
        normal in a service embedded in a browser tab. Shut it up on stderr
        instead of dumping a socketserver traceback for every tab close."""
        import sys
        import traceback

        try:
            exc = sys.exc_info()[1]
            if isinstance(
                exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)
            ):
                return
            print(
                f"SAIPENVIEW service: request from {client_address} failed:",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
        except Exception:  # noqa: BLE001 - error reporting must never throw
            pass

    def wait(self) -> None:
        """Block the caller until stop() is requested (signal-driven shutdown)."""
        import time

        while not self._stopping.is_set():
            time.sleep(0.25)

    # ── event bridge (watcher -> SSE) ───────────────────────────────────────

    def _on_file_changed(self, data: dict) -> None:
        """Fan the structured file-change event out to every SSE subscriber."""
        payload = json.dumps(
            {
                "event": "file.changed",
                "root": data.get("root", ""),
                "file": data.get("file", ""),
                "origin": data.get("origin", "external"),
            }
        )
        with self._subscriber_lock:
            subscribers = list(self._event_subscribers)
        for cond in subscribers:
            try:
                queue = getattr(cond, "_sse_queue", None)
                if queue is not None:
                    queue.append(payload)
                with cond:
                    cond.notify_all()
            except RuntimeError:
                pass

    # ── RPC dispatch ────────────────────────────────────────────────────────

    def _dispatch(self, method: str, args: list[Any]) -> Any:
        if method not in ALLOWED_RPC_METHODS:
            if method in _DESKTOP_ONLY_METHODS:
                raise _ServiceError(
                    f"RPC {method!r} is a desktop-shell operation and is not "
                    "exposed by the SAIPENVIEW service",
                    403,
                )
            raise _ServiceError(f"RPC {method!r} is not allowlisted", 404)
        if self._api is None:
            raise _ServiceError("SAIPENVIEW service is not running", 503)
        fn = getattr(self._api, method, None)
        if fn is None or not callable(fn) or method.startswith("_"):
            raise _ServiceError(f"RPC {method!r} is not callable", 404)
        result = fn(*args)
        # JSON-safe serialisation check; the pywebview bridge would also marshal
        # this, so failing here surfaces the same contract violations early.
        json.dumps(result)
        return result

    def _check_auth(self, token: str | None) -> None:
        # Constant-ish comparison; the token is a high-entropy per-launch secret
        # so timing here is not a practical concern, but compare anyway.
        if not token or not secrets.compare_digest(token, self._token):
            raise _ServiceError("missing or invalid session token", 401)

    # ── handler factory ─────────────────────────────────────────────────────

    def _make_handler(self):
        service = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args) -> None:
                # Route request logs to stderr (the handshake owns stdout).
                print(
                    f"SAIPENVIEW service: {self.address_string()} {fmt % args}",
                    file=__import__("sys").stderr,
                )

            # -- shared helpers --

            def _send_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_error_json(self, status: int, message: str) -> None:
                self._send_json(status, {"ok": False, "error": message})

            def _auth_from_query(self) -> str | None:
                q = self.path.split("?", 1)
                if len(q) < 2:
                    return None
                for part in q[1].split("&"):
                    if part.startswith("token="):
                        return part[len("token=") :]
                return None

            # -- routes --

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/") or "/"
                if path == "/health":
                    from saipenview import __version__

                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "service": "saipenview",
                            "version": __version__,
                            "mode": "service",
                        },
                    )
                    return
                if path == "/api/events":
                    try:
                        service._check_auth(self._auth_from_query())
                    except _ServiceError as e:
                        self._send_error_json(e.status, str(e))
                        return
                    self._stream_events()
                    return
                self._serve_static(path)
                return

            # -- static UI (embedded iframe loads the same page via proxy) --

            _MIME = {
                ".html": "text/html",
                ".js": "application/javascript",
                ".css": "text/css",
                ".json": "application/json",
                ".png": "image/png",
                ".ico": "image/x-icon",
                ".svg": "image/svg+xml",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".map": "application/json",
            }

            def _serve_static(self, path: str) -> None:
                from pathlib import Path

                static_dir = Path(__file__).resolve().parent / "ui" / "static"
                # Serve index.html for the bare base path (SAIWORK iframe target).
                rel = "index.html" if path in ("/", "") else path.lstrip("/")
                candidate = (static_dir / rel).resolve()
                # Path-safety: never escape the static dir, never serve dotfiles.
                if not candidate.is_relative_to(
                    static_dir
                ) or candidate.name.startswith("."):
                    self._send_error_json(404, f"not found: {path}")
                    return
                if not candidate.is_file():
                    self._send_error_json(404, f"not found: {path}")
                    return
                mime = self._MIME.get(
                    candidate.suffix.lower(), "application/octet-stream"
                )
                body = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0]
                if path != "/api/rpc":
                    self._send_error_json(404, f"not found: {path}")
                    return
                try:
                    service._check_auth(self.headers.get("X-Saipenview-Token"))
                except _ServiceError as e:
                    self._send_error_json(e.status, str(e))
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    body = json.loads(raw)
                except (ValueError, json.JSONDecodeError) as e:
                    self._send_error_json(400, f"malformed JSON body: {e}")
                    return
                if not isinstance(body, dict) or not isinstance(
                    body.get("method"), str
                ):
                    self._send_error_json(400, "body must be {method, args}")
                    return
                args = body.get("args") or []
                if not isinstance(args, list):
                    self._send_error_json(400, "args must be an array")
                    return
                try:
                    result = service._dispatch(body["method"], args)
                except _ServiceError as e:
                    self._send_error_json(e.status, str(e))
                    return
                except TypeError as e:
                    self._send_error_json(400, f"bad arguments: {e}")
                    return
                except Exception as e:  # noqa: BLE001 - surface backend failure, keep service alive
                    print(
                        f"SAIPENVIEW service: RPC {body['method']} failed: {e}",
                        file=__import__("sys").stderr,
                    )
                    self._send_error_json(500, f"RPC {body['method']} failed")
                    return
                self._send_json(200, {"ok": True, "result": result})

            # -- SSE --

            def _stream_events(self) -> None:
                cond = threading.Condition()
                cond._sse_queue = []  # type: ignore[attr-defined]
                with service._subscriber_lock:
                    service._event_subscribers.add(cond)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    # Initial keep-alive comment so the client sees the stream open.
                    self.wfile.write(b": connected\n\n")
                    self.wfile.flush()
                    while not service._stopping.is_set():
                        with cond:
                            cond.wait(timeout=15)
                        queue = cond._sse_queue  # type: ignore[attr-defined]
                        while queue:
                            payload = queue.pop(0)
                            self.wfile.write(b"data: ")
                            self.wfile.write(payload.encode("utf-8"))
                            self.wfile.write(b"\n\n")
                            self.wfile.flush()
                        # Heartbeat every ~15s so a silent connection dies loudly.
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # client went away; subscriber removed below
                finally:
                    with service._subscriber_lock:
                        service._event_subscribers.discard(cond)

        return _Handler


def run_service(host: str, port: int, token: str | None) -> SaipenViewService:
    """Start the service and print the structured startup handshake."""
    service = SaipenViewService(host=host, port=port, token=token)
    service.start()
    # ONE structured line owns stdout. Everything else logs to stderr. The
    # explicit flush is load-bearing: when stdout is a redirected file
    # (SAIWORK captures the handshake), Python's default block buffering would
    # hold the line until buffer fill or process exit, making READY unusable.
    print(
        "SAIPENVIEW_SERVICE_READY "
        + json.dumps(
            {
                "port": service.bound_port,
                "token": service.token,
                "host": "127.0.0.1",
                "version": __import__(
                    "saipenview", fromlist=["__version__"]
                ).__version__,
            }
        ),
        flush=True,
    )
    return service
