"""T-891, T-892, T-899, T-900: the git mutation path must be failure-atomic.

Each test proves one omission the audit found in ``git_diff.py`` by driving the
real entry points against a real temporary git repository, with exactly one
fault injected. The invariant every one of them asserts is the same sentence:
**when a mutation refuses, the index is byte-identical to how it was before the
call** -- and when user bytes are preserved instead of restored, the caller is
told where they are.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from saipenview import git_diff


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"
    return r.stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "Tester")
    (root / "a.txt").write_text("original\n", encoding="utf-8")
    (root / "zzz.txt").write_text("other\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    return root


def _staged_state(root: Path) -> str:
    return _git(root, "diff", "--cached", "--name-status")


def _fingerprint(root: str) -> str:
    state = git_diff._current_state(root)
    assert state.get("ok"), state
    return state["fingerprint"]


def test_t891_revert_install_failure_restores_the_index(repo):
    """T-891: the install-failure branch must restore the index like every
    sibling failure in the same try. Before the fix the branch returned without
    `_restore_index`, leaving the HEAD repointing that `_set_index_entries` had
    already written -- a half-applied revert plus the user's own staged work
    silently unstaged."""
    # The user has staged their own edits on BOTH paths. A revert repoints the
    # index at HEAD, so without the restore this staged work is silently
    # unstaged -- and staging it on an authorized path is what makes the loss
    # observable rather than a no-op.
    (repo / "a.txt").write_text("user staged edit\n", encoding="utf-8")
    (repo / "zzz.txt").write_text("user staged other\n", encoding="utf-8")
    _git(repo, "add", ".")
    before = _staged_state(repo)
    assert "a.txt" in before and "zzz.txt" in before, before

    fingerprint = _fingerprint(str(repo))
    real_install = git_diff._install_exclusive
    calls = {"n": 0}

    def failing_install(src: Path, target: Path, mode: str) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            return False  # refuse the FIRST authorized path
        return real_install(src, target, mode)

    with patch.object(git_diff, "_install_exclusive", failing_install):
        result = git_diff.revert_agent_work(str(repo), fingerprint)

    assert result["ok"] is False, result
    assert calls["n"] == 1, "the fault was never reached"
    assert _staged_state(repo) == before, (
        "the index was left rewritten after a refused revert; the user's staged "
        "work is no longer where they put it"
    )


def test_t892_rejected_commit_restores_the_index(repo):
    """T-892: a pre-commit hook that rejects the commit must leave the index as
    it was. Before the fix the function returned the git error without
    `_restore_index`, and `staging.cleanup()` then unlinked `index_backup`, so
    the original index was unrecoverable even by hand."""
    hooks = repo / ".git" / "hooks" / "pre-commit"
    hooks.parent.mkdir(parents=True, exist_ok=True)
    hooks.write_text("#!/bin/sh\necho 'policy: nope' >&2\nexit 1\n", encoding="utf-8")

    (repo / "a.txt").write_text("agent edit\n", encoding="utf-8")
    (repo / "zzz.txt").write_text("other edit\n", encoding="utf-8")
    before = _staged_state(repo)

    fingerprint = _fingerprint(str(repo))
    result = git_diff.commit_agent_work(str(repo), "agent work", fingerprint)

    assert result["ok"] is False, result
    assert "policy: nope" in result["error"]
    assert _staged_state(repo) == before, (
        "the index kept the mutation's writes after the commit was rejected"
    )


def test_t899_unreadable_staged_paths_refuses_instead_of_committing(repo):
    """T-899: `_staged_paths` used to return [] when git failed, which reads as
    "nothing is staged outside the reviewed scope" and let the guard pass
    vacuously -- the exact condition the guard exists to catch."""
    (repo / "a.txt").write_text("agent edit\n", encoding="utf-8")
    fingerprint = _fingerprint(str(repo))

    real = git_diff._run_git
    failed = {"n": 0}

    def blind_git(root: str, args: list[str]):
        if args[:3] == ["diff", "--cached", "--name-only"]:
            failed["n"] += 1
            return subprocess.CompletedProcess(args, 128, "", "index.lock exists")
        return real(root, args)

    with patch.object(git_diff, "_run_git", blind_git):
        result = git_diff.commit_agent_work(str(repo), "agent work", fingerprint)

    assert failed["n"] == 1, "the staged-scope guard was never consulted"
    assert result["ok"] is False, "a commit proceeded with an unverifiable scope"
    assert result["code"] == "SCOPE_UNVERIFIABLE", result
    assert _git(repo, "log", "--oneline").count("\n") == 1, "a commit was created"


def test_t900_preserved_bytes_are_named_not_dropped(repo):
    """T-900: a claim that cannot be put back stays on disk -- it is the only
    pointer to recoverable user work. `_claim_all` used to report it only when
    THIS path's own restore failed, so a successful restore on the conflicting
    path silently dropped every OTHER path that was preserved instead."""
    staging = git_diff._Staging(repo, repo / ".git")
    fake: dict[str, Path] = {}

    def fake_claim(root: str, rel: str, st) -> Path:
        fake[rel] = st.base / f"claim-{rel}"
        return fake[rel]

    def identity_at(path: Path) -> str:
        # zzz.txt verifies; a.txt is the late-write conflict.
        return "verified" if "zzz" in path.name else "late-write"

    identities = {"zzz.txt": "verified", "a.txt": "verified"}

    with (
        patch.object(git_diff, "_claim_path", fake_claim),
        patch.object(git_diff, "_identity_at", identity_at),
        # The conflicting path itself goes back cleanly...
        patch.object(git_diff, "_release_claim", lambda claim, target: True),
        # ...while the earlier claim could NOT, so its bytes survive.
        patch.object(git_diff, "_release_claims", lambda root, claims: [str(fake["zzz.txt"])]),
    ):
        claims, conflict = git_diff._claim_all(
            str(repo), ["zzz.txt", "a.txt"], identities, staging
        )

    assert claims == {}
    assert conflict is not None, "an identity mismatch must fail closed"
    assert conflict["code"] == "PREVIEW_STALE", conflict
    assert "reviewed bytes are kept at" in conflict["error"], (
        "a preserved claim went unreported, so the user cannot find their own "
        f"bytes: {conflict}"
    )
    # _conflict_error repr()s the location, so match the claim name itself.
    assert "claim-zzz.txt" in conflict["error"], (
        f"the reported location is not the surviving claim: {conflict}"
    )
    assert "claim-a.txt" not in conflict["error"], conflict