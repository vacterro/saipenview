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
        # A second service on the SAME port must bind cleanly — if the first
        # listener survived stop() this raises OSError: address in use.
        svc2 = SaipenViewService(port=port, token="t2", auto_scan=False)
        try:
            svc2.start()
            assert svc2.bound_port == port
        finally:
            svc2.stop()

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
