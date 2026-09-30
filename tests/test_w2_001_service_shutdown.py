"""W2-001: shutdown request and completed teardown are different states."""

from __future__ import annotations

import argparse
import signal
import threading
import time

import pytest

from saipenview import __main__ as main_module
from saipenview import guard as guard_module
from saipenview import service as service_module
from saipenview.service import SaipenViewService


@pytest.fixture
def service(tmp_config_path):
    instance = SaipenViewService(
        host="127.0.0.1", port=0, token="w2-001-token", auto_scan=False
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()


def test_wait_and_concurrent_stop_wait_for_admitted_rpc(service, monkeypatch):
    api = service._api
    assert api is not None
    entered = threading.Event()
    release = threading.Event()
    rpc_errors: list[BaseException] = []
    api_stop_calls: list[str] = []

    def blocked_rpc(*_args):
        entered.set()
        release.wait()

    real_api_stop = api.stop

    def counted_api_stop():
        api_stop_calls.append("stop")
        real_api_stop()

    api.record_manual_work = blocked_rpc  # type: ignore[attr-defined]
    api.stop = counted_api_stop  # type: ignore[method-assign]

    server_thread = service._thread
    assert server_thread is not None
    server_join_timeouts = []
    real_server_join = server_thread.join

    def observe_server_join(timeout=None):
        server_join_timeouts.append(timeout)
        return real_server_join(timeout=timeout)

    monkeypatch.setattr(server_thread, "join", observe_server_join)
    # Exercise the join branch even if serve_forever exits just before the
    # state check after shutdown().
    monkeypatch.setattr(server_thread, "is_alive", lambda: True)

    drain_waiting = threading.Event()
    real_rpc_wait_for = service._rpc_cond.wait_for

    def observe_rpc_drain(predicate, timeout=None):
        # Shutdown has no deadline: hitting the former RPC timeout must not
        # publish a false completion while this worker still owns the Api.
        assert timeout is None
        drain_waiting.set()
        return real_rpc_wait_for(predicate, timeout=timeout)

    monkeypatch.setattr(service._rpc_cond, "wait_for", observe_rpc_drain)

    def call_rpc():
        try:
            service._dispatch("record_manual_work", ["blocked"])
        except BaseException as exc:  # keep worker failures visible to the test
            rpc_errors.append(exc)

    rpc_thread = threading.Thread(target=call_rpc)
    rpc_thread.start()
    assert entered.wait(timeout=5), "RPC never entered the backend"

    stop_done = threading.Event()
    waiter_done = threading.Event()
    second_stop_done = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (service.stop(), stop_done.set())
    )
    wait_thread = threading.Thread(target=lambda: (service.wait(), waiter_done.set()))
    second_stop_thread = threading.Thread(
        target=lambda: (service.stop(), second_stop_done.set())
    )
    try:
        stop_thread.start()
        assert drain_waiting.wait(timeout=5), "stop did not begin RPC drain"
        wait_thread.start()
        second_stop_thread.start()
        # Synchronize on the INVARIANT, not on how `wait()` blocks. The old
        # gate counted entries into `_stopped.wait()`, which pinned wait()'s
        # implementation and so forbade the bounded poll T-884 needs to stay
        # interruptible on Windows. What this test is actually about is that
        # neither waiter may RETURN while the RPC still owns the Api; give
        # both threads time to reach their blocking call, then assert exactly
        # that below.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not wait_thread.is_alive() or not second_stop_thread.is_alive():
                break
            if (
                waiter_done.is_set()
                or second_stop_done.is_set()
                or stop_done.is_set()
            ):
                break
            if (
                service._stop_owner is not None
                and service._state == "stopping"
                and service._rpc_active > 0
            ):
                break
            time.sleep(0.01)
        assert service._state == "stopping"
        assert service._stopping.is_set()
        assert not service._stopped.is_set()
        assert not stop_done.is_set()
        assert not waiter_done.is_set()
        assert not second_stop_done.is_set()
        assert api_stop_calls == []

        release.set()
        for thread in (rpc_thread, stop_thread, wait_thread, second_stop_thread):
            thread.join(timeout=10)
            assert not thread.is_alive(), f"{thread.name} did not finish after RPC drain"
        assert rpc_errors == []
        assert stop_done.is_set() and waiter_done.is_set() and second_stop_done.is_set()
        assert api_stop_calls == ["stop"]
        assert server_join_timeouts == [None]
        assert service._state == "stopped"
        assert service._stopped.is_set()
    finally:
        release.set()
        for thread in (rpc_thread, stop_thread, wait_thread, second_stop_thread):
            if thread.ident is not None:
                thread.join(timeout=10)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_run_service_holds_single_instance_guard_until_completion(
    monkeypatch, signum
):
    class FakeGuard:
        def __init__(self, *, port):
            self.port = port
            self.stopped = threading.Event()

        def acquire(self):
            return True

        def release_listener(self):
            pass

        def stop(self):
            self.stopped.set()

    class FakeService:
        def __init__(self):
            self.stop_requested = threading.Event()
            self.waiting = threading.Event()
            self.completed = threading.Event()

        def stop(self):
            self.stop_requested.set()

        def wait(self):
            self.waiting.set()
            self.completed.wait()

    fake_guard = FakeGuard(port=0)
    fake_service = FakeService()
    handlers = {}
    errors: list[BaseException] = []

    monkeypatch.setattr(guard_module, "SingleInstanceGuard", lambda **_kw: fake_guard)
    monkeypatch.setattr(
        service_module,
        "run_service",
        lambda **_kw: fake_service,
        raising=False,
    )
    monkeypatch.setattr(signal, "signal", lambda key, handler: handlers.__setitem__(key, handler))

    def send_shutdown():
        try:
            assert fake_service.waiting.wait(timeout=5), "service.wait was not entered"
            handlers[signum](signum, None)
            assert fake_service.stop_requested.is_set()
            assert not fake_guard.stopped.is_set(), "guard released on request, before completion"
            fake_service.completed.set()
        except BaseException as exc:  # propagate helper-thread assertion failures
            errors.append(exc)
            fake_service.completed.set()

    signal_thread = threading.Thread(target=send_shutdown)
    signal_thread.start()
    result = main_module._run_service(
        argparse.Namespace(host="127.0.0.1", port=0, token="test")
    )
    signal_thread.join(timeout=5)

    assert not signal_thread.is_alive()
    assert errors == []
    assert result == 0
    assert fake_guard.stopped.is_set()
