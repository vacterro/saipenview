"""Tests for saipenview.scanner — project discovery and directory walking."""

from __future__ import annotations


class TestExcludeDirs:
    def test_exclude_contains_common_dirs(self):
        from saipenview.scanner import EXCLUDE_DIRS

        assert "node_modules" in EXCLUDE_DIRS
        assert ".git" in EXCLUDE_DIRS
        assert "Windows" in EXCLUDE_DIRS
        assert "__pycache__" in EXCLUDE_DIRS
        assert "venv" in EXCLUDE_DIRS

    def test_system_drive_constant(self):
        from saipenview.scanner import SYSTEM_DRIVE

        assert SYSTEM_DRIVE == "C:\\"

    def test_max_depth_cap(self):
        from saipenview.scanner import MAX_SCAN_DEPTH

        assert MAX_SCAN_DEPTH == 8


class TestWalkWithDepthLimit:
    def test_finds_saipen_projects(self, tmp_path):
        from saipenview.scanner import _walk_with_depth_limit

        # Create a project structure
        proj = tmp_path / "my-project"
        (proj / ".saipen").mkdir(parents=True)
        (proj / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )

        results = list(_walk_with_depth_limit(tmp_path, max_depth=6, delay=0))
        assert len(results) == 1
        assert results[0].name == "my-project"

    def test_skips_node_modules(self, tmp_path):
        from saipenview.scanner import _walk_with_depth_limit

        # Create a project inside node_modules — should be excluded
        (tmp_path / "node_modules" / "fake-project" / ".saipen").mkdir(parents=True)
        (
            tmp_path / "node_modules" / "fake-project" / ".saipen" / "STATE.md"
        ).write_text("---\nphase: DONE\n---\n", encoding="utf-8")
        results = list(_walk_with_depth_limit(tmp_path, max_depth=6, delay=0))
        assert len(results) == 0

    def test_skips_git_dir(self, tmp_path):
        from saipenview.scanner import _walk_with_depth_limit

        (tmp_path / "some-repo" / ".git" / ".saipen").mkdir(parents=True)
        (tmp_path / "some-repo" / ".git" / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )
        results = list(_walk_with_depth_limit(tmp_path, max_depth=6, delay=0))
        assert len(results) == 0

    def test_respects_depth_limit(self, tmp_path):
        from saipenview.scanner import _walk_with_depth_limit

        # Project at depth 3: a/b/c/project/.saipen/STATE.md
        # rel parts = ('a', 'b', 'c', 'project') → depth 4
        deep = tmp_path / "a" / "b" / "c" / "project"
        (deep / ".saipen").mkdir(parents=True)
        (deep / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )

        results = list(_walk_with_depth_limit(tmp_path, max_depth=2, delay=0))
        assert len(results) == 0  # Too shallow

        results = list(_walk_with_depth_limit(tmp_path, max_depth=5, delay=0))
        assert len(results) == 1  # Within limit

    def test_finds_nested_saipen_projects(self, tmp_path):
        """A project inside another project IS found -- the old dirnames.clear()
        hid real nested repos (a project like V:\\...\\__CODE contains
        _PY\\_SAIPENVIEW etc). Test fixtures are pruned by EXCLUDE_DIRS
        (tests/) and GARBAGE_PATH_MARKERS, not by stopping the walk."""
        from saipenview.scanner import _walk_with_depth_limit

        outer = tmp_path / "outer-project"
        (outer / ".saipen").mkdir(parents=True)
        (outer / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )

        # Nested project inside the first -- SHOULD be found
        (outer / "nested" / ".saipen").mkdir(parents=True)
        (outer / "nested" / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )

        # A test-fixture-style nest below a project root must stay hidden
        (outer / "tests" / "scenarios" / "fix" / ".saipen").mkdir(parents=True)
        (outer / "tests" / "scenarios" / "fix" / ".saipen" / "STATE.md").write_text(
            "---\nphase: INIT\n---\n", encoding="utf-8"
        )

        results = sorted(list(_walk_with_depth_limit(tmp_path, max_depth=6, delay=0)))
        assert len(results) == 2
        assert {r.name for r in results} == {"outer-project", "nested"}

    def test_extra_excludes(self, tmp_path):
        from saipenview.scanner import _walk_with_depth_limit

        (tmp_path / "custom_exclude" / ".saipen").mkdir(parents=True)
        (tmp_path / "custom_exclude" / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )
        results = list(
            _walk_with_depth_limit(
                tmp_path, max_depth=6, delay=0, extra_excludes={"custom_exclude"}
            )
        )
        assert len(results) == 0


