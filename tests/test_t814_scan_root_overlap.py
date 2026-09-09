"""T-814: overlapping configured scan roots walk the same subtree twice.

Config carries both ``v:\\`` and ``v:\\___vac\\__k\\__code``; the naive
one-worker-per-root submission walked the nested CODE subtree once per root --
measured 2.11s of every cycle for 7 projects the parent only missed because of
depth. The repair is an ownership plan, not a depth change: each configured
root stays an independent depth/provenance unit, and a parent walk PRUNES every
child directory owned by a more-specific configured root BEFORE entering it.

The oracles, each stated so it can fail against the pre-fix implementation:

* discovery completeness -- all projects remain discoverable, including one
  too deep for the parent's budget but visible from the nested root;
* traversal ownership -- instrumenting ``os.walk`` counts the nested subtree
  physically descended ONCE. Dedup at the end would hide this: duplicate
  traversal still produces deduplicated results while keeping the bug;
* a project located exactly at the nested root is discovered once (pruning
  removes the dirname; the owning worker, not the parent, finds it);
* three-level overlap: parent > child > grandchild, each pruned from every
  shallower ancestor;
* non-overlapping roots and alias spellings behave exactly as before;
* cancellation and timeout quarantine behaviour is untouched.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

import saipenview.scanner as scanner_mod
from saipenview.scanner import (
    build_overlap_plan,
    scan,
    _is_lexical_descendant,
    _lexical_norm,
)

STATE_MD = (
    "---\nphase: DONE\ntask: none\nnext_action: PHASE DONE\nblocker: none\n"
    "agent: a\nsaipen_version: 7\nmode: full\ntransition_from: SHIP\n"
    "updated: 2026-08-30T00:00:00Z\nlast_event: 1\n---\n"
)
BOARD_MD = "# Board\n\n## DOING\n## TODO\n## DONE\n## BLOCKED\n"
LOG_MD = "# Log\n- 30.08.26 00:00 [E-001] DEC: base\n"


def _project(root: Path) -> Path:
    (root / ".saipen").mkdir(parents=True, exist_ok=True)
    (root / ".saipen" / "STATE.md").write_text(STATE_MD, encoding="utf-8")
    (root / ".saipen" / "BOARD.md").write_text(BOARD_MD, encoding="utf-8")
    (root / ".saipen" / "LOG.md").write_text(LOG_MD, encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _no_fixture_garbage(monkeypatch):
    """Fixture paths contain 'tmp' (a garbage marker); the real scan path only
    guards projects reached from a real drive, so the overlap semantics under
    test must not be shadowed by the garbage filter here."""
    monkeypatch.setattr(scanner_mod, "_is_garbage_root", lambda p: False)


class _WalkCounter:
    """Honest traversal boundary: wraps os.walk and records every directory
    actually yielded, attributed to the walk root that visited it. The same
    directory visited under two DIFFERENT walk roots = duplicate traversal,
    regardless of any later dedup. (One root yielding nested dirs is one
    traversal by definition.)"""

    def __init__(self):
        self.visits: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._real = os.walk

    def install(self, monkeypatch):
        counter = self

        def counting(path, *args, **kwargs):
            walk_root = _lexical_norm(str(path))
            for item in counter._real(path, *args, **kwargs):
                with counter._lock:
                    counter.visits.append((walk_root, str(item[0])))
                yield item

        monkeypatch.setattr(scanner_mod.os, "walk", counting)
        return counter

    def walk_roots_under(self, subtree: Path) -> set[str]:
        """Distinct walk roots that descended into *subtree*. More than one
        means the subtree was physically traversed more than once."""
        prefix = _lexical_norm(str(subtree))
        with self._lock:
            return {
                wr
                for wr, d in self.visits
                if _lexical_norm(d) == prefix
                or _lexical_norm(d).startswith(prefix + os.sep)
            }

    def owner_walked_into(self, walk_root: Path, owned: Path) -> bool:
        """True when the *walk_root* worker visited any directory under
        *owned* -- i.e. an ancestor walk entered a subtree that belongs to a
        more-specific configured root (the T-814 defect)."""
        wr = _lexical_norm(str(walk_root))
        prefix = _lexical_norm(str(owned))
        with self._lock:
            return any(
                v == wr and (_lexical_norm(d) == prefix or _lexical_norm(d).startswith(prefix + os.sep))
                for v, d in self.visits
            )

    def any_directory_visited_by_two_roots(self) -> list[str]:
        """Directories that two DIFFERENT walk roots both visited."""
        seen: dict[str, set[str]] = {}
        with self._lock:
            for wr, d in self.visits:
                seen.setdefault(_lexical_norm(d), set()).add(wr)
        return [d for d, wrs in seen.items() if len(wrs) > 1]


# ── Lexical plan unit behaviour ──────────────────────────────────────────────


class TestOverlapPlan:
    def test_plan_prunes_nested_root_from_parent(self):
        plan = build_overlap_plan(["v:\\", "v:\\___vac\\__k\\__code"])
        assert plan[_lexical_norm("v:\\")] == [_lexical_norm("v:\\___vac\\__k\\__code")]
        assert _lexical_norm("v:\\___vac\\__k\\__code") not in plan

    def test_drive_root_and_bare_drive_letter_are_related(self):
        assert _is_lexical_descendant("v:\\", "v:\\x")
        assert _is_lexical_descendant("v:", "v:\\x")

    def test_case_and_trailing_separator_are_aliases(self):
        plan = build_overlap_plan(["V:\\", "v:\\"])
        assert plan == {}, "alias spellings of one root must not prune each other"
        plan = build_overlap_plan(
            ["V:\\___VAC\\__K\\__CODE\\", "v:\\___vac\\__k\\__code"]
        )
        assert plan == {}

    def test_cross_drive_roots_never_related(self):
        plan = build_overlap_plan(["c:\\", "v:\\tools"])
        assert plan == {}
        assert not _is_lexical_descendant("c:\\", "v:\\tools")

    def test_deepest_root_owns_overlapping_subtree(self):
        plan = build_overlap_plan(
            ["v:\\", "v:\\a", "v:\\a\\b"]
        )
        parent = _lexical_norm("v:\\")
        child = _lexical_norm("v:\\a")
        grandchild = _lexical_norm("v:\\a\\b")
        # The parent prunes both nested roots...
        assert sorted(plan[parent]) == sorted([child, grandchild])
        # ...but the middle root prunes ONLY the grandchild, never the
        # grandchild's own subtree twice.
        assert plan[child] == [grandchild]
        assert grandchild not in plan

    def test_no_plan_for_disjoint_roots(self):
        assert build_overlap_plan(["v:\\a", "v:\\b"]) == {}


# ── scan() end-to-end ownership ──────────────────────────────────────────────


class TestScanOverlapOwnership:
    def test_nested_subtree_traversed_exactly_once(self, tmp_path, monkeypatch):
        """The performance defect is duplicate traversal, not output dedup."""
        parent_root = tmp_path / "drive"
        nested = parent_root / "nested"
        _project(_project(nested / "deep"))
        _project(_project(parent_root / "shallow"))

        counter = _WalkCounter().install(monkeypatch)
        outcome = scan(
            [str(parent_root), str(nested)], max_depth=6, delay=0, cancel=None
        )

        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        assert os.path.normcase(str(_project(nested / "deep"))) in roots or (nested / "deep").is_dir()
        # The parent walk never entered the nested subtree...
        assert not counter.owner_walked_into(parent_root, nested), (
            "parent walk entered the nested-owned subtree"
        )
        # ...and no directory was physically traversed twice.
        assert counter.any_directory_visited_by_two_roots() == [], (
            "some directory was walked by two different workers"
        )

    def test_all_projects_discoverable_with_overlap(self, tmp_path):
        parent_root = tmp_path / "drive"
        nested = parent_root / "nested"
        expected = [
            _project(parent_root / "shallow"),
            _project(nested / "deep"),
            _project(nested / "deeper" / "still"),
        ]
        outcome = scan(
            [str(parent_root), str(nested)], max_depth=3, delay=0
        )
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        for p in expected:
            assert os.path.normcase(str(p)) in roots, f"{p} lost after overlap pruning"
        assert outcome.complete

    def test_deep_project_needs_nested_root_depth_budget(self, tmp_path):
        """A project beyond the parent's max_depth but visible from the nested
        root stays discoverable -- the reason the nested root exists."""
        parent_root = tmp_path / "drive"
        nested = parent_root / "l1" / "l2" / "l3"
        deep = _project(nested / "goal")
        outcome = scan(
            [str(parent_root), str(nested)], max_depth=2, delay=0
        )
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        assert os.path.normcase(str(deep)) in roots, (
            "overlap pruning dropped a project only the nested root could reach"
        )

    def test_project_at_nested_root_discovered_once(self, tmp_path):
        parent_root = tmp_path / "drive"
        nested = _project(parent_root / "nested")
        outcome = scan([str(parent_root), str(nested)], max_depth=4, delay=0)
        matches = [
            p for p in outcome.projects
            if os.path.normcase(str(p.root)) == os.path.normcase(str(nested))
        ]
        assert len(matches) == 1, (
            "project exactly at the nested root must be discovered once"
        )

    def test_three_level_overlap_no_double_walk(self, tmp_path, monkeypatch):
        root = tmp_path / "drive"
        child = root / "child"
        grandchild = child / "grand"
        _project(root / "p0")
        _project(child / "p1")
        _project(grandchild / "p2")

        counter = _WalkCounter().install(monkeypatch)
        outcome = scan(
            [str(root), str(child), str(grandchild)], max_depth=4, delay=0
        )
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        assert os.path.normcase(str(_project(grandchild / "p2"))) in roots
        assert os.path.normcase(str(_project(child / "p1"))) in roots
        assert os.path.normcase(str(_project(root / "p0"))) in roots
        # Ownership: the parent walk never entered child's subtree; the child
        # walk never entered grandchild's subtree. (The grandchild walk covers
        # its own subtree -- that is its configured job.)
        assert not counter.owner_walked_into(root, child), (
            "parent walk entered the child-owned subtree"
        )
        assert not counter.owner_walked_into(root, grandchild), (
            "parent walk entered the grandchild-owned subtree"
        )
        assert not counter.owner_walked_into(child, grandchild), (
            "child walk entered the grandchild-owned subtree"
        )
        # Globally: no directory was physically traversed twice.
        assert counter.any_directory_visited_by_two_roots() == [], (
            "some directory was walked by two different workers"
        )

    def test_non_overlapping_roots_behave_unchanged(self, tmp_path, monkeypatch):
        a = tmp_path / "a"
        b = tmp_path / "b"
        expected = [_project(a / "pa"), _project(b / "pb")]
        counter = _WalkCounter().install(monkeypatch)
        outcome = scan([str(a), str(b)], max_depth=4, delay=0)
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        for p in expected:
            assert os.path.normcase(str(p)) in roots
        # Both roots walked normally; no pruning side effects.
        assert counter.walk_roots_under(a) == {_lexical_norm(str(a))}
        assert counter.walk_roots_under(b) == {_lexical_norm(str(b))}
        assert outcome.complete

    def test_alias_spelled_roots_still_dedup_and_complete(self, tmp_path):
        root = tmp_path / "drive"
        expected = [_project(root / "one"), _project(root / "two")]
        upper = str(root).upper()
        lower = str(root).lower()
        outcome = scan([upper + os.sep, lower], max_depth=4, delay=0)
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        for p in expected:
            assert os.path.normcase(str(p)) in roots
        # One logical root => alias dedup leaves a single discovery per project.
        assert len(roots) == 2

    def test_junction_aliased_root_still_pruned(self, tmp_path, monkeypatch):
        """Audit RUN-1/IMP-003 (T-814 follow-up): a configured root that is a
        junction to a deeper directory under ANOTHER configured root has no
        lexical overlap -- the raw plan is empty -- yet both spellings walk the
        same physical subtree. The worker-side canonical-alias extension must
        prune it: the nested physical subtree is traversed exactly once.
        Requires symlink privilege; skipped when the OS refuses mklink /J."""
        import subprocess

        physical = tmp_path / "realroot"
        nested = physical / "deep" / "code"
        _project(nested / "p1")
        junc = tmp_path / "aliasroot"
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junc), str(nested)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            pytest.skip(f"junction creation refused: {r.stderr.strip()}")
        counter = _WalkCounter().install(monkeypatch)
        outcome = scan([str(physical), str(junc)], max_depth=6, delay=0)
        roots = {os.path.normcase(str(p.root)) for p in outcome.projects}
        assert os.path.normcase(str(nested / "p1")) in roots
        # The physical nested subtree must be traversed by exactly ONE walk root.
        walkers = counter.walk_roots_under(nested)
        assert len(walkers) == 1, (
            f"junction-aliased subtree walked by {len(walkers)} roots: {walkers}"
        )

    def test_cancellation_stops_scan(self, tmp_path):
        root = tmp_path / "drive"
        _project(root / "one")
        cancel = threading.Event()
        cancel.set()
        outcome = scan([str(root)], max_depth=2, delay=0, cancel=cancel)
        assert outcome.projects == []

    def test_provenance_preserved_on_overlap(self, tmp_path):
        parent_root = tmp_path / "drive"
        nested = parent_root / "nested"
        _project(_project(nested / "deep"))
        _project(_project(parent_root / "shallow"))
        outcome = scan([str(parent_root), str(nested)], max_depth=4, delay=0)
        assert outcome.complete
        assert len(outcome.completed_roots) == 2
        assert outcome.unresolved_roots == []

    def test_timeout_quarantine_intact(self, tmp_path, monkeypatch):
        """A hung root still quarantines its pool generation; overlap planning
        must not change PERF-001 semantics."""
        root = tmp_path / "drive"
        _project(root / "one")

        real_scan_one = scanner_mod._scan_one_root

        def hung(*args, **kwargs):
            event = kwargs.get("cancel")
            if args and _lexical_norm(str(args[0])).endswith("hung"):
                if event is not None:
                    event.wait(5)
                raise AssertionError("worker should have been abandoned")
            return real_scan_one(*args, **kwargs)

        monkeypatch.setattr(scanner_mod, "_scan_one_root", hung)
        monkeypatch.setattr(scanner_mod, "PER_ROOT_TIMEOUT_SECONDS", 0.05)
        outcome = scan(
            [str(root), str(tmp_path / "hung")], max_depth=2, delay=0
        )
        assert outcome.complete is False
        assert any("hung" in r for r in outcome.unresolved_roots)


def test_linked_worktrees_honor_overlap_plan(tmp_path, monkeypatch):
    """AUDIT cycle-2 IMP-002: find_linked_worktrees shares the T-814 ownership
    plan. Pre-fix it walked overlapping roots with a plain per-root os.walk and
    double-traversed nested subtrees (probe: 4 visits / 2 unique dirs under
    the nested root); the walker is live in production through
    Api._set_cache's fallback branch (api.py:1117)."""
    nested = tmp_path / "nested"
    proj = _project(nested / "proj1")
    # A linked worktree (git-as-FILE, no .saipen) ONLY under the nested root.
    wt = nested / "wt_one"
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    proj.mkdir(exist_ok=True)

    counter = _WalkCounter().install(monkeypatch)
    results = scanner_mod.find_linked_worktrees(
        [str(tmp_path), str(nested)], max_depth=6, delay=0
    )

    # Only the owning (nested) walk root may traverse the nested subtree.
    assert counter.walk_roots_under(nested) == {_lexical_norm(str(nested))}
    # The worktree is discovered exactly once.
    assert len(results) == 1 and results[0]["name"] == "wt_one"


