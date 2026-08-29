"""T-162: git mutation-scope honesty.

Each test runs against a real temporary git repository so the scope parser,
commit staging and revert behaviour are verified against git itself, not
against mocks.

The ten scenarios the ticket requires:

1. modified tracked file is displayed
2. staged file is displayed
3. untracked file is displayed
4. ignored file never enters the mutation scope
5. Commit does not include a file that appeared after the preview
6. tracked-only restore does not delete untracked files
7. untracked deletion requires its own separate operation
8. a status change after the preview cancels the mutation
9. paths with spaces and Unicode work
10. a worktree whose ``.git`` is a FILE is supported
"""

from __future__ import annotations

import subprocess

import pytest

from saipenview.git_diff import (
    commit_agent_work,
    delete_untracked_files,
    get_working_diff,
    is_git_repo,
    revert_agent_work,
)

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


@pytest.fixture
def repo(tmp_path):
    """A fresh git repository with one committed tracked file."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.autocrlf", "false")
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "init")
    return root


def _git(root, *args, check=True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and r.returncode != 0:
        raise AssertionError(f"git {args!r} failed: {r.stderr}")
    return r


def _untracked_paths(scope: dict) -> list[str]:
    return scope["scope"]["untracked"]


def test_modified_tracked_file_is_displayed(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    res = get_working_diff(str(repo))
    assert res["ok"]
    assert "tracked.txt" in res["diff"]
    assert "tracked.txt" in res["scope"]["modified"]
    assert res["scope"]["counts"]["modified"] == 1


def test_staged_file_is_displayed(repo):
    (repo / "staged.txt").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    res = get_working_diff(str(repo))
    assert res["ok"]
    assert "staged.txt" in res["scope"]["staged"]
    assert "staged.txt" in res["diff"]


def test_untracked_file_is_displayed(repo):
    (repo / "new.txt").write_text("hello\n", encoding="utf-8")
    res = get_working_diff(str(repo))
    assert res["ok"]
    assert "new.txt" in _untracked_paths(res)
    assert "hello" in res["diff"]


def test_ignored_file_never_enters_scope(repo):
    (repo / ".gitignore").write_text("secret.log\n", encoding="utf-8")
    (repo / "secret.log").write_text("ignored\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "add gitignore")
    res = get_working_diff(str(repo))
    assert res["ok"]
    assert "secret.log" not in _untracked_paths(res)
    assert res["scope"]["counts"]["untracked"] == 0


def test_commit_does_not_include_a_file_that_appeared_after_preview(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    (repo / "sneaky.txt").write_text("late\n", encoding="utf-8")

    res = commit_agent_work(str(repo), "msg", preview["fingerprint"])
    assert not res["ok"]
    assert (
        "changed" in res["error"].lower()
        or "changed" in res["error"]
        or "status" in res["error"].lower()
    )

    log = _git(repo, "log", "--oneline").stdout
    assert "msg" not in log


def test_commit_with_stale_fingerprint_aborts(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    (repo / "another.txt").write_text("x\n", encoding="utf-8")

    res = commit_agent_work(str(repo), "msg", preview["fingerprint"])
    assert not res["ok"]


def test_tracked_only_restore_keeps_untracked(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("keep me\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    res = revert_agent_work(str(repo), preview["fingerprint"])
    assert res["ok"]
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "one\n"
    assert (repo / "untracked.txt").exists()


def test_untracked_deletion_requires_separate_operation(repo):
    (repo / "untracked.txt").write_text("data\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    revert_agent_work(str(repo), preview["fingerprint"])
    assert (repo / "untracked.txt").exists()

    preview2 = get_working_diff(str(repo))
    res = delete_untracked_files(str(repo), preview2["fingerprint"])
    assert res["ok"]
    assert not (repo / "untracked.txt").exists()


def test_untracked_deletion_ignored_files_survive(repo):
    (repo / ".gitignore").write_text("keep.log\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "gitignore")
    (repo / "keep.log").write_text("ignored\n", encoding="utf-8")
    (repo / "real.txt").write_text("untracked\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]
    res = delete_untracked_files(str(repo), preview["fingerprint"])
    assert res["ok"]
    assert (repo / "keep.log").exists()
    assert not (repo / "real.txt").exists()


def test_status_change_after_preview_cancels_mutation(repo):
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    (repo / "tracked.txt").write_text("changed again\n", encoding="utf-8")

    assert not revert_agent_work(str(repo), preview["fingerprint"])["ok"]
    assert not commit_agent_work(str(repo), "m", preview["fingerprint"])["ok"]
    assert not delete_untracked_files(str(repo), preview["fingerprint"])["ok"]


def test_paths_with_spaces_and_unicode(repo):
    folder = repo / "folder with spaces"
    folder.mkdir(exist_ok=True)
    weird = folder / "ünïcödé file .txt"
    weird.write_text("spaced\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]
    assert any("ü" in p and " " in p for p in _untracked_paths(preview))

    res = commit_agent_work(str(repo), "weird paths", preview["fingerprint"])
    assert res["ok"]
    log = _git(repo, "log", "--oneline").stdout
    assert "weird paths" in log
    assert weird.exists()


def test_worktree_with_git_file_is_supported(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "test@example.com")
    _git(main, "config", "user.name", "Test")
    (main / "a.txt").write_text("a\n", encoding="utf-8")
    _git(main, "add", "a.txt")
    _git(main, "commit", "-qm", "init")
    _git(main, "branch", "-M", "main")

    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", "-b", "wtbranch", str(wt), "main")
    assert wt.joinpath(".git").is_file()

    assert is_git_repo(str(wt))
    (wt / "b.txt").write_text("b\n", encoding="utf-8")
    res = get_working_diff(str(wt))
    assert res["ok"]
    assert "b.txt" in _untracked_paths(res)


def test_non_git_dir_reports_clean_error(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    res = get_working_diff(str(plain))
    assert not res["ok"]
    assert "git" in res["error"].lower()


def test_scope_fingerprint_is_stable_until_tree_changes(repo):
    from saipenview.git_diff import _current_state

    f1 = _current_state(str(repo))["fingerprint"]
    f2 = _current_state(str(repo))["fingerprint"]
    assert f1 == f2
    (repo / "untracked.txt").write_text("x\n", encoding="utf-8")
    f3 = _current_state(str(repo))["fingerprint"]
    assert f3 != f1


def test_preview_streams_each_tracked_diff_once(repo):
    from unittest.mock import patch

    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    (repo / "tracked.txt").write_text("changed again\n", encoding="utf-8")

    from saipenview import git_diff

    original = git_diff._stream_git_diff
    with patch.object(git_diff, "_stream_git_diff", wraps=original) as stream:
        result = get_working_diff(str(repo))

    assert result["ok"]
    assert [call.args[1] for call in stream.call_args_list] == [
        ["diff", "--cached"],
        ["diff"],
    ]


def test_large_untracked_preview_uses_bounded_read(repo):
    from pathlib import Path
    from unittest.mock import patch

    (repo / "large.bin").write_bytes(b"x" * (3 * 1024 * 1024))
    from saipenview import git_diff

    with patch.object(
        Path, "read_bytes", side_effect=AssertionError("whole-file read")
    ):
        result = get_working_diff(str(repo))

    assert result["ok"]
    assert len(result["diff"]) < 3 * 1024 * 1024
    assert result["fingerprint"] == git_diff._current_state(str(repo))["fingerprint"]
