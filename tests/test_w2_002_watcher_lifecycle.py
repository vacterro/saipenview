"""W2-002: watcher topology must be lifecycle-aware on EVERY path.

`_watch_scan_root`'s "already scheduled" fast path used to refresh the router
and mapping WITHOUT taking `_lock` and WITHOUT checking `_stopped`/`_life_gen`.
A sync that captured an old generation could reach that branch after
stop()+revive() cleared the maps, republish durable topology with NO live
Observer watch, and then make every subsequent sync take the same fast path --
so the watcher permanently missed filesystem events for that scope.

Reproduction is deterministic: capture the generation, run stop()+revive(),
then invoke `_watch_scan_root` with the STALE generation (exactly what the old
sync would do when it resumes after the barrier).
"""

from __future__ import annotations

import threading
from pathlib import Path

from saipenview.watcher import SaipenWatcher


class _BarrierDict(dict):
    """A dict whose membership test parks the caller once.

    The pre-fix fast path evaluates ``scope in self._root_router`` and then
    UNCONDITIONALLY writes the router. The race window is between that check
    and that write, so the barrier captures the membership result and then
    blocks -- the exact point a real sync sits in when stop()+revive() runs.
    """

    def __init__(self, initial, entered, release):
        super().__init__(initial)
        self._entered = entered
        self._release = release
        self._fired = False

    def __contains__(self, key):
        result = super().__contains__(key)
        if not self._fired:
            self._fired = True
            self._entered.set()
            self._release.wait(timeout=5)
        return result


def _make_scan_tree(tmp_path: Path) -> tuple[Path, Path]:
    scan_root = tmp_path / "scan"
    proj = scan_root / "proj"
    (proj / ".saipen").mkdir(parents=True)
    (proj / ".saipen" / "STATE.md").write_text("---\nphase: DONE\n---\n", encoding="utf-8")
    return scan_root, proj


def test_stale_sync_after_stop_revive_does_not_republish_topology(tmp_path):
    scan_root, proj = _make_scan_tree(tmp_path)
    w = SaipenWatcher(debounce_delay=0.05)
    try:
        # 1. A sync captures the current generation and publishes the scope.
        w.sync([str(proj)], scan_roots=[str(scan_root)])
        scope = str(scan_root)
        assert scope in w._root_router
        assert scope in w._watches
        with w._lock:
            old_gen = w._life_gen

        # 2. Suspend the in-flight sync inside the fast path, between its
        #    membership check and its router write.
        entered = threading.Event()
        release = threading.Event()
        w._root_router = _BarrierDict(w._root_router, entered, release)

        result: dict = {}

        def stale_sync():
            w._watch_scan_root(scope, [str(proj)], old_gen)
            result["done"] = True

        t = threading.Thread(target=stale_sync)
        t.start()

        # If the fast path was entered (pre-fix), stop()+revive() lands in the
        # window and the resumed sync must not republish. If the fix returned
        # before the branch (gen check), the thread simply finishes.
        entered.wait(timeout=2)
        w.stop()
        w.revive()
        release.set()
        t.join(timeout=5)
        assert not t.is_alive()
        assert result.get("done"), "stale sync did not complete"

        # The core invariant: no durable topology survived the stale sync.
        assert scope not in w._root_router, "stale sync republished the router"
        assert scope not in w._watches, "stale sync republished a watch entry"

        # A fresh sync must actually schedule one real watch for the scope.
        w.sync([str(proj)], scan_roots=[str(scan_root)])
        assert scope in w._watches, "fresh sync failed to schedule a real watch"
        assert scope in w._root_router
        assert w._project_to_scope.get(str(proj)) == scope
        assert len(w._watches) == 1
    finally:
        w.stop()


def test_consistent_fast_path_refreshes_without_duplicate_watch(tmp_path):
    scan_root, proj = _make_scan_tree(tmp_path)
    w = SaipenWatcher(debounce_delay=0.05)
    try:
        w.sync([str(proj)], scan_roots=[str(scan_root)])
        scope = str(scan_root)
        with w._lock:
            gen = w._life_gen
            first_watch = w._watches.get(scope)
        # A second sync at the SAME generation refreshes the router in place;
        # it must not create a second watch.
        w.sync([str(proj)], scan_roots=[str(scan_root)])
        with w._lock:
            assert w._watches.get(scope) is first_watch
            assert len(w._watches) == 1
        assert w._life_gen == gen
    finally:
        w.stop()


def test_public_watch_racing_stop_revive_is_generation_guarded(tmp_path):
    scan_root, proj = _make_scan_tree(tmp_path)
    w = SaipenWatcher(debounce_delay=0.05)
    try:
        # Capture the generation, then stop+revive before the public watch()
        # would commit, and drive the fallback with the stale generation.
        with w._lock:
            stale_gen = w._life_gen
        w.stop()
        w.revive()
        w._watch_project_fallback(str(proj), stale_gen)
        assert str(proj) not in w._fallback_projects, (
            "stale public watch republished fallback topology"
        )
        # A fresh watch() schedules a real fallback.
        w.watch(str(proj))
        assert str(proj) in w._fallback_projects
    finally:
        w.stop()
