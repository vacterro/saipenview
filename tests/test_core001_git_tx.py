"""CORE-001: git mutations hold the per-root ownership lock atomically.

Before the fix, commit_agent_work / revert_agent_work / delete_untracked_files
called _guard_live_agent (a non-locking liveness check) and then released
that check before entering git_diff, leaving a window where a live agent
could slip in and clobber the tree. The repair wraps the entire
fingerprint-verify + git-mutation under begin_app_tx / end_app_tx so the
per-root RLock is held for the full transaction.

These tests verify the lock-holding behavior directly via the git_diff
functions plus the ownership layer, bypassing the Api root-resolution path.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview.git_diff import (
    commit_agent_work,
    delete_untracked_files,
    get_working_diff,
    revert_agent_work,
)
from saipenview.paths import canonical
from saipenview.protocol_write import get_coordinator


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "commit.gpgsign", "false"], check=True
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "core.autocrlf", "false"], check=True
    )


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _init_repo(root)
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "initial"], check=True
    )
    return root


def _stage_change(repo: Path) -> str:
    """Modify tracked.txt, stage it with real git, return fingerprint."""
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    diff = get_working_diff(str(canonical(repo)))
    assert diff["ok"], diff
    return diff["fingerprint"]


def _smart_mock(repo: Path, sleep_sec: float = 0.3):
    """Return a mock for _run_git that:
    - For status/diff/rev-parse calls: runs the real git command immediately.
    - For mutation calls (commit/reset/clean): signals entry, sleeps, then runs real git.
    """
    entered = threading.Event()
    real_git = subprocess.run

    def mock_run(root: str, args: list[str]):
        entered.set()
        if args[0] in ("status", "diff", "rev-parse"):
            return real_git(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        time.sleep(sleep_sec)
        return real_git(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    return mock_run, entered


class TestGitMutationOwnershipTx:
    """CORE-001: reserve_agent blocks while a git mutation holds the tx lock."""

    def test_commit_hold_lock_allows_reserve_after(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        root = canonical(repo)
        coord = get_coordinator()
        fp = _stage_change(repo)

        reserve_ok: list[bool] = []

        def try_reserve():
            mock_run, entered = _smart_mock(repo)
            with patch("saipenview.git_diff._run_git", side_effect=mock_run):
                entered.wait(timeout=2)
                reserve_ok.append(coord.ownership.reserve_agent(Path(root)))

        t = threading.Thread(target=try_reserve)
        t.start()
        time.sleep(0.05)

        mock_run, entered = _smart_mock(repo)
        with patch("saipenview.git_diff._run_git", side_effect=mock_run):
            result = commit_agent_work(root, "test msg", fp)

        assert result["ok"] is True, result
        t.join(timeout=5)
        assert not t.is_alive(), "reserve_agent did not return"
        assert reserve_ok == [True], f"got {reserve_ok}"

    def test_revert_hold_lock_allows_reserve_after(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        root = canonical(repo)
        coord = get_coordinator()

        # First commit a change.
        fp1 = _stage_change(repo)
        mock_run1, _ = _smart_mock(repo, sleep_sec=0.01)
        with patch("saipenview.git_diff._run_git", side_effect=mock_run1):
            r = commit_agent_work(root, "ch1", fp1)
        assert r["ok"] is True

        # Reset to base, then make another change for revert.
        subprocess.run(
            ["git", "-C", str(repo), "reset", "--hard", "HEAD~1"], check=True
        )
        (repo / "tracked.txt").write_text("ch2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        fp2 = get_working_diff(root)
        assert fp2["ok"]

        reserve_ok: list[bool] = []

        def try_reserve():
            mock_r, entered = _smart_mock(repo)
            with patch("saipenview.git_diff._run_git", side_effect=mock_r):
                entered.wait(timeout=2)
                reserve_ok.append(coord.ownership.reserve_agent(Path(root)))

        t = threading.Thread(target=try_reserve)
        t.start()
        time.sleep(0.05)

        mock_run2, entered2 = _smart_mock(repo)
        with patch("saipenview.git_diff._run_git", side_effect=mock_run2):
            result = revert_agent_work(root, fp2["fingerprint"])

        assert result["ok"] is True, result
        t.join(timeout=5)
        assert not t.is_alive()
        assert reserve_ok == [True]

    def test_delete_untracked_hold_lock_allows_reserve_after(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        root = canonical(repo)
        coord = get_coordinator()

        # Add an untracked file.
        (repo / "extra.txt").write_text("extra\n", encoding="utf-8")
        diff = get_working_diff(root)
        assert diff["ok"]
        fp = diff["fingerprint"]

        reserve_ok: list[bool] = []

        def try_reserve():
            mock_r, entered = _smart_mock(repo)
            with patch("saipenview.git_diff._run_git", side_effect=mock_r):
                entered.wait(timeout=2)
                reserve_ok.append(coord.ownership.reserve_agent(Path(root)))

        t = threading.Thread(target=try_reserve)
        t.start()
        time.sleep(0.05)

        mock_run, entered = _smart_mock(repo)
        with patch("saipenview.git_diff._run_git", side_effect=mock_run):
            result = delete_untracked_files(root, fp)

        assert result["ok"] is True, result
        t.join(timeout=5)
        assert not t.is_alive()
        assert reserve_ok == [True]

    def test_reserve_blocked_while_tx_held(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        root = canonical(repo)
        coord = get_coordinator()

        reserve_result: list[bool] = []
        tx_entered = threading.Event()

        def slow_mock(root_arg: str, args: list[str]):
            if args[0] in ("status", "diff", "rev-parse"):
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
            tx_entered.set()
            time.sleep(0.3)
            return subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        def try_reserve():
            tx_entered.wait(timeout=2)
            reserve_result.append(coord.ownership.reserve_agent(Path(root)))

        t = threading.Thread(target=try_reserve)
        t.start()
        time.sleep(0.05)

        fp = _stage_change(repo)
        with patch("saipenview.git_diff._run_git", side_effect=slow_mock):
            result = commit_agent_work(root, "test msg", fp)

        assert result["ok"] is True, result
        t.join(timeout=5)
        assert not t.is_alive()
        assert reserve_result == [True], f"got {reserve_result}"