def test_linked_worktrees_no_dup_discovery_overlapping_roots(tmp_path):
    """AUDIT cycle-2 IMP-002 discovery side: with overlapping roots, a worktree
    under the nested root appears exactly once in the results (pre-fix the
    same .git-as-FILE dir was appended by both walks)."""
    nested = tmp_path / "nested"
    nested.mkdir(parents=True)
    for name in ("wt_a", "wt_b"):
        d = nested / name
        d.mkdir()
        (d / ".git").write_text("gitdir: x\n", encoding="utf-8")
    results = scanner_mod.find_linked_worktrees(
        [str(tmp_path), str(nested)], max_depth=6, delay=0
    )
    assert sorted(r["name"] for r in results) == ["wt_a", "wt_b"]
    assert len({r["root"] for r in results}) == 2


def _junction_available(alias: Path, target: Path) -> bool:
    import subprocess

    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def test_linked_worktrees_junction_aliased_root_still_pruned(tmp_path, monkeypatch):
    """AUDIT cycle-4 IMP-001: the worktree walker must survive the same
    junction-alias case scan() survived in cycle-1 -- a configured root whose
    canonical resolution differs lexically from every raw spelling produces an
    EMPTY lexical plan, so only the worker-side canonical extension detects the
    overlap. Pre-fix the physical subtree was traversed by two distinct walk
    roots and the worktree appeared twice (both records resolving to the same
    physical directory)."""
    import subprocess

    real_root = tmp_path / "real"
    deep = real_root / "deep" / "code"
    deep.mkdir(parents=True)
    wt = deep / "wt_j"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    alias = tmp_path / "alias"
    if not _junction_available(alias, deep):
        pytest.skip("OS refused junction creation")

    visits = []
    real_walk = scanner_mod.os.walk

    def counting_walk(path, *args, **kwargs):
        wr = str(path)
        for item in real_walk(path, *args, **kwargs):
            visits.append((wr, str(Path(item[0]).resolve()).lower()))
            yield item

    monkeypatch.setattr(scanner_mod.os, "walk", counting_walk)
    results = scanner_mod.find_linked_worktrees(
        [str(real_root), str(alias)], max_depth=6, delay=0
    )

    deep_phys = str(deep.resolve()).lower()
    under = [d for _, d in visits if d == deep_phys or d.startswith(deep_phys + "\\")]
    # The physical subtree is traversed once (one walk root, no repeat dirs).
    assert len(under) == len(set(under))
    assert len({wr for wr, d in visits if d in set(under)}) == 1
    # The worktree is discovered exactly once.
    assert len(results) == 1 and results[0]["name"] == "wt_j"
    assert len({str(Path(r["root"]).resolve()) for r in results}) == 1


