"""PERF-001 (SRC-018 R011): scanner shared-pool exception and lease safety.

The audited defects in scan():

  * the shared pool was acquired BEFORE the exception-safe cleanup, and
    ``_release_shared_pool()`` was called only on the normal return path --
    an exception between acquisition and return leaked a pool user;
  * roots were submitted through a comprehension, then tracked in a second
    pass, so a submit failure on the Nth root left the prior N-1 futures
    untracked;
  * only ``OSError``/``ValueError`` were caught per root, so an ordinary
    worker ``Exception`` escaped the background cycle and killed the loop.

These regressions pin the fixed contract deterministically (no sleeps for the
core assertions):

  * an unexpected error after acquisition still releases the pool exactly once;
  * a submit failure leaves no untracked work and reports every root;
  * one worker's ordinary Exception marks only that root unresolved, healthy
    peers still publish, and the background loop survives the cycle.
"""

from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path

import pytest

import saipenview.scanner as scanner_mod


@pytest.fixture
def pool_globals():
    with scanner_mod._SHARED_POOL_LOCK:
        saved = (
            scanner_mod._SHARED_POOL,
            scanner_mod._SHARED_POOL_USERS,
            scanner_mod._SHARED_POOL_FUTURES,
            scanner_mod._SHARED_POOL_STALE,
            scanner_mod._QUARANTINED_FUTURES,
        )
        scanner_mod._SHARED_POOL = None
        scanner_mod._SHARED_POOL_USERS = 0
        scanner_mod._SHARED_POOL_FUTURES = 0
        scanner_mod._SHARED_POOL_STALE = False
        scanner_mod._QUARANTINED_FUTURES = 0
    yield
    with scanner_mod._SHARED_POOL_LOCK:
        (
            scanner_mod._SHARED_POOL,
            scanner_mod._SHARED_POOL_USERS,
            scanner_mod._SHARED_POOL_FUTURES,
            scanner_mod._SHARED_POOL_STALE,
            scanner_mod._QUARANTINED_FUTURES,
        ) = saved


def _saipen_root(base: Path, name: str) -> Path:
    root = base / name
    (root / ".saipen").mkdir(parents=True)
    return root


def test_submit_runtimeerror_leaves_no_untracked_work_and_releases_pool(
    tmp_path, monkeypatch, pool_globals
):
    """A RuntimeError on the SECOND submit must: report the failing + remaining
    roots as unresolved, leave no untracked future, and release the pool user
    exactly once (users back to 0)."""
    roots = [str(_saipen_root(tmp_path, f"r{i}")) for i in range(4)]

    real_pool = scanner_mod._get_shared_pool
    submit_count = {"n": 0}

    class _FlakyPool:
        def __init__(self, inner):
            self._inner = inner

        def submit(self, *a, **kw):
            submit_count["n"] += 1
            if submit_count["n"] == 2:
                raise RuntimeError("cannot schedule new futures after shutdown")
            return self._inner.submit(*a, **kw)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    def flaky_get_shared_pool(n):
        inner = real_pool(n)
        if inner is None:
            return None
        return _FlakyPool(inner)

    monkeypatch.setattr(scanner_mod, "_get_shared_pool", flaky_get_shared_pool)

    outcome = scanner_mod.scan(roots, delay=0.0)

    # Every root is accounted (the one that got a future may complete, but the
    # failing submit and everything after it are unresolved).
    assert not outcome.complete
    all_reported = set(outcome.completed_roots) | set(outcome.unresolved_roots)
    assert len(all_reported) == len(roots), (
        f"a root went missing after submit failure: {all_reported}"
    )
    # Pool released exactly once: no leaked user.
    assert scanner_mod._SHARED_POOL_USERS == 0


def test_unexpected_error_after_acquisition_still_releases_pool(
    tmp_path, monkeypatch, pool_globals
):
    """An unexpected exception raised AFTER the pool is acquired must still
    release it (finally). The old code released only on the normal path."""
    roots = [str(_saipen_root(tmp_path, "r0"))]

    # Make as_completed explode with an unexpected error to simulate a failure
    # between acquisition and the normal return.
    def boom(*a, **kw):
        raise RuntimeError("unexpected internal failure")

    monkeypatch.setattr(concurrent.futures, "as_completed", boom)

    with pytest.raises(RuntimeError):
        scanner_mod.scan(roots, delay=0.0)

    # The pool user must have been released despite the exception.
    assert scanner_mod._SHARED_POOL_USERS == 0


def test_one_ordinary_worker_exception_isolated_healthy_publish(
    tmp_path, monkeypatch, pool_globals
):
    """A single root whose worker raises an ordinary (non-OSError) Exception is
    marked unresolved with a diagnostic; healthy peers still publish. The old
    per-root except only caught OSError/ValueError."""
    healthy = [_saipen_root(tmp_path, f"h{i}") for i in range(2)]
    bad = _saipen_root(tmp_path, "bad")

    real_task = scanner_mod._scan_root_task

    def flaky_task(raw_root, *a, **kw):
        if Path(raw_root).name == "bad":
            raise KeyError("ordinary non-OSError worker failure")
        return real_task(raw_root, *a, **kw)

    monkeypatch.setattr(scanner_mod, "_scan_root_task", flaky_task)

    outcome = scanner_mod.scan(
        [str(bad)] + [str(h) for h in healthy], delay=0.0
    )

    # The bad root is unresolved; the healthy roots completed.
    assert not outcome.complete
    assert len(outcome.completed_roots) == 2, (
        f"healthy roots did not publish: {outcome.completed_roots}"
    )
    assert len(outcome.unresolved_roots) == 1
    assert scanner_mod._SHARED_POOL_USERS == 0


def test_background_loop_survives_an_exceptional_cycle(
    tmp_path, monkeypatch, pool_globals
):
    """A cycle that raises an ordinary Exception must not kill the loop -- a
    later cycle still runs. BaseException is NOT swallowed."""
    root = _saipen_root(tmp_path, "r0")
    cycles: list[int] = []
    fail_first = {"done": False}

    def flaky_do_scan(self, event, generation):
        cycles.append(1)
        if not fail_first["done"]:
            fail_first["done"] = True
            raise RuntimeError("first cycle blows up")
        # second cycle: signal completion and stop the loop
        event.set()

    monkeypatch.setattr(
        scanner_mod.BackgroundScanner, "_do_scan", flaky_do_scan, raising=True
    )

    scanner = scanner_mod.BackgroundScanner(
        on_result=lambda *a, **k: None,
        scan_roots=[str(root)],
        interval_seconds=0.01,
        initial_delay=0.0,
    )
    event = threading.Event()
    gen = scanner._gen_counter.next()
    # Drive the loop directly on this thread with a bounded stop.
    scanner._scan_context = (event, gen)
    t = threading.Thread(target=scanner._loop, daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "loop thread hung"
    # The loop survived the first exceptional cycle and ran at least a second.
    assert len(cycles) >= 2, (
        f"loop died after the exceptional cycle: {len(cycles)} cycle(s)"
    )
