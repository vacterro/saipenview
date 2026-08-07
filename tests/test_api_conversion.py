"""Tests for api.py pure conversion functions — no Api/window dependency."""

from __future__ import annotations


class TestPhaseRank:
    """_phase_rank maps phase strings to sort-order integers."""

    def test_active_ranked_first(self):
        from saipenview.api import _phase_rank

        assert _phase_rank("ACTIVE") == 0

    def test_blocked_ranked_second(self):
        from saipenview.api import _phase_rank

        assert _phase_rank("BLOCKED") == 1

    def test_work_phases_ranked_middle(self):
        from saipenview.api import _phase_rank

        for phase in (
            "INIT",
            "HUNT",
            "BUILD",
            "REVIEW",
            "PLAN",
            "SCOUT",
            "ADD",
            "CLEAN",
            "TRANSLATE",
            "VALIDATE",
        ):
            assert _phase_rank(phase) == 2, f"{phase} should be rank 2"

    def test_verification_phases_ranked_third(self):
        from saipenview.api import _phase_rank

        assert _phase_rank("VERIFY") == 3
        assert _phase_rank("SHIP") == 3

    def test_done_ranked_last(self):
        from saipenview.api import _phase_rank

        assert _phase_rank("DONE") == 4

    def test_unknown_phase_ranked_lowest(self):
        from saipenview.api import _phase_rank

        assert _phase_rank("UNKNOWN") == 5
        assert _phase_rank("") == 5

    def test_case_sensitive(self):
        """_phase_rank is case-sensitive — lowercase gets fallback rank."""
        from saipenview.api import _phase_rank

        assert _phase_rank("done") == 5  # not 4
        assert _phase_rank("Done") == 5

    def test_rank_order_guarantees_smart_sort(self):
        """Verify the full rank ordering: ACTIVE < BLOCKED < WORK < VERIFY < DONE < UNKNOWN."""
        from saipenview.api import _phase_rank

        ranks = [
            ("ACTIVE", 0),
            ("BLOCKED", 1),
            ("INIT", 2),
            ("VERIFY", 3),
            ("SHIP", 3),
            ("DONE", 4),
            ("NOPE", 5),
        ]
        for phase, expected in ranks:
            assert _phase_rank(phase) == expected, (
                f"{phase}: expected {expected}, got {_phase_rank(phase)}"
            )


class TestReversed:
    """_Reversed wrapper enables descending sort inside ascending tuple key."""

    def test_reverses_comparison(self):
        from saipenview.api import _Reversed

        assert _Reversed("b") < _Reversed(
            "a"
        )  # b < a because Reversed swaps the comparison
        assert not (_Reversed("a") < _Reversed("b"))

    def test_reverses_numeric(self):
        from saipenview.api import _Reversed

        assert _Reversed(10) < _Reversed(5)
        assert not (_Reversed(3) < _Reversed(7))

    def test_eq_identity_not_defined(self):
        """__eq__ is not overridden — identity comparison only."""
        from saipenview.api import _Reversed

        a = _Reversed("x")
        b = _Reversed("x")
        assert a is a  # same object
        assert a is not b  # different objects

    def test_slots(self):
        """_Reversed uses __slots__ = ('obj',)."""
        from saipenview.api import _Reversed

        r = _Reversed(42)
        assert r.obj == 42
        assert not hasattr(r, "__dict__")  # __slots__ means no __dict__


class TestProjectSortKey:
    """_project_sort_key returns a tuple suitable for list.sort()."""

    def make_project(self, **overrides) -> dict:
        p = {
            "is_pinned": False,
            "name": "test",
            "phase": "DONE",
            "mtime": 1000,
            "git_dirty": False,
        }
        p.update(overrides)
        return p

    def test_smart_sort_orders_pinned_first(self):
        from saipenview.api import _project_sort_key

        pinned = self.make_project(is_pinned=True, name="z-pinned")
        unpinned = self.make_project(is_pinned=False, name="a-unpinned")
        # (not pinned=0) sorts before (not pinned=1) in tuple
        assert _project_sort_key(pinned) < _project_sort_key(unpinned)

    def test_smart_sort_phases_correctly(self):
        from saipenview.api import _project_sort_key

        active = self.make_project(phase="ACTIVE", mtime=500)
        done = self.make_project(phase="DONE", mtime=100)
        # ACTIVE (rank 0) should sort before DONE (rank 4)
        assert _project_sort_key(active) < _project_sort_key(done)

    def test_smart_sort_dirty_after_clean(self):
        from saipenview.api import _project_sort_key

        clean = self.make_project(phase="BUILD", git_dirty=False, mtime=100)
        dirty = self.make_project(phase="BUILD", git_dirty=True, mtime=200)
        # `not git_dirty` means dirty (0) sorts before clean (1) within the same phase rank.
        assert _project_sort_key(dirty) < _project_sort_key(clean)

    def test_smart_sort_recent_mtime_first(self):
        from saipenview.api import _project_sort_key

        recent = self.make_project(phase="BUILD", git_dirty=False, mtime=999)
        old = self.make_project(phase="BUILD", git_dirty=False, mtime=1)
        # -mtime: -999 < -1 → recent sorts before old
        assert _project_sort_key(recent) < _project_sort_key(old)

    def test_smart_sort_alphabetical_tiebreaker(self):
        from saipenview.api import _project_sort_key

        a_proj = self.make_project(
            phase="DONE", mtime=100, git_dirty=False, name="alpha"
        )
        b_proj = self.make_project(
            phase="DONE", mtime=100, git_dirty=False, name="beta"
        )
        assert _project_sort_key(a_proj) < _project_sort_key(b_proj)

    def test_name_asc_sort(self):
        from saipenview.api import _project_sort_key

        a = self.make_project(is_pinned=False, name="apple")
        b = self.make_project(is_pinned=False, name="banana")
        assert _project_sort_key(a, "name_asc") < _project_sort_key(b, "name_asc")

    def test_name_desc_sort(self):
        from saipenview.api import _project_sort_key

        a = self.make_project(is_pinned=False, name="apple")
        b = self.make_project(is_pinned=False, name="banana")
        # Reversed: "banana" < "apple" in reversed comparison
        assert _project_sort_key(b, "name_desc") < _project_sort_key(a, "name_desc")

    def test_recent_sort_uses_negated_mtime(self):
        from saipenview.api import _project_sort_key

        recent = self.make_project(mtime=200)
        old = self.make_project(mtime=100)
        assert _project_sort_key(recent, "recent") < _project_sort_key(old, "recent")

    def test_oldest_sort_uses_mtime(self):
        from saipenview.api import _project_sort_key

        recent = self.make_project(mtime=200)
        old = self.make_project(mtime=100)
        assert _project_sort_key(old, "oldest") < _project_sort_key(recent, "oldest")

    def test_pinned_overrides_every_order(self):
        from saipenview.api import _project_sort_key

        pinned = self.make_project(is_pinned=True, name="zzz")
        unpinned = self.make_project(is_pinned=False, name="aaa")
        for order in ("smart", "name_asc", "name_desc", "recent", "oldest"):
            assert _project_sort_key(pinned, order) < _project_sort_key(
                unpinned, order
            ), f"pinned should sort first in {order}"
