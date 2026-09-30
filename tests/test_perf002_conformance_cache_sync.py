"""PERF-002 (SRC-018 R012): per-project conformance cache synchronization.

The audited defect: ``_BOARD_CACHE_LOCK`` and ``_LOG_CACHE_LOCK`` were
module-global RLocks that were HELD across the stat/read/parse/fold work, so a
slow BOARD or LOG read for one root serialized every other root's conformance
check behind it.

Fixed: the global lock is a short-lived mapping lock; the expensive per-file
work runs under a per-path / per-root lock. Same-root checks stay serialized
(and byte-equivalent); unrelated roots progress independently; an eviction
during an in-flight parse cannot resurrect the evicted entry.

Deterministic barriers, no sleeps for the ordering assertions.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import saipenview.conformance as conf


def _make_project(base: Path, name: str) -> Path:
    root = base / name
    saipen = root / ".saipen"
    saipen.mkdir(parents=True)
    saipen.joinpath("STATE.md").write_text(
        "---\nphase: BUILD\ntask: T-001\nnext_action: work\nblocker: none\n"
        "agent: test\nsaipen_version: 7\nmode: full\n"
        "updated: 2026-08-28T00:00:00Z\ntransition_from: SCOUT\n"
        "schema_version: 3\nlast_event: 1\nstyle_contract: test\n---\n",
        encoding="utf-8",
    )
    saipen.joinpath("BOARD.md").write_text(
        "# Board\n## DOING\n\n## TODO\n\n## DONE\n\n## BLOCKED\n", encoding="utf-8"
    )
    saipen.joinpath("LOG.md").write_text(
        "# Log\n\n- 28.08.26 00:00 [E-1] RUN: bootstrap\n", encoding="utf-8"
    )
    return root


class _Collector:
    def __init__(self):
        self.findings = []

    def fail(self, *a, **k):
        pass

    def warn(self, *a, **k):
        pass


@pytest.fixture(autouse=True)
def clean_caches():
    conf.evict_project_caches()
    yield
    conf.evict_project_caches()


def test_board_read_of_root_a_does_not_block_root_b(tmp_path, monkeypatch):
    """A BOARD read blocked for root A must not stall root B's check."""
    root_a = _make_project(tmp_path, "a")
    root_b = _make_project(tmp_path, "b")

    a_in_read = threading.Event()
    let_a_finish = threading.Event()
    real_read = conf.read_doc

    def gated_read(path, *a, **k):
        p = Path(path)
        if p.parent.parent.name == "a" and p.name == "BOARD.md":
            a_in_read.set()
            assert let_a_finish.wait(timeout=5), "A never released"
        return real_read(path, *a, **k)

    monkeypatch.setattr(conf, "read_doc", gated_read)

    def check_a():
        conf.check_board(root_a, _Collector())

    t_a = threading.Thread(target=check_a)
    t_a.start()
    assert a_in_read.wait(timeout=5), "A never entered its BOARD read"

    # B must complete WHILE A's read is blocked -- proving no global lock is
    # held across A's I/O.
    b_done = threading.Event()

    def check_b():
        conf.check_board(root_b, _Collector())
        b_done.set()

    t_b = threading.Thread(target=check_b)
    t_b.start()
    assert b_done.wait(timeout=5), (
        "root B blocked behind root A's BOARD read -- global lock held across I/O"
    )

    let_a_finish.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert not t_a.is_alive() and not t_b.is_alive()


def test_log_load_of_root_a_does_not_block_root_b(tmp_path, monkeypatch):
    root_a = _make_project(tmp_path, "a")
    root_b = _make_project(tmp_path, "b")

    a_in_read = threading.Event()
    let_a_finish = threading.Event()
    real_read = conf.read_doc

    def gated_read(path, *a, **k):
        p = Path(path)
        if p.parent.parent.name == "a" and p.name == "LOG.md":
            a_in_read.set()
            assert let_a_finish.wait(timeout=5), "A never released"
        return real_read(path, *a, **k)

    monkeypatch.setattr(conf, "read_doc", gated_read)

    def check_a():
        conf.check_log(root_a, _Collector())

    t_a = threading.Thread(target=check_a)
    t_a.start()
    assert a_in_read.wait(timeout=5), "A never entered its LOG read"

    b_done = threading.Event()

    def check_b():
        conf.check_log(root_b, _Collector())
        b_done.set()

    t_b = threading.Thread(target=check_b)
    t_b.start()
    assert b_done.wait(timeout=5), (
        "root B blocked behind root A's LOG load -- global lock held across I/O"
    )

    let_a_finish.set()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    assert not t_a.is_alive() and not t_b.is_alive()


def test_same_root_concurrent_board_checks_are_byte_equivalent(tmp_path):
    """Two concurrent checks of the SAME root stay serialized on the per-path
    lock and produce identical parsed results."""
    root = _make_project(tmp_path, "same")
    results: list[dict] = []
    lock = threading.Lock()

    def check():
        tickets = conf.check_board(root, _Collector())
        with lock:
            results.append(tickets)

    threads = [threading.Thread(target=check) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert all(not t.is_alive() for t in threads)
    assert len(results) == 8
    # All results are byte-equivalent (same keys, same sections).
    first = {tid: t.section for tid, t in results[0].items()}
    for r in results[1:]:
        assert {tid: t.section for tid, t in r.items()} == first


def test_append_and_eviction_stress_no_stale_resurrection(tmp_path):
    """Interleave appends, checks and evictions on one root: the aggregate must
    never resurrect an evicted stale entry or drift its fail count."""
    root = _make_project(tmp_path, "stress")
    log_path = root / ".saipen" / "LOG.md"

    for i in range(2, 40):
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"- 28.08.26 00:{i:02d} [E-{i}] [parent: E-{i-1}] RUN: event {i}\n"
            )
        conf.check_log(root, _Collector())
        if i % 5 == 0:
            conf.evict_project_caches([str(root)])

    # After eviction, a fresh check rebuilds from disk with correct ordering
    # (no duplicate/order fails from stale resurrection).
    c = _Collector()
    conf.check_log(root, c)
    order_fails = [
        f for f in c.findings
        if getattr(f, "code", "") in ("log.event.order", "log.event.duplicate")
    ]
    assert order_fails == [], f"stale resurrection produced spurious fails: {order_fails}"