def test_alias_spelled_walk_root_still_owns_nested_sibling(tmp_path, monkeypatch):
    """AUDIT cycle-5 IMP-001: when the WALK ROOT ITSELF is an alias spelling
    (junction) and the other configured root sits physically inside its
    target, the alias walk must own that subtree -- pre-fix
    _worker_local_plan skipped lexically-nested siblings on the false
    assumption that the raw plan (keyed by raw spellings) already pruned
    them for this walk, and the walker's alias-spelled dirpaths matched no
    prune target: the sibling subtree was walked by two distinct walk roots
    and the worktree appeared twice."""
    import subprocess

    real_root = tmp_path / "real"
    deep = real_root / "deep" / "code"
    deep.mkdir(parents=True)
    wt = deep / "wt_x"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    alias = tmp_path / "alias"
    if not _junction_available(alias, deep):
        pytest.skip("OS refused junction creation")

    visits = []
    real_walk = scanner_mod.os.walk

    def counting_walk(path, *args, **kwargs):
        wr = str(path)
        for item in real_walk(path, *args, **kwargs):
            visits.append((wr, str(Path(item[0]).resolve()).lower()))
            yield item

    monkeypatch.setattr(scanner_mod.os, "walk", counting_walk)
    results = scanner_mod.find_linked_worktrees(
        [str(alias), str(wt)], max_depth=6, delay=0
    )

    wt_phys = str(wt.resolve()).lower()
    under = [(wr, d) for wr, d in visits if d == wt_phys or d.startswith(wt_phys + "\\")]
    # The wt subtree is traversed by exactly ONE walk root, once.
    assert len({wr for wr, _ in under}) == 1
    assert len(under) == len({d for _, d in under})
    # The worktree is discovered exactly once.
    assert len(results) == 1 and results[0]["name"] == "wt_x"
    assert len({str(Path(r["root"]).resolve()) for r in results}) == 1


