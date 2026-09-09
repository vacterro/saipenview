"""T-821: the normalized-snapshot cache must be keyed by the live router
table object, never by a reusable ``(id, len)`` coincidence.

CPython can hand a newly built dict the id of a freed one. The old
``(id(projects), len(projects))`` cache key then matched the *new* table
while still serving the *previous* table's snapshot, so ``_resolve_project``
attributed external ``.saipen`` events for newly synced projects to a dead
mapping. The regression reproduces the exact free/alloc cycle through the
real ``_RootRouterHandler`` and fails on the old key shape.
"""

from __future__ import annotations

import gc

import pytest

from saipenview.watcher import _RootRouterHandler

SCOPE = "v:/"
OLD_TABLE = {"v:/proj_a": "v:/proj_a", "v:/proj_b": "v:/proj_b"}


def test_id_reuse_serves_live_table_not_the_dead_one():
    """Red control on the pre-fix (id, len) key; green on the is-check.

    The cache pin is released explicitly so the old table can actually be
    freed and its id recycled -- the exact production shape after sync()
    rebinds the router table.
    """
    router = {SCOPE: dict(OLD_TABLE)}
    handler = _RootRouterHandler(SCOPE, router)
    old_table = router[SCOPE]
    # Warm the cache against the live table.
    handler._norm_snapshot(old_table)
    old_id = id(old_table)

    # Drop every reference: the production rebind + the fix's own pin.
    router[SCOPE] = {}
    del old_table
    handler._snapshot_cache = None
    gc.collect()

    replacement = None
    for _ in range(200_000):
        candidate = {
            "v:/proj_c": "v:/proj_c",
            "v:/proj_d": "v:/proj_d",
        }
        if id(candidate) == old_id:
            replacement = candidate
            break
        del candidate
    if replacement is None:
        pytest.skip("runtime refused to reuse the freed dict id")
    assert len(replacement) == 2

    router[SCOPE] = replacement  # the sync() refresh rebind, watcher.py:449
    snapshot = handler._norm_snapshot(replacement)
    assert set(snapshot) == {"v:/proj_c", "v:/proj_d"}, (
        "stale snapshot served for a reused-id table: "
        f"{sorted(snapshot)} -- the cache key aliased the dead object"
    )


def test_cache_holds_the_live_table_reference():
    """The fixed cache pins the table, so its id cannot be recycled while
    the handler lives (that pin IS the fix mechanism)."""
    router = {SCOPE: dict(OLD_TABLE)}
    handler = _RootRouterHandler(SCOPE, router)
    handler._norm_snapshot(router[SCOPE])
    router[SCOPE] = {"v:/proj_c": "v:/proj_c"}
    snapshot = handler._norm_snapshot(router[SCOPE])
    assert set(snapshot) == {"v:/proj_c"}
    assert handler._snapshot_cache[0] is router[SCOPE]


def test_in_place_pop_still_invalidates():
    """unwatch() mutates the table in place (.pop); len must invalidate."""
    router = {SCOPE: dict(OLD_TABLE)}
    handler = _RootRouterHandler(SCOPE, router)
    table = router[SCOPE]
    handler._norm_snapshot(table)
    table.pop("v:/proj_a")
    snapshot = handler._norm_snapshot(table)
    assert set(snapshot) == {"v:/proj_b"}


def test_rebuilt_table_different_length_serves_new_content():
    """sync() may rebuild with a different project count."""
    router = {SCOPE: dict(OLD_TABLE)}
    handler = _RootRouterHandler(SCOPE, router)
    handler._norm_snapshot(router[SCOPE])
    rebuilt = {"v:/proj_e": "v:/proj_e"}
    router[SCOPE] = rebuilt
    snapshot = handler._norm_snapshot(rebuilt)
    assert set(snapshot) == {"v:/proj_e"}


def test_resolve_project_uses_live_table_after_rebind():
    """End-to-end: _resolve_project resolves against the rebound table."""
    router = {SCOPE: dict(OLD_TABLE)}
    handler = _RootRouterHandler(SCOPE, router)
    handler._norm_snapshot(router[SCOPE])
    router[SCOPE] = {"v:/proj_c": "v:/proj_c"}
    assert handler._resolve_project("v:/proj_c/.saipen/STATE.md") == "v:/proj_c"
    assert handler._resolve_project("v:/proj_a/.saipen/STATE.md") is None