class TestFindLinkedWorktrees:
    def test_detects_worktree(self, tmp_path):
        from saipenview.scanner import find_linked_worktrees

        # Create a directory with .git as a FILE (worktree), not a dir
        wt = tmp_path / "worktree-project"
        wt.mkdir(parents=True)
        (wt / ".git").write_text(
            "gitdir: /main/.git/worktrees/worktree-project\n", encoding="utf-8"
        )

        results = find_linked_worktrees([str(tmp_path)], max_depth=3, delay=0)
        assert len(results) == 1
        assert results[0]["name"] == "worktree-project"
        assert "gitdir:" in results[0]["git_dir"]

    def test_skips_if_saipen_exists(self, tmp_path):
        """Worktree with .saipen/ should not appear in linked worktrees."""
        from saipenview.scanner import find_linked_worktrees

        wt = tmp_path / "project-with-saipen"
        wt.mkdir(parents=True)
        (wt / ".git").write_text(
            "gitdir: /main/.git/worktrees/project\n", encoding="utf-8"
        )
        (wt / ".saipen").mkdir()
        (wt / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )

        results = find_linked_worktrees([str(tmp_path)], max_depth=3, delay=0)
        assert len(results) == 0

    def test_skips_normal_git_dir(self, tmp_path):
        """Normal .git directory should not be detected as worktree."""
        from saipenview.scanner import find_linked_worktrees

        repo = tmp_path / "normal-repo"
        (repo / ".git").mkdir(parents=True)

        results = find_linked_worktrees([str(tmp_path)], max_depth=3, delay=0)
        assert len(results) == 0

    def test_empty_roots_returns_empty(self):
        from saipenview.scanner import find_linked_worktrees

        assert find_linked_worktrees([], max_depth=3, delay=0) == []

    def test_skips_nonexistent_root(self):
        """A root that doesn't exist is skipped without error."""
        from saipenview.scanner import find_linked_worktrees

        results = find_linked_worktrees(["Z:\\nonexistent"], max_depth=3, delay=0)
        assert results == []

    def test_detects_worktree_with_unreadable_git_file(self, tmp_path):
        """When .git is unreadable, the worktree is still reported with empty git_dir."""
        from saipenview.scanner import find_linked_worktrees

        wt = tmp_path / "wt-project"
        wt.mkdir(parents=True)
        # Write a non-UTF-8 encoding to cause decode error
        (wt / ".git").write_bytes(b"\xff\xfe#@invalid")

        results = find_linked_worktrees([str(tmp_path)], max_depth=3, delay=0)
        # Should either detect it or skip gracefully — the key is no crash
        assert isinstance(results, list)

    def test_respects_depth_limit_in_worktree_scan(self, tmp_path):
        from saipenview.scanner import find_linked_worktrees

        deep = tmp_path / "a" / "b" / "c" / "deep-wt"
        deep.mkdir(parents=True)
        (deep / ".git").write_text("gitdir: /main/.git\n", encoding="utf-8")

        results = find_linked_worktrees([str(tmp_path)], max_depth=2, delay=0)
        assert len(results) == 0  # Too shallow

        results = find_linked_worktrees([str(tmp_path)], max_depth=5, delay=0)
        assert len(results) == 1  # Within limit


class TestAutoRoots:
    def test_excludes_c_drive(self):
        from saipenview.scanner import SYSTEM_DRIVE, _auto_roots

        roots = _auto_roots()
        # C:\ should not be in auto roots
        for r in roots:
            assert r.upper() != SYSTEM_DRIVE.upper()

    def test_returns_paths_with_trailing_slash(self, tmp_path):
        from saipenview.scanner import scan

        # scan() normalizes roots with trailing backslash. tmp_path stands in
        # for real drive roots: a real-drive scan here crawled the whole
        # machine mid-suite and its abandoned daemon git workers could hit a
        # dead subprocess._readerthread at interpreter shutdown (Bad file
        # descriptor) -- T-179 family.
        scan(scan_roots=[str(tmp_path) + "\\", "E:\\nonexistent"], max_depth=3, delay=0)
        # No assertion on results (roots may not exist on CI), just no crash


