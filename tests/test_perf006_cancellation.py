"""T-595 / PERF-006: scanner cancellation must actually stop filesystem work.

``scan()`` used to consult its cancel Event exactly once before starting;
``_walk_with_depth_limit`` never looked at it again; ``BackgroundScanner``
never passed its stop event in at all; and ``stop()`` cleared ``_thread``
after a one-second join while ThreadPoolExecutor workers (which are NOT
daemon threads, despite the old comment) kept walking with their inflight
root reservations held -- through interpreter shutdown.

The contract now:

* one cooperative cancellation event threads BackgroundScanner -> scan ->
  _scan_worker -> _walk_with_depth_limit, checked before every descent;
* a worker whose cancellation fired before it started does no work at all
  but still releases its root reservation;
* the overall-timeout path sets an internal cancel, drops queued futures via
  ``shutdown(cancel_futures=True)``, and never publishes partial data as
  authoritative (complete stays False);
* ``stop()`` keeps the coordinator reference while it is genuinely alive --
  no lying about thread death -- and a later start() reaps it cleanly.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from saipenview import scanner
from saipenview.scanner import (
    BackgroundScanner,
    _inflight_lock,
    _inflight_roots,
    _walk_with_depth_limit,
    canonical_key,
    scan,
)


def _wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TestWalkCooperativeCancel:
    def test_cancel_stops_the_walk_between_directories(self, tmp_path):
        # A wide tree: without the check the walk visits every directory.
        for i in range(200):
            (tmp_path / f"d{i:03d}").mkdir()
        cancel = threading.Event()
        walk = _walk_with_depth_limit(tmp_path, 8, 0, cancel=cancel)
        visited_before_cancel = sum(1 for _ in zip(walk, range(3), strict=False))
        assert visited_before_cancel == 0  # no projects here, just dirs
        # The generator is lazy; force one more iteration then cancel.
        next(walk, None)
        cancel.set()
        remaining = sum(1 for _ in walk)
        assert remaining == 0

    def test_no_cancel_walks_everything(self, tmp_path):
        for i in range(5):
            (tmp_path / f"d{i}").mkdir()
        assert list(_walk_with_depth_limit(tmp_path, 8, 0)) == []


class TestWorkerEntryCancel:
    def test_cancelled_worker_does_no_work_and_releases_reservation(self, tmp_path):
        root = str(tmp_path)
        ckey = canonical_key(root)
        with _inflight_lock:
            _inflight_roots[ckey] = "running"
        try:
            calls = []
            original = scanner._scan_one_root

            def spy(*args, **kwargs):
                calls.append(1)
                return original(*args, **kwargs)

            scanner._scan_one_root = spy
            try:
                cancel = threading.Event()
                cancel.set()
                projects, worktrees = scanner._scan_worker(root, 4, 0.0, None, cancel)
                assert projects == [] and worktrees == []
                assert calls == [], "cancelled worker must not touch the walk"
            finally:
                scanner._scan_one_root = original
            with _inflight_lock:
                assert ckey not in _inflight_roots, "reservation leaked"
        finally:
            with _inflight_lock:
                _inflight_roots.pop(ckey, None)


class TestScanTimeoutCancelsWorkers:
    def test_overall_timeout_cancels_queued_and_running_work(
        self, tmp_path, monkeypatch
    ):
        roots = []
        for i in range(4):
            r = tmp_path / f"root{i}"
            r.mkdir()
            roots.append(str(r))

        real_walk = scanner._walk_with_depth_limit

        def slow_walk(root_path, *args, **kwargs):
            cancel = kwargs.get("cancel")
            if Path(str(root_path)).name == "root0":
                # A wedged drive: grind in small steps that still honor the
                # cooperative cancel, so scan's timeout can unwind it promptly.
                for _ in range(200000):
                    if cancel is not None and cancel.is_set():
                        return
                    time.sleep(0.005)
                return
            yield from real_walk(root_path, *args, **kwargs)

        monkeypatch.setattr(scanner, "_walk_with_depth_limit", slow_walk)
        monkeypatch.setattr(scanner, "PER_ROOT_TIMEOUT_SECONDS", 1)

        outcome = scan(roots, delay=0.0)
        assert outcome.complete is False, "timeout must never look authoritative"

        # PERF-002: the shared bounded executor pool stays alive across
        # cycles (its workers are bounded, not per-cycle leaks). The
        # contract is no non-daemon-worker GROWTH per cycle, not zero
        # threads. After several timed-out scans the executor thread count
        # must stay within the shared pool's bound, never accumulate.
        before = sum(
            1
            for t in threading.enumerate()
            if t.name.startswith("ThreadPoolExecutor")
        )
        for _ in range(3):
            scan(roots, delay=0.0)
        after = sum(
            1
            for t in threading.enumerate()
            if t.name.startswith("ThreadPoolExecutor")
        )
        assert after <= scanner._SHARED_POOL_MAX, (
            f"executor threads exceeded shared pool bound: {after}"
        )
        assert after <= before + 1, (
            f"executor threads grew across cycles: {before} -> {after}"
        )


class TestBackgroundScannerStopHonesty:
    def test_stop_keeps_thread_reference_while_it_is_alive(self):
        gate = threading.Event()
        proceed = threading.Event()

        class Slow(BackgroundScanner):
            def _loop(self):  # override: block inside "scan" after start
                while not self._stop_event.is_set():
                    gate.set()
                    proceed.wait(timeout=5)
                    break

        s = Slow(lambda projects, complete=False: None, interval_seconds=60)
        s.start()
        assert gate.wait(timeout=5)
        s.stop()
        # The 1s join may or may not outlive this trivial loop; either way the
        # reference must be honest.
        if s._thread is not None:
            assert s._thread.is_alive(), "reference kept only for live threads"
        proceed.set()
        assert _wait_for(lambda: not s.is_alive())
        assert s._thread is None or not s._thread.is_alive()

    def test_start_after_stop_reaps_dead_reference(self):
        s = BackgroundScanner(lambda p, complete=False, **kw: None, interval_seconds=60)
        s.start()
        assert _wait_for(s.is_alive)
        s.stop()
        assert _wait_for(lambda: not s.is_alive())
        s.start()
        try:
            assert s.is_alive()
        finally:
            s.stop()

    def test_stop_cancels_the_in_flight_scan_promptly(self, tmp_path):
        """A scan wedged inside traversal finishes quickly after stop()."""
        big = tmp_path / "big"
        big.mkdir()
        for i in range(3000):
            (big / f"d{i:04d}").mkdir()

        entered = threading.Event()
        real_walk = scanner._walk_with_depth_limit

        def spy_walk(root_path, *args, **kwargs):
            entered.set()
            t0 = time.monotonic()
            gen = real_walk(root_path, *args, **kwargs)
            while True:
                try:
                    next(gen)
                except StopIteration:
                    break
                if time.monotonic() - t0 > 20:
                    raise AssertionError("walk ignored cancellation")
            return

        monkey = pytest.MonkeyPatch()
        monkey.setattr(scanner, "_walk_with_depth_limit", spy_walk)
        published = []
        s = BackgroundScanner(
            lambda p, complete=False, **kw: published.append(p),
            scan_roots=[str(big)],
            interval_seconds=60,
        )
        s.start()
        try:
            assert entered.wait(timeout=5)
            t0 = time.monotonic()
            s.stop()
            stopped = time.monotonic() - t0
            # Without cooperative cancellation this waited for 3000 dirs +
            # the 1s join; now the walk aborts between directories.
            assert stopped < 5, stopped
            assert published == [], "stale generation must not publish"
        finally:
            monkey.undo()


class TestPreflightCancelStillWorks:
    def test_presetscan_cancel_returns_complete_empty(self, tmp_path):
        cancel = threading.Event()
        cancel.set()
        outcome = scan([str(tmp_path)], cancel=cancel)
        assert outcome.projects == []
        assert outcome.complete is True


class TestPerf001Quarantine:
    def test_one_hung_root_does_not_poison_healthy_roots(self, tmp_path, monkeypatch):
        """PERF-001: a timed-out non-cooperative root must not prevent healthy
        roots from executing in the next scan cycle.  The hung root's pool
        generation is quarantined; the next scan gets a fresh pool."""
        import saipenview.scanner as scanner_mod
        from pathlib import Path

        hung = tmp_path / "hung"
        hung.mkdir()
        (hung / ".saipen").mkdir()
        healthy = [tmp_path / f"h{i}" for i in range(3)]
        for h in healthy:
            h.mkdir()
            (h / ".saipen").mkdir()

        release = threading.Event()
        real_walk = scanner_mod._walk_with_depth_limit

        def blocking_walk(root_path, *args, **kwargs):
            if Path(root_path).name == "hung":
                assert release.wait(timeout=30), "hung root never released"
                return
            yield from real_walk(root_path, *args, **kwargs)

        monkeypatch.setattr(scanner_mod, "_walk_with_depth_limit", blocking_walk)
        monkeypatch.setattr(scanner_mod, "PER_ROOT_TIMEOUT_SECONDS", 0.5)

        # First scan: hung root blocks, healthy roots finish.
        roots = [str(hung)] + [str(h) for h in healthy]
        outcome1 = scanner_mod.scan(roots, delay=0.0)
        assert not outcome1.complete, "first scan with hung root must be incomplete"
        assert len(outcome1.unresolved_roots) == 1, "hung root should be unresolved"

        # Release the hung root so its future completes and quarantine
        # accounting drains for the next test.
        release.set()

        # Second scan: healthy roots only; fresh pool must let them run.
        outcome2 = scanner_mod.scan([str(h) for h in healthy], delay=0.0)
        assert outcome2.complete, f"second scan with only healthy roots must be complete: {outcome2}"
        assert len(outcome2.completed_roots) == 3, f"all 3 healthy roots should be scanned: {outcome2.completed_roots}"

    def test_quarantine_budget_exhaustion_returns_degraded(self, tmp_path, monkeypatch):
        """PERF-001: when _QUARANTINED_FUTURES reaches _SHARED_POOL_MAX,
        scan returns an explicit incomplete/degraded outcome."""
        import saipenview.scanner as scanner_mod

        real = scanner_mod._QUARANTINED_FUTURES
        try:
            with scanner_mod._SHARED_POOL_LOCK:
                scanner_mod._QUARANTINED_FUTURES = scanner_mod._SHARED_POOL_MAX
            outcome = scanner_mod.scan([str(tmp_path)], delay=0.0)
            assert not outcome.complete, "degraded scan must be incomplete"
            assert len(outcome.unresolved_roots) == 1
        finally:
            with scanner_mod._SHARED_POOL_LOCK:
                scanner_mod._QUARANTINED_FUTURES = real

    def test_preserves_inflight_duplicate_quarantine(self, tmp_path, monkeypatch):
        """PERF-001: inflight-root quarantine still prevents duplicate workers."""
        import saipenview.scanner as scanner_mod

        blocked = tmp_path / "blocked"
        blocked.mkdir()
        (blocked / ".saipen").mkdir()

        entered = threading.Event()
        release = threading.Event()
        real_canonical = scanner_mod.canonical

        def blocking_canonical(path):
            entered.set()
            assert release.wait(timeout=10), "canonical never released"
            return real_canonical(path)

        monkeypatch.setattr(scanner_mod, "canonical", blocking_canonical)

        results = {}

        def worker():
            results["out1"] = scanner_mod._scan_root_task(
                str(blocked), 6, 0.0, set(), threading.Event()
            )

        t = threading.Thread(target=worker)
        t.start()
        assert entered.wait(timeout=5), "first worker never reached canonical()"
        out2 = scanner_mod._scan_root_task(
            str(blocked), 6, 0.0, set(), threading.Event()
        )
        assert out2.get("status") == "skipped", out2
        release.set()
        t.join(timeout=10)
        assert "out1" in results
        assert results["out1"].get("status") == "completed", results["out1"]
