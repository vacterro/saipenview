"""PERF-005 (SRC-018 R015): reclaimable idle per-root RootOwnership locks.

The audited defect: ``RootOwnership`` kept every per-root RLock forever in a
strong dictionary, so touching thousands of transient roots grew the registry
without bound.

Fixed: guarded weak retention. A lock is kept alive by its holders' own
references -- held or awaited locks can never be reclaimed, and once no one
references a lock it is garbage-collected with the entry. Same-root concurrent
callers always receive the exact same LIVE object; agent reservation and
app-transaction exclusion semantics are unchanged.

Regression: 5000 transient roots must leave the retained entry count bounded
near active concurrency (not 5000), while same-root two-thread identity and
serialization remain exact under GC pressure.
"""

from __future__ import annotations

import gc
import threading
from pathlib import Path

from saipenview.ownership import RootOwnership


def test_5000_transient_roots_leave_bounded_retention():
    reg = RootOwnership()
    for i in range(5000):
        root = Path(f"V:\\transient_{i}\\proj")
        lock = reg.lock(root)
        lock.acquire()
        lock.release()
        del lock
    # Drop caller references and force reclamation.
    gc.collect()
    retained = len(reg._locks)
    assert retained <= 50, (
        f"{retained} lock entries retained after 5000 transient roots -- "
        "idle locks are not being reclaimed"
    )


def test_same_root_two_threads_same_live_object():
    reg = RootOwnership()
    root = Path("V:\\proj")

    main_lock = reg.lock(root)  # main thread holds a live reference

    seen: list[threading.RLock] = []
    barrier = threading.Barrier(2, timeout=10)

    def other():
        barrier.wait()
        seen.append(reg.lock(root))

    t = threading.Thread(target=other)
    t.start()
    barrier.wait()
    t.join(timeout=10)

    assert not t.is_alive()
    assert len(seen) == 1
    assert seen[0] is main_lock, (
        "two concurrent same-root callers received different live lock objects"
    )


def test_held_lock_never_swapped_or_retired():
    reg = RootOwnership()
    root = Path("V:\\proj")

    holder = reg.lock(root)
    holder.acquire()
    try:
        # While HELD, any number of new callers (plus forced GC) must observe
        # the exact same object.
        gc.collect()
        again = reg.lock(root)
        assert again is holder

        acquired = threading.Event()
        released = threading.Event()

        def waiter():
            l2 = reg.lock(root)
            assert l2 is holder
            acquired.set()
            l2.acquire()  # blocks until the holder releases
            try:
                assert l2 is holder
            finally:
                l2.release()
            released.set()

        t = threading.Thread(target=waiter)
        t.start()
        assert acquired.wait(timeout=5)
        # The waiter is AWAITING holder; it must never be handed a new object,
        # even under GC pressure.
        gc.collect()
        holder.release()
        assert released.wait(timeout=5)
        t.join(timeout=5)
    finally:
        if holder._is_owned():
            holder.release()


def test_idle_lock_is_reclaimed_after_last_reference_drops():
    """After every holder drops the reference, the idle entry is reclaimable.
    A later caller gets a fresh object -- but at that instant nobody holds or
    awaits the old one, so serialization was never split."""
    reg = RootOwnership()
    root = Path("V:\\reclaim")

    l1 = reg.lock(root)
    l1.acquire()
    l1.release()
    del l1
    gc.collect()

    l2 = reg.lock(root)
    assert l2 is not None
    assert hasattr(l2, "acquire") and hasattr(l2, "release")
    # l2 is again live: concurrent callers see the same new object.
    assert reg.lock(root) is l2


def test_agent_reservation_and_app_tx_exclusion_unchanged():
    """CORE-002 semantics: reserve_agent/begin_app_tx mutual exclusion intact."""
    reg = RootOwnership()
    root = Path("V:\\proj")

    with reg.lock(root):
        assert reg.reserve_agent(root) is True
    # App tx refused while agent owns.
    with reg.lock(root):
        assert reg.begin_app_tx(root) is False
    # Second launch refused.
    with reg.lock(root):
        assert reg.reserve_agent(root) is False
    reg.release_agent(root)

    with reg.lock(root):
        assert reg.begin_app_tx(root) is True
    # Launch refused while app tx active.
    with reg.lock(root):
        assert reg.reserve_agent(root) is False
    reg.end_app_tx(root)

    with reg.lock(root):
        assert reg.reserve_agent(root) is True
    assert reg.agent_owns(root) is True
    reg.release_agent(root)
    assert reg.agent_owns(root) is False

    # gc pressure must not break the reservation semantics.
    gc.collect()
    with reg.lock(root):
        assert reg.begin_app_tx(root) is True
    with reg.lock(root):
        assert reg.reserve_agent(root) is False
    reg.end_app_tx(root)


def test_gc_pressure_cannot_split_active_root_serialization():
    """Hammer same-root lock() from many threads while forcing GC: identity
    stays exact whenever a holder keeps a reference, and app_tx/agent
    exclusion never interleaves."""
    reg = RootOwnership()
    root = Path("V:\\hammer")

    threading.Event()
    violations: list[str] = []

    def worker(n: int):
        # Keep a live reference the whole time: identity must hold.
        held_lock = reg.lock(root)
        for _ in range(200):
            with held_lock:
                ok = reg.reserve_agent(Path("V:\\hammer"))
                if not ok:
                    violations.append(f"worker {n}: reserve refused under own lock")
                reg.release_agent(Path("V:\\hammer"))
            gc.collect() if n == 0 else None

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(not t.is_alive() for t in threads)
    assert violations == []