def test_duplicate_canonical_root_spelling_walked_once(tmp_path, monkeypatch):
    """AUDIT cycle-6 IMP-001: two configured spellings of the SAME canonical
    root (junction alias + physical path) are ONE root -- scan() enforces that
    through its canonical in-flight reservation (second spelling -> skipped);
    the worktree walker must dedup the same way. Pre-fix os.walk was invoked
    twice over the same physical tree and the worktree record appeared twice."""
    import subprocess

    deep = tmp_path / "deep" / "code"
    deep.mkdir(parents=True)
    wt = deep / "wt_d"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    alias = tmp_path / "alias"
    if not _junction_available(alias, deep):
        pytest.skip("OS refused junction creation")

    invocations = []
    real_walk = scanner_mod.os.walk

    def counting(path, *args, **kwargs):
        invocations.append(str(Path(path).resolve()).lower())
        yield from real_walk(path, *args, **kwargs)

    monkeypatch.setattr(scanner_mod.os, "walk", counting)
    results = scanner_mod.find_linked_worktrees(
        [str(alias), str(deep)], max_depth=6, delay=0
    )

    assert len(invocations) == 1
    assert len(results) == 1 and results[0]["name"] == "wt_d"
    assert len({str(Path(r["root"]).resolve()) for r in results}) == 1
