"""Headless service mode: lifecycle, RPC dispatch, auth, allowlist, SSE.

The service runs the REAL `Api` backend on an ephemeral loopback port, so these
tests double as transport-parity evidence for the read-only surface: an RPC
over HTTP must return the same payload shape the pywebview bridge would marshal
for the same backend state.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from saipenview.service import ALLOWED_RPC_METHODS, SaipenViewService


@pytest.fixture()
def service(tmp_config_path):
    svc = SaipenViewService(
        host="127.0.0.1", port=0, token="test-token-123", auto_scan=False
    )
    svc.start()
    yield svc
    svc.stop()


def _rpc(svc, method, args=None, token="test-token-123", raw=False):
    """POST /api/rpc; returns parsed JSON. `raw=True` returns (status, body).

    Windows loopback under full-suite load occasionally aborts the keep-alive
    connection mid-handshake (ConnectionAbortedError, WinError 10053) -- the
    request never reached the server. The probes here are idempotent reads
    (auth checks, status), so exactly one abort-retry of the CONNECTION is
    safe and keeps the suite deterministic; the retry is on the transport,
    never on a side-effecting RPC.
    """
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Saipenview-Token"] = token
    req = urllib.request.Request(
        f"http://127.0.0.1:{svc.bound_port}/api/rpc",
        data=json.dumps({"method": method, "args": args or []}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return (resp.status, body) if raw else body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            return (e.code, body) if raw else body
        except (ConnectionAbortedError, ConnectionResetError) as e:
            if attempt == 0:
                time.sleep(0.2)
                continue
            raise e


def _health(svc, raw=False):
    for attempt in range(2):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{svc.bound_port}/health", timeout=10
            ) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return (resp.status, body) if raw else body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            return (e.code, body) if raw else body
        except (ConnectionAbortedError, ConnectionResetError) as e:
            if attempt == 0:
                time.sleep(0.2)
                continue
            raise e


# ── lifecycle / handshake ──────────────────────────────────────────────────


class TestLifecycle:
    def test_binds_loopback_only(self):
        with pytest.raises(ValueError, match="loopback"):
            SaipenViewService(host="0.0.0.0", port=0)
        with pytest.raises(ValueError, match="loopback"):
            SaipenViewService(host="192.168.1.1", port=0)

    def test_health_is_deterministic_and_unauthenticated(self, service):
        status, body = _health(service, raw=True)
        assert status == 200
        assert body["ok"] is True
        assert body["service"] == "saipenview"
        assert body["mode"] == "service"
        assert isinstance(body["version"], str)

    def test_ephemeral_port_allocated(self, service):
        assert service.bound_port > 0

    def test_stop_releases_the_port(self, tmp_config_path):
        svc = SaipenViewService(port=0, token="t", auto_scan=False)
        svc.start()
        port = svc.bound_port
        svc.stop()
        svc2 = SaipenViewService(port=port, token="t2", auto_scan=False)
        try:
            svc2.start()
            assert svc2.bound_port == port
        finally:
            svc2.stop()

    def test_start_thread_failure_releases_port_and_preserves_exception(
        self, tmp_config_path, monkeypatch
    ):
        svc = SaipenViewService(port=0, token="t", auto_scan=False)
        original_start = threading.Thread.start
        failure = RuntimeError("ORIGINAL_START_FAILURE")

        def fail_start(thread):
            if thread.name == "saipenview-service":
                raise failure
            original_start(thread)

        monkeypatch.setattr(threading.Thread, "start", fail_start)
        with pytest.raises(RuntimeError, match="ORIGINAL_START_FAILURE"):
            svc.start()

        assert svc._state == "stopped"
        assert svc._server is None
        assert svc._thread is None
        assert svc._api is None

        monkeypatch.setattr(threading.Thread, "start", original_start)
        svc.start()
        try:
            assert svc.bound_port > 0
        finally:
            svc.stop()

    def test_start_cleanup_failure_preserves_startup_exception(
        self, tmp_config_path, monkeypatch
    ):
        import saipenview.service as service_module

        class FakeApi:
            def __init__(self):
                self._auto_scan = True
                self._config = {}

            def start(self):
                pass

            def stop(self):
                raise ValueError("CLEANUP_FAILURE")

        svc = SaipenViewService(port=0, token="t", auto_scan=False)
        original_start = threading.Thread.start

        def fail_start(thread):
            if thread.name == "saipenview-service":
                raise RuntimeError("ORIGINAL_START_FAILURE")
            original_start(thread)

        monkeypatch.setattr(service_module, "Api", FakeApi)
        monkeypatch.setattr(threading.Thread, "start", fail_start)
        with pytest.raises(RuntimeError, match="ORIGINAL_START_FAILURE"):
            svc.start()
        assert svc._state == "stopped"
        assert svc._server is None
        assert svc._thread is None
        assert svc._api is None

    def test_rpc_rejected_when_stopped(self, tmp_config_path):
        svc = SaipenViewService(port=0, token="t", auto_scan=False)
        svc.start()
        port = svc.bound_port
        svc.stop()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/rpc",
            data=json.dumps({"method": "get_status", "args": []}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Saipenview-Token": "t"},
            method="POST",
        )
        # The listener is gone, so the request cannot be served: the port is
        # released (see test_stop_releases_the_port) — connection refused.
        with pytest.raises((urllib.error.HTTPError, OSError)):
            urllib.request.urlopen(req, timeout=10)


# ── auth ───────────────────────────────────────────────────────────────────


class TestAuth:
    def test_missing_token_rejected(self, service):
        status, body = _rpc(service, "get_status", token=None, raw=True)
        assert status == 401
        assert body["ok"] is False

    def test_bad_token_rejected(self, service):
        status, body = _rpc(service, "get_status", token="wrong", raw=True)
        assert status == 401
        assert body["ok"] is False

    def test_events_require_token(self, service):
        req = urllib.request.Request(
            f"http://127.0.0.1:{service.bound_port}/api/events", method="GET"
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 401


# ── allowlist ──────────────────────────────────────────────────────────────


class TestAllowlist:
    def test_unknown_method_rejected(self, service):
        status, body = _rpc(service, "no_such_method", raw=True)
        assert status == 404
        assert body["ok"] is False

    def test_private_method_never_dispatchable(self, service):
        for name in ("_write_cache", "_set_cache", "__init__", "getattr"):
            status, body = _rpc(service, name, raw=True)
            assert status in (403, 404), f"{name} slipped through the allowlist"
            assert body["ok"] is False

    def test_desktop_shell_ops_rejected(self, service):
        for name in (
            "quit",
            "minimize_window",
            "maximize_window",
            "move_by",
            "set_hotkeys",
            "set_autostart_enabled",
            "browse_folder",
            "open_editor",
            "clipboard_copy",
        ):
            status, body = _rpc(service, name, raw=True)
            assert status == 403, f"{name} must be desktop-only"
            assert "desktop-shell" in body["error"]

    def test_every_allowlisted_method_has_no_prefix_and_is_dispatchable_shape(self):
        # Allowlist hygiene: no private names, no shell-only names that would
        # have been rejected anyway.
        for name in ALLOWED_RPC_METHODS:
            assert not name.startswith("_")
            assert name not in {
                "quit",
                "minimize_window",
                "maximize_window",
                "browse_folder",
            }

    def test_every_sai_api_method_is_either_service_allowlisted_or_desktop_only(self):
        import re

        from saipenview.service import _DESKTOP_ONLY_METHODS

        sai_api_path = (
            Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "sai-api.js"
        )
        text = sai_api_path.read_text(encoding="utf-8")
        start = text.index("var SAI_API_METHODS =")
        decl = text[start : text.index("];", start) + 2]
        names = re.findall(r'"([A-Za-z_]+)"', decl)
        assert names, "SAI_API_METHODS not parsed from sai-api.js"
        assert len(set(names)) == len(names), f"SAI_API_METHODS has duplicates: {names}"
        assert not ALLOWED_RPC_METHODS & _DESKTOP_ONLY_METHODS, (
            "allowlisted and desktop-only classifications overlap: "
            f"{ALLOWED_RPC_METHODS & _DESKTOP_ONLY_METHODS}"
        )
        missing = [
            n for n in names if n not in ALLOWED_RPC_METHODS and n not in _DESKTOP_ONLY_METHODS
        ]
        assert not missing, (
            "shared frontend methods with no service classification (neither "
            f"ALLOWED_RPC_METHODS nor _DESKTOP_ONLY_METHODS): {missing}"
        )
        assert "running_agent_count" in ALLOWED_RPC_METHODS

    def test_running_agent_count_authenticated_dispatch_and_nonzero_boundary(self, service):
        original = service._api._process_manager.count_running
        service._api._process_manager.count_running = lambda: 3  # type: ignore[assignment]
        try:
            body = _rpc(service, "running_agent_count")
            assert body["ok"] is True
            assert body["result"] == 3
        finally:
            service._api._process_manager.count_running = original
        body = _rpc(service, "running_agent_count")
        assert body["ok"] is True
        assert isinstance(body["result"], int)


# ── happy path RPC (transport parity surface) ──────────────────────────────


class TestRpc:
    def test_get_status_returns_backend_dict(self, service):
        body = _rpc(service, "get_status")
        assert body["ok"] is True
        result = body["result"]
        assert "scanned" in result
        assert "scanning" in result

    def test_get_projects_returns_list(self, service):
        body = _rpc(service, "get_projects")
        assert body["ok"] is True
        assert isinstance(body["result"], list)

    def test_get_config_returns_dict(self, service):
        body = _rpc(service, "get_config")
        assert body["ok"] is True
        assert isinstance(body["result"], dict)
        assert "scan_roots" in body["result"]

    def test_registry_status_and_recovery_are_authenticated_rpc(self, service, tmp_path):
        from saipenview.external_changes import get_registry

        registry = get_registry()
        persist = Path(tmp_path) / "ec.json"
        persist.write_text("{ corrupt", encoding="utf-8")
        registry._set_persist_path(persist)

        status = _rpc(service, "get_external_change_registry_status")
        assert status["ok"] is True
        assert status["result"]["state"] == "corrupt"

        recovery = _rpc(service, "recover_external_change_registry")
        assert recovery["ok"] is True
        assert recovery["result"]["ok"] is True
        assert recovery["result"]["status"]["state"] == "healthy"
        assert "archived" not in recovery["result"]

        for method in (
            "get_external_change_registry_status",
            "recover_external_change_registry",
        ):
            code, body = _rpc(service, method, token=None, raw=True)
            assert code == 401
            assert body["ok"] is False

    def test_malformed_body_rejected(self, service):
        req = urllib.request.Request(
            f"http://127.0.0.1:{service.bound_port}/api/rpc",
            data=b"{not json",
            headers={
                "Content-Type": "application/json",
                "X-Saipenview-Token": "test-token-123",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 400

    def test_args_must_be_array(self, service):
        req = urllib.request.Request(
            f"http://127.0.0.1:{service.bound_port}/api/rpc",
            data=json.dumps({"method": "get_projects", "args": "nope"}).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Saipenview-Token": "test-token-123",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 400

    @pytest.mark.parametrize(
        "bad_args",
        [{}, "", 0, False],
    )
    def test_args_silent_reinterpretation_rejected(self, service, bad_args):
        """T-41/W2-031: non-list non-null args must be rejected, not coerced
        to []. body.get('args') or [] silently reinterprets {}, '', 0 and
        false as empty list -- all of these are invalid and must return 400."""
        req = urllib.request.Request(
            f"http://127.0.0.1:{service.bound_port}/api/rpc",
            data=json.dumps({"method": "get_projects", "args": bad_args}).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Saipenview-Token": "test-token-123",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 400


# ── protocol mutation safety (via real backend) ────────────────────────────


class TestProtocolSafety:
    def test_unsafe_file_path_rejected(self, service, tmp_path):
        # A path far outside any scan root must be rejected by the existing
        # path validation, not by the transport.
        victim = tmp_path / "secret.txt"
        victim.write_text("nope", encoding="utf-8")
        body = _rpc(
            service,
            "read_file_text",
            [str(victim)],
        )
        # The backend keeps its own validation: either a clean error result or
        # a safe None — never the file contents.
        assert body["ok"] is True
        assert body["result"] in (None, "")

    def test_coordinator_rpc_mutation_surfaces(self, service):
        # update_project_state on a non-project path must not throw into a 500;
        # the backend's path guard returns a structured result.
        body = _rpc(
            service,
            "update_project_state",
            ["Z:\\no\\such\\project", {"phase": "DONE"}],
        )
        assert body["ok"] is True  # backend answers cleanly
        assert body["result"] is None or "error" in body["result"]


# ── SSE ────────────────────────────────────────────────────────────────────


class TestSse:
    def test_event_stream_delivers_file_changed(self, service, tmp_path):
        received = []
        done = threading.Event()

        def _reader():
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{service.bound_port}/api/events?token=test-token-123",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    # Read first frames until the file.changed event arrives.
                    while not done.is_set():
                        line = resp.readline().decode("utf-8", "replace")
                        if line.startswith("data: "):
                            received.append(line[6:].strip())
                            if '"file.changed"' in line:
                                return
            except Exception as e:  # noqa: BLE001 - reader must not hang the test
                received.append(f"ERR:{e}")

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        time.sleep(0.3)

        # Emit through the same bus the watcher uses.
        from saipenview.events import event_bus

        event_bus.publish(
            "saipen.file_changed",
            {"root": "C:\\proj", "file": "STATE.md", "origin": "external"},
        )
        t.join(timeout=10)
        done.set()
        joined = "\n".join(received)
        assert '"file.changed"' in joined, f"event never arrived: {joined!r}"
        assert (
            '"C:\\\\proj"' in joined or "C:\\\\proj" in joined or "C:\\proj" in joined
        )