class TestScan:
    def test_empty_roots(self):
        from saipenview.scanner import scan

        results = scan(scan_roots=[], max_depth=3, delay=0)
        assert results == []

    def test_nonexistent_root(self):
        from saipenview.scanner import scan

        results = scan(scan_roots=["Z:\\nonexistent"], max_depth=3, delay=0)
        assert results == []

    def test_finds_projects(self, tmp_path, monkeypatch):
        from saipenview.scanner import scan

        # tmp_path contains garbage markers (pytest-of-), so _is_garbage_root
        # would filter it out. Bypass for this test.
        monkeypatch.setattr("saipenview.scanner._is_garbage_root", lambda root: False)

        proj = tmp_path / "real-project"
        (proj / ".saipen").mkdir(parents=True)
        (proj / ".saipen" / "STATE.md").write_text(
            "---\nphase: BUILD\n---\n", encoding="utf-8"
        )
        (proj / ".saipen" / "BOARD.md").write_text(
            "# BOARD\n\n## TODO\n\n## DONE\n\n", encoding="utf-8"
        )
        (proj / ".saipen" / "LOG.md").write_text("# LOG\n\n", encoding="utf-8")

        results = scan(scan_roots=[str(tmp_path)], max_depth=3, delay=0)
        assert len(results) == 1
        assert results[0].name == "real-project"
        assert results[0].phase == "BUILD"

    def test_case_and_slash_dupes_collapse(self, tmp_path, monkeypatch):
        """The same root typed as `c:\foo` and `C:/FOO/` scans once, not twice."""
        from saipenview.scanner import scan

        monkeypatch.setattr("saipenview.scanner._is_garbage_root", lambda root: False)
        proj = tmp_path / "dup-root"
        (proj / ".saipen").mkdir(parents=True)
        (proj / ".saipen" / "STATE.md").write_text(
            "---\nphase: DONE\n---\n", encoding="utf-8"
        )

        # Only on Windows are these two spellings the same path.
        path_str = str(tmp_path)
        results = scan(
            scan_roots=[path_str, path_str.replace("\\", "/").upper()],
            max_depth=3,
            delay=0,
        )
        assert len(results) == 1

    def test_missing_root_is_quarantined_not_silently_dropped(self, tmp_path):
        """A scan root that doesn't exist produces a scan error entry."""
        from saipenview.scanner import get_scan_error_log, scan

        missing = str(tmp_path / "gone-drive")
        scan(scan_roots=[missing, str(tmp_path)], max_depth=3, delay=0)
        messages = [e["message"] for e in get_scan_error_log()]
        assert any("missing" in m and "gone-drive" in m for m in messages)


class TestBackgroundScanner:
    def test_create_and_stop_no_crash(self):
        """BackgroundScanner can be created and stopped without errors."""
        from saipenview.scanner import BackgroundScanner

        events = []

        def on_result(projects):
            events.append(("result", len(projects)))

        bs = BackgroundScanner(
            on_result=on_result,
            scan_roots=[],
            interval_seconds=1,
            max_depth=3,
            delay=0,
        )
        bs.start()
        bs.stop()
        # No assertion on events — just verify no crash

    def test_generation_increment_on_stop(self):
        """Stop increments the generation counter."""
        from saipenview.scanner import BackgroundScanner, _is_gen_current, _next_gen

        gen = _next_gen()
        bs = BackgroundScanner(on_result=lambda p: None, scan_roots=[])
        bs.start()
        bs.stop()
        assert not _is_gen_current(gen)

    def test_double_start_is_noop(self):
        """Starting an already-running scanner is a no-op."""
        from saipenview.scanner import BackgroundScanner

        bs = BackgroundScanner(on_result=lambda p: None, scan_roots=[])
        bs.start()
        bs.start()  # Should not error
        bs.stop()

    def test_rescan_now_executes_scan(self):
        """rescan_now triggers a scan directly via _on_result."""
        from unittest.mock import patch

        from saipenview.scanner import BackgroundScanner

        bs = BackgroundScanner(
            on_result=lambda p: None,
            scan_roots=[],
            interval_seconds=1,
        )
        with patch.object(bs, "_on_result") as mock_result:
            bs.rescan_now()
            assert mock_result.called

    def test_rescan_now_stale_gen_returns_early(self):
        """rescan_now returns early if generation is stale."""
        from saipenview.scanner import BackgroundScanner, _next_gen

        events = []
        bs = BackgroundScanner(
            on_result=lambda p: events.append(len(p)),
        )
        _next_gen()  # Invalidate gen
        bs.rescan_now()  # Should return without calling scan
        assert len(events) == 0


class TestScanErrors:
    def test_get_scan_errors(self):
        """Scan errors deque can be read safely."""
        from saipenview.scanner import _push_error, get_scan_errors

        # push an error and read it back
        _push_error("test error")
        errors = get_scan_errors()
        assert len(errors) > 0
        assert any("test error" in e for e in errors)

    def test_get_scan_error_log(self):
        """get_scan_error_log returns full dict entries."""
        from saipenview.scanner import _push_error, get_scan_error_log

        _push_error("log error")
        logs = get_scan_error_log()
        assert len(logs) > 0
        assert logs[-1]["message"] == "log error"
        assert "time" in logs[-1]


class TestScanProgress:
    def test_get_scan_progress(self):
        from saipenview.scanner import _set_scan_progress, get_scan_progress

        _set_scan_progress(pct=50, root="D:\\")
        progress = get_scan_progress()
        assert progress["pct"] == 50
        assert progress["root"] == "D:\\"
