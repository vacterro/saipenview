"""The guard must never silently refuse to start the app.

These cover the failure that actually shipped: the port was held by a socket
nobody was serving (a wedged accept loop with a full backlog, or a lingering
close from a killed process), so `bind` failed AND `connect` failed, and
`acquire()` returned False. `app.run()` reads that as "another instance has
it" and returns 0 -- no window, no error, exit code 0. Double-clicking the
launcher did nothing at all, with nothing anywhere to explain why.

The rule these lock in: False from acquire() means, and only means, that a
LIVE instance answered and was told to show itself.
"""

from __future__ import annotations

import socket
import threading

from saipenview.guard import SingleInstanceGuard

# Away from SINGLE_INSTANCE_PORT so a real running SAIPENVIEW cannot skew this.
_TEST_PORT = 47991


def test_dead_socket_holding_the_port_does_not_block_startup():
    """Bound but never listening: connect is refused, so nobody can answer."""
    squatter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    squatter.bind(("127.0.0.1", _TEST_PORT))
    # Deliberately no listen() -- this is the "held by a corpse" state.
    guard = SingleInstanceGuard(port=_TEST_PORT)
    try:
        assert guard.acquire() is True, (
            "a port held by a socket nobody serves must NOT be mistaken for a "
            "live instance -- that is the silent no-start bug"
        )
    finally:
        guard.stop()
        squatter.close()


def test_full_backlog_with_a_wedged_listener_does_not_block_startup():
    """Listening but never accepting -- the exact wedged-loop case observed.

    A listener whose accept loop is stuck stops draining the queue; once the
    backlog fills, the OS refuses new connections, so the handoff cannot
    succeed even though something IS bound and listening.
    """
    wedged = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    wedged.bind(("127.0.0.1", _TEST_PORT))
    wedged.listen(1)  # never accept()s
    fillers = []
    try:
        for _ in range(12):
            try:
                c = socket.create_connection(("127.0.0.1", _TEST_PORT), timeout=0.3)
                fillers.append(c)
            except OSError:
                break  # backlog refusing connections is the state we want

        guard = SingleInstanceGuard(port=_TEST_PORT)
        try:
            assert guard.acquire() is True, (
                "a wedged listener must not make the app unstartable"
            )
        finally:
            guard.stop()
    finally:
        for c in fillers:
            c.close()
        wedged.close()


def test_live_instance_is_still_woken_and_the_second_launch_exits():
    """The behaviour that must survive all of the above hardening."""
    owner = SingleInstanceGuard(port=_TEST_PORT)
    shown = threading.Event()
    assert owner.acquire(on_show_request=shown.set) is True
    try:
        second = SingleInstanceGuard(port=_TEST_PORT)
        assert second.acquire() is False, (
            "a healthy live instance must still absorb the second launch"
        )
        assert shown.wait(timeout=5.0), "the live instance was never asked to show"
    finally:
        owner.stop()


def test_a_slow_show_handler_cannot_wedge_the_accept_loop():
    """on_show_request runs off-thread, so a blocking handler is survivable."""
    owner = SingleInstanceGuard(port=_TEST_PORT)
    release = threading.Event()
    calls = []

    def blocking_show():
        calls.append(1)
        release.wait(timeout=10.0)  # stands in for a deadlocked evaluate_js

    assert owner.acquire(on_show_request=blocking_show) is True
    try:
        SingleInstanceGuard(port=_TEST_PORT).acquire()
        SingleInstanceGuard(port=_TEST_PORT).acquire()

        deadline = threading.Event()
        for _ in range(50):
            if len(calls) >= 2:
                break
            deadline.wait(0.1)
        assert len(calls) >= 2, (
            "the second SHOW never landed -- the first one wedged the loop"
        )
    finally:
        release.set()
        owner.stop()
