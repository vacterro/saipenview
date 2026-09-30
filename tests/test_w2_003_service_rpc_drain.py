"""W2-003: service shutdown is a quiescence boundary for RPC work.

Before the fix, `_dispatch` applied lifecycle admission only to `launch_agent`.
Every other allowlisted RPC (write_file_text, ticket mutation, commit/revert,
stop_agent, ...) proceeded as long as `_api` was non-None, and once a request
thread captured a bound `_api` method, clearing `_api` could not revoke it.
`stop()` could therefore publish `state=stopped` and tear down Api-owned
scanners/watchers/processes while an admitted mutable RPC still held a callable
into that Api, executing mutation after shutdown.

The fix adds one service-wide RPC admission/drain boundary: `_dispatch`
registers each RPC as an active worker before dereferencing `_api` and
unregisters in `finally`; `stop()` closes admission first, then waits for the
admitted workers to drain before touching Api.
"""

from __future__ import annotations

import threading

import pytest

from saipenview.service import SaipenViewService


@pytest.fixture()
def service(tmp_config_path):
    svc = SaipenViewService(
        host="127.0.0.1", port=0, token="w2-003-token", auto_scan=False
    )
    svc.start()
    yield svc
    svc.stop()


def test_stop_waits_for_admitted_rpc_before_api_teardown(service):
    """An ordinary mutable RPC blocked mid-execution must keep stop() from
    reaching the Api teardown until the worker is released and drained.
    """
    api = service._api
    assert api is not None

    entered = threading.Event()
    release = threading.Event()
    order: list[str] = []

    real_stop = api.stop

    def recording_stop():
        order.append("api.stop")
        return real_stop()

    def blocking_mutation(*args, **kwargs):
        entered.set()
        release.wait(timeout=10)
        order.append("mutation_done")

    # Inject an allowlisted, blocking backend method on the live Api.
    api.record_manual_work = blocking_mutation  # type: ignore[attr-defined]
    api.stop = recording_stop  # type: ignore[method-assign]

    err: list = []

    def call_rpc():
        try:
            service._dispatch("record_manual_work", ["while stopping"])
        except Exception as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=call_rpc)
    t.start()
    assert entered.wait(timeout=5), "RPC never entered the backend"

    stop_done = threading.Event()

    def do_stop():
        service.stop()
        stop_done.set()

    s = threading.Thread(target=do_stop)
    s.start()

    # The worker is still blocked: stop() must NOT have reached api.stop yet.
    assert not stop_done.wait(timeout=0.8), (
        "stop() completed while a mutable RPC was still executing"
    )
    assert "api.stop" not in order, "api.stop ran before the worker drained"
    assert service._state != "stopped"

    # Release the worker; stop() may now proceed.
    release.set()
    t.join(timeout=10)
    assert stop_done.wait(timeout=10), "stop() never completed after drain"
    s.join(timeout=10)
    assert "mutation_done" in order
    assert order.index("mutation_done") < order.index("api.stop"), order
    assert service._state == "stopped"
    assert service._api is None


def test_admission_closed_during_stopping_refuses_new_rpc(service):
    """While the service is stopping, a newly arriving non-launch RPC must be
    refused with a controlled 503 and must not enter Api.
    """
    api = service._api
    assert api is not None

    calls = {"n": 0}

    def counting_mutation(*args, **kwargs):
        calls["n"] += 1
        return {"ok": True}

    api.record_manual_work = counting_mutation  # type: ignore[attr-defined]

    # Force the stopping window: close admission without completing teardown.
    with service._rpc_cond:
        service._rpc_admission_open = False
    try:
        from saipenview.service import _ServiceError

        with pytest.raises(_ServiceError) as ei:
            service._dispatch("record_manual_work", ["x"])
        assert ei.value.status == 503
        assert calls["n"] == 0, "RPC entered Api while admission was closed"
    finally:
        with service._rpc_cond:
            service._rpc_admission_open = True


def test_restart_new_generation_isolation(service):
    """After stop()+start(), a fresh lifecycle runs with reopened admission."""
    service.stop()
    service.start()
    try:
        with service._rpc_cond:
            assert service._rpc_admission_open is True
            assert service._rpc_active == 0
        # A normal allowlisted read works on the new generation.
        res = service._dispatch("running_agent_count", [])
        assert isinstance(res, int)
    finally:
        service.stop()
