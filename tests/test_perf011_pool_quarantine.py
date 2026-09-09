"""T-800 / PERF-001: a timed-out non-cooperative scan root is quarantined.

The ticket's own `verify:` clause is a reproduction plus two resource claims,
and the coverage it shipped with could not fail: the existing quarantine tests
in `test_perf006_cancellation.py` either release the hung worker before
asserting anything (so nothing depends on the quarantine) or set
``_QUARANTINED_FUTURES`` by hand and assert the exhaustion branch the fix never
touched. Reverting the whole repair in place left them green -- a disarmed
control per `VERIFY-ORACLE-01`.

What the repair actually promises, in observable terms:

* a scan that times out on a still-running worker marks that POOL GENERATION
  stale, so the next scan runs on a DIFFERENT executor object instead of
  competing for the workers the hung root still owns;
* that running future occupies quarantined capacity for exactly as long as it
  runs -- counted when it is abandoned, released by its own done callback;
* capacity is global, so quarantine is subtracted from the pool bound rather
  than merely noted.

Each test here goes red when the quarantine is reverted in place
(`_SHARED_POOL_STALE` never set, `_QUARANTINED_FUTURES` never incremented) with
the tests, fixtures and command unchanged.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import saipenview.scanner as scanner_mod


@pytest.fixture
def pool_globals():
    """Snapshot and restore every shared-pool global.

    The pool is process-global by design, so a test that leaves a stale
    generation or a non-zero quarantine count changes the verdict of the next
    one. Restoring here keeps each case's red/green attributable to its own
    subject.
    """
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


def _hang_one_root(monkeypatch, hung_name: str, release: threading.Event):
    """Make the walk of `hung_name` block until `release` is set."""
    real_walk = scanner_mod._walk_with_depth_limit

    def blocking_walk(root_path, *args, **kwargs):
        if Path(root_path).name == hung_name:
            assert release.wait(timeout=30), "hung root never released"
            return
        yield from real_walk(root_path, *args, **kwargs)

    monkeypatch.setattr(scanner_mod, "_walk_with_depth_limit", blocking_walk)
    monkeypatch.setattr(scanner_mod, "PER_ROOT_TIMEOUT_SECONDS", 0.5)


def _wait_until(predicate, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class TestPoolGenerationIsQuarantined:
    def test_timeout_retires_the_pool_generation(self, tmp_path, monkeypatch, pool_globals):
        """The executor the hung worker occupies must not serve the next scan.

        This is the claim the ticket's reproduction was meant to prove, stated
        so it can fail: identity of the executor object across the two scans.
        Reusing it is exactly how one hung drive starves healthy roots -- the
        old generation's workers are still blocked inside it.
        """
        hung = _saipen_root(tmp_path, "hung")
        healthy = [_saipen_root(tmp_path, f"h{i}") for i in range(3)]
        release = threading.Event()
        _hang_one_root(monkeypatch, "hung", release)

        try:
            outcome1 = scanner_mod.scan(
                [str(hung)] + [str(h) for h in healthy], delay=0.0
            )
            assert not outcome1.complete
            first_pool = scanner_mod._SHARED_POOL
            assert first_pool is not None, "hung future must keep its pool alive"
            assert scanner_mod._SHARED_POOL_STALE is True, (
                "the generation holding a non-cooperative worker must be retired"
            )

            scanner_mod.scan([str(h) for h in healthy], delay=0.0)
            assert scanner_mod._SHARED_POOL is not first_pool, (
                "second scan reused the executor the hung worker still occupies"
            )
        finally:
            release.set()
            _wait_until(lambda: scanner_mod._QUARANTINED_FUTURES == 0)

    def test_abandoned_worker_holds_capacity_until_it_finishes(
        self, tmp_path, monkeypatch, pool_globals
    ):
        """Quarantine is accounting, not a label.

        A worker that ignored cancellation is still consuming a thread, so it
        has to be subtracted from the global bound while it runs and given back
        when it ends. Counted at abandonment and released by the future's own
        done callback -- never by the next scan assuming it drained.
        """
        hung = _saipen_root(tmp_path, "hung")
        release = threading.Event()
        _hang_one_root(monkeypatch, "hung", release)

        try:
            outcome = scanner_mod.scan([str(hung)], delay=0.0)
            assert not outcome.complete
            assert scanner_mod._QUARANTINED_FUTURES == 1, (
                "an abandoned running worker must occupy quarantined capacity"
            )
        finally:
            release.set()

        assert _wait_until(lambda: scanner_mod._QUARANTINED_FUTURES == 0), (
            "quarantined capacity must be returned when the worker finishes"
        )

    def test_quarantine_is_subtracted_from_the_global_bound(
        self, tmp_path, monkeypatch, pool_globals
    ):
        """Capacity is global: the next generation is sized by what is left.

        With the bound pinned to 2 and one worker quarantined, a fresh pool may
        open exactly one thread. A pool that ignores the quarantine would size
        itself against the full bound and oversubscribe the same hardware the
        timeout was evidence of.
        """
        hung = _saipen_root(tmp_path, "hung")
        healthy = [_saipen_root(tmp_path, f"h{i}") for i in range(2)]
        release = threading.Event()
        _hang_one_root(monkeypatch, "hung", release)
        monkeypatch.setattr(scanner_mod, "_SHARED_POOL_MAX", 2)

        try:
            scanner_mod.scan([str(hung)], delay=0.0)
            assert scanner_mod._QUARANTINED_FUTURES == 1

            scanner_mod.scan([str(h) for h in healthy], delay=0.0)
            pool = scanner_mod._SHARED_POOL
            assert pool is not None
            assert pool._max_workers == 1, (
                f"fresh pool ignored the quarantine: {pool._max_workers} workers "
                f"for a bound of 2 with 1 quarantined"
            )
        finally:
            release.set()
            _wait_until(lambda: scanner_mod._QUARANTINED_FUTURES == 0)


class TestExhaustionIsDegradedNotSilent:
    def test_no_capacity_returns_every_root_unresolved(self, tmp_path, pool_globals):
        """Saturation is reported, never silently skipped.

        `_get_shared_pool` returning None must produce an incomplete outcome
        naming every requested root as unresolved -- an empty COMPLETE result
        would let the cache replace live rows with nothing.
        """
        roots = [str(_saipen_root(tmp_path, f"r{i}")) for i in range(3)]
        with scanner_mod._SHARED_POOL_LOCK:
            scanner_mod._QUARANTINED_FUTURES = scanner_mod._SHARED_POOL_MAX

        outcome = scanner_mod.scan(roots, delay=0.0)
        assert not outcome.complete
        assert outcome.projects == []
        assert len(outcome.unresolved_roots) == 3
        assert outcome.completed_roots == []
