"""CORE-001: every Git mutation is bound to the verified preview snapshot.

The preview fingerprint is an authorization snapshot, not an early
precondition. Each mutation must act on the exact scope that was successfully
verified, revalidate the authorized path identities at the destructive
boundary, and never widen its scope from a later repository query.

These are deterministic barrier regressions: a pause is injected *after*
successful preview verification but *before* the actual Git mutation, the
worktree is mutated externally while the mutation is paused, and the operation
must either confine itself to the authorized scope or fail closed as a stale
preview. No sleeps, no polling -- two threading.Events and a bounded wait.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from saipenview import git_diff
from saipenview.git_diff import (
    commit_agent_work,
    delete_untracked_files,
    get_working_diff,
    revert_agent_work,
)

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)

BARRIER_TIMEOUT = 5.0


def _git(root: Path, *args, check=True) -> subprocess.CompletedProcess:
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


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.autocrlf", "false")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "init")
    return root


class _Boundary:
    """Pause the mutation at the revalidation boundary.

    ``_revalidate_authorized`` runs after the fingerprint has verified and the
    authorized identities were captured, and immediately before the Git
    mutation. Wrapping it lets a test mutate the worktree exactly inside that
    window, deterministically, without touching the production code.
    """

    def __init__(self):
        self.at_boundary = threading.Event()
        self.proceed = threading.Event()

    def install(self, monkeypatch):
        real = git_diff._revalidate_authorized
        boundary = self

        def wrapped(root, snapshot, paths):
            boundary.at_boundary.set()
            if not boundary.proceed.wait(BARRIER_TIMEOUT):
                raise AssertionError("test did not release the mutation barrier")
            return real(root, snapshot, paths)

        monkeypatch.setattr(git_diff, "_revalidate_authorized", wrapped)
        return self


def _run_paused(fn, *args):
    """Run a mutation in a worker thread; return the result holder + thread."""
    holder: dict = {}

    def worker():
        holder["result"] = fn(*args)

    t = threading.Thread(target=worker)
    t.start()
    return holder, t


def _await_boundary(boundary: _Boundary, thread: threading.Thread):
    assert boundary.at_boundary.wait(BARRIER_TIMEOUT), "mutation never reached the boundary"
    assert thread.is_alive(), "mutation returned before the injected late change"


# ── 1. Commit -- unrelated late untracked file ──────────────────────────────


def test_commit_excludes_unrelated_late_untracked_file(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(commit_agent_work, str(repo), "msg", preview["fingerprint"])
    _await_boundary(boundary, t)

    # External writer creates a never-previewed file inside the window.
    (repo / "late.txt").write_text("never reviewed\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    tree = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert "late.txt" not in tree
    assert "tracked.txt" in tree
    assert (repo / "late.txt").exists()


# ── 2. Commit -- late mutation of a previewed path ──────────────────────────


def test_commit_aborts_on_late_change_of_previewed_path(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(commit_agent_work, str(repo), "msg", preview["fingerprint"])
    _await_boundary(boundary, t)

    # External writer replaces the bytes of an ALREADY previewed path.
    (repo / "tracked.txt").write_text("late external\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    # No commit recorded, and the late bytes are untouched.
    assert "msg" not in _git(repo, "log", "--oneline").stdout
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "late external\n"


# ── 3. Revert -- unrelated late tracked edit survives ───────────────────────


def test_revert_keeps_unrelated_late_tracked_edit(repo, monkeypatch):
    (repo / "other.txt").write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(repo, "commit", "-qm", "add other")
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")

    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(revert_agent_work, str(repo), preview["fingerprint"])
    _await_boundary(boundary, t)

    # External writer edits an unrelated TRACKED path inside the window.
    (repo / "other.txt").write_text("late unrelated edit\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    # Authorized path restored; the unrelated late edit is outside scope.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert (repo / "other.txt").read_text(encoding="utf-8") == "late unrelated edit\n"


# ── 4. Revert -- late mutation of an authorized path aborts ─────────────────


def test_revert_aborts_on_late_change_of_authorized_path(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(revert_agent_work, str(repo), preview["fingerprint"])
    _await_boundary(boundary, t)

    (repo / "tracked.txt").write_text("late bytes\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    # The late bytes were NOT destroyed by a restore.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "late bytes\n"


# ── 5. Delete -- unrelated late untracked file survives ─────────────────────


def test_delete_keeps_unrelated_late_untracked_file(repo, monkeypatch):
    (repo / "old.txt").write_text("authorized\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]
    assert "old.txt" in preview["scope"]["untracked"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(delete_untracked_files, str(repo), preview["fingerprint"])
    _await_boundary(boundary, t)

    (repo / "late.txt").write_text("late\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    assert not (repo / "old.txt").exists()
    assert (repo / "late.txt").exists()


# ── 6. Delete -- changed/replaced authorized target fails closed ────────────


def test_delete_aborts_on_changed_authorized_target(repo, monkeypatch):
    (repo / "target.txt").write_text("v1\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _Boundary().install(monkeypatch)
    holder, t = _run_paused(delete_untracked_files, str(repo), preview["fingerprint"])
    _await_boundary(boundary, t)

    # External writer replaces the authorized untracked target's bytes.
    (repo / "target.txt").write_text("v2\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    assert (repo / "target.txt").read_text(encoding="utf-8") == "v2\n"


# ── Scope-binding guards ────────────────────────────────────────────────────


def test_revert_does_not_use_repository_wide_reset(repo, monkeypatch):
    """Revert must never run repository-wide ``git reset --hard``."""
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("survives\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    seen: list[list[str]] = []
    real_run_git = git_diff._run_git

    def spy(root, args):
        seen.append(list(args))
        return real_run_git(root, args)

    monkeypatch.setattr(git_diff, "_run_git", spy)
    res = revert_agent_work(str(repo), preview["fingerprint"])
    assert res["ok"], res

    assert not any(a[:2] == ["reset", "--hard"] for a in seen if a)
    assert (repo / "untracked.txt").exists()


def test_delete_does_not_use_repository_wide_clean(repo, monkeypatch):
    """Delete must never run a repository-wide ``git clean -fd``."""
    (repo / "target.txt").write_text("authorized\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    seen: list[list[str]] = []
    real_run_git = git_diff._run_git

    def spy(root, args):
        seen.append(list(args))
        return real_run_git(root, args)

    monkeypatch.setattr(git_diff, "_run_git", spy)
    res = delete_untracked_files(str(repo), preview["fingerprint"])
    assert res["ok"], res

    for args in seen:
        if args and args[0] == "clean":
            # A bare/global clean has no ``--`` path terminator; the scoped
            # form always names the exact targets after it.
            assert "--" in args, f"unscoped git clean: {args}"

# ── Class 2: barriers AFTER a successful revalidation ───────────────────────
#
# The barriers above pause *inside* ``_revalidate_authorized``: they prove the
# mutation reacts to a scope change, not that it survives one. These pause after
# the revalidation has already returned success and before the mutation consumes,
# restores or deletes its target, which is the window a non-cooperating writer
# can actually hit. ``RootOwnership`` cannot serialize an external editor, so the
# only real defence is that the destructive step stops depending on a later read
# of the path: Commit stages the captured bytes, Revert and Delete act on an
# object claimed with one atomic rename.


class _PostBoundary:
    """Pause after ``_revalidate_authorized`` returned success.

    ``revalidated`` is set only when the real revalidation returned ``None``, so
    every test can prove the authorization boundary had already been crossed
    before the external write was injected -- a wrapper that pauses *before* the
    real check would leave that event unset and fail the test.
    """

    def __init__(self, stage: str):
        self.stage = stage
        self.revalidated = threading.Event()
        self.at_seam = threading.Event()
        self.proceed = threading.Event()

    def install(self, monkeypatch):
        boundary = self
        real_revalidate = git_diff._revalidate_authorized
        real_seam = git_diff._mutation_seam

        def revalidate(root, snapshot, paths):
            result = real_revalidate(root, snapshot, paths)
            if result is None:
                boundary.revalidated.set()
            return result

        def seam(stage, paths):
            if stage != boundary.stage:
                return real_seam(stage, paths)
            boundary.at_seam.set()
            if not boundary.proceed.wait(BARRIER_TIMEOUT):
                raise AssertionError("test did not release the post-revalidation barrier")
            return real_seam(stage, paths)

        monkeypatch.setattr(git_diff, "_revalidate_authorized", revalidate)
        monkeypatch.setattr(git_diff, "_mutation_seam", seam)
        return self


def _await_post_boundary(boundary: _PostBoundary, thread: threading.Thread):
    assert boundary.at_seam.wait(BARRIER_TIMEOUT), (
        "mutation never reached the post-revalidation seam"
    )
    assert boundary.revalidated.is_set(), (
        "_revalidate_authorized had not returned success before the injected write"
    )
    assert thread.is_alive(), "mutation returned before the injected late change"


# ── 7. Commit -- late write cannot replace reviewed bytes in the commit ─────


def test_commit_after_revalidation_commits_reviewed_bytes_only(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("capture-complete").install(monkeypatch)
    holder, t = _run_paused(
        commit_agent_work, str(repo), "post-reval", preview["fingerprint"]
    )
    _await_post_boundary(boundary, t)

    # External writer replaces an authorized path AFTER revalidation passed.
    (repo / "tracked.txt").write_text("late external\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    # The commit contains exactly the reviewed bytes, not the late ones.
    assert _git(repo, "show", "HEAD:tracked.txt").stdout == "reviewed\n"
    assert "late external" not in _git(repo, "show", "HEAD:tracked.txt").stdout
    # The late bytes were not destroyed either: they stand as an unstaged edit.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "late external\n"
    # index == HEAD (reviewed bytes), worktree holds the late edit: unstaged.
    status = _git(repo, "status", "--porcelain").stdout
    assert status.startswith(" M tracked.txt"), repr(status)


def test_commit_after_revalidation_ignores_a_new_untracked_file(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("capture-complete").install(monkeypatch)
    holder, t = _run_paused(
        commit_agent_work, str(repo), "post-reval", preview["fingerprint"]
    )
    _await_post_boundary(boundary, t)

    (repo / "appeared-late.txt").write_text("never reviewed\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    tree = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert tree == ["tracked.txt"], tree
    assert (repo / "appeared-late.txt").exists()


# ── 8. Revert -- a post-revalidation edit is never destroyed ────────────────


def test_revert_after_revalidation_preserves_late_bytes(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("before-claim").install(monkeypatch)
    holder, t = _run_paused(revert_agent_work, str(repo), preview["fingerprint"])
    _await_post_boundary(boundary, t)

    (repo / "tracked.txt").write_text("late bytes\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    # The late edit is intact: it was claimed, recognised as unknown content and
    # put back, instead of being overwritten by the restore.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "late bytes\n"


def test_revert_does_not_clobber_a_write_that_lands_after_the_claim(repo, monkeypatch):
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("claimed").install(monkeypatch)
    holder, t = _run_paused(revert_agent_work, str(repo), preview["fingerprint"])
    _await_post_boundary(boundary, t)

    # The reviewed bytes are already claimed out of the way; a writer recreates
    # the path inside the install window.
    (repo / "tracked.txt").write_text("brand new\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    # O_EXCL refuses to overwrite it, so the newest write survives.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "brand new\n"


# ── 9. Delete -- a post-revalidation replacement is never removed ───────────


def test_delete_after_revalidation_keeps_the_replacement(repo, monkeypatch):
    (repo / "target.txt").write_text("v1\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("before-claim").install(monkeypatch)
    holder, t = _run_paused(
        delete_untracked_files, str(repo), preview["fingerprint"]
    )
    _await_post_boundary(boundary, t)

    (repo / "target.txt").write_text("v2 late\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert not res["ok"], res
    assert (repo / "target.txt").read_text(encoding="utf-8") == "v2 late\n"


def test_delete_acts_on_the_claimed_object_not_the_path(repo, monkeypatch):
    (repo / "target.txt").write_text("authorized\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    boundary = _PostBoundary("claimed").install(monkeypatch)
    holder, t = _run_paused(
        delete_untracked_files, str(repo), preview["fingerprint"]
    )
    _await_post_boundary(boundary, t)

    # The authorized file is already claimed; a writer recreates the path.
    (repo / "target.txt").write_text("new file\n", encoding="utf-8")
    boundary.proceed.set()
    t.join(BARRIER_TIMEOUT)
    assert not t.is_alive()

    res = holder["result"]
    assert res["ok"], res
    # Exactly the reviewed object was removed; the newcomer is untouched.
    assert (repo / "target.txt").read_text(encoding="utf-8") == "new file\n"


# ── 10. The mutation never falls back to a worktree re-reading command ─────


def test_mutations_never_re_read_the_worktree(repo, monkeypatch):
    """No ``git add``/``git restore``/``git clean`` after the boundary.

    Those commands take their content from the worktree at execution time, which
    is precisely the check-then-act gap CORE-001 is about.
    """
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    (repo / "extra.txt").write_text("untracked\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]

    seen: list[list[str]] = []
    real_run_git = git_diff._run_git

    def spy(root, args):
        seen.append(list(args))
        return real_run_git(root, args)

    monkeypatch.setattr(git_diff, "_run_git", spy)
    assert commit_agent_work(str(repo), "no reread", preview["fingerprint"])["ok"]

    preview = get_working_diff(str(repo))
    assert preview["ok"]
    assert delete_untracked_files(str(repo), preview["fingerprint"])["ok"]

    (repo / "tracked.txt").write_text("again\n", encoding="utf-8")
    preview = get_working_diff(str(repo))
    assert preview["ok"]
    assert revert_agent_work(str(repo), preview["fingerprint"])["ok"]

    forbidden = {"add", "restore", "checkout", "clean", "reset", "stash"}
    offenders = [args for args in seen if args and args[0] in forbidden]
    assert offenders == [], offenders

# ── 11. Snapshot-bound staging still honours git attributes ────────────────


def test_snapshot_bound_commit_applies_gitattributes_like_git_add(repo, monkeypatch):
    """The captured bytes go through the same clean filters ``git add`` applies.

    Writing blobs straight from captured content is equivalent to ``git add``
    only when the path's attributes are honoured: ``hash-object --path`` runs the
    clean filter, while a ``--no-filters`` shortcut would store CRLF where the
    repository stores LF and silently rewrite the file's diff history.
    """
    (repo / ".gitattributes").write_text("*.txt text eol=lf\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attributes")
    (repo / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")

    preview = get_working_diff(str(repo))
    assert preview["ok"]

    seen: list[list[str]] = []
    real_run_git = git_diff._run_git

    def spy(root, args):
        seen.append(list(args))
        return real_run_git(root, args)

    monkeypatch.setattr(git_diff, "_run_git", spy)
    res = commit_agent_work(str(repo), "attributes", preview["fingerprint"])
    assert res["ok"], res

    # Raw bytes: text mode would hide the CRLF this asserts against.
    blob = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", "HEAD:crlf.txt"],
        capture_output=True,
    ).stdout
    assert blob == b"one\ntwo\n", blob
    # Built from the reviewed bytes, never by re-reading the worktree.
    assert not [a for a in seen if a and a[0] in {"add", "restore", "clean"}]


# ── 9. Revert -- a post-index-write failure restores the index ──────────────

def test_revert_restores_the_index_when_it_fails_after_rewriting_it(repo, monkeypatch):
    """Revert repoints index entries at the HEAD blob ids. If anything fails
    after that write, the index must come back byte-identical -- otherwise the
    user's own staged work is silently unstaged while the returned error names
    an unrelated cause."""
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged content\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")

    preview = get_working_diff(str(repo))
    assert preview["ok"]
    staged_before = _git(repo, "diff", "--cached", "--name-status").stdout
    tree_before = _git(repo, "write-tree").stdout

    real_run_git = git_diff._run_git

    def fail_checkout_index(root, args):
        # Deterministic failure AFTER _set_index_entries has already run.
        if args and args[0] == "checkout-index":
            return subprocess.CompletedProcess(
                args=["git", *args], returncode=1, stdout="", stderr="injected"
            )
        return real_run_git(root, args)

    monkeypatch.setattr(git_diff, "_run_git", fail_checkout_index)
    res = revert_agent_work(str(repo), preview["fingerprint"])

    assert not res["ok"], res
    assert _git(repo, "diff", "--cached", "--name-status").stdout == staged_before
    assert _git(repo, "write-tree").stdout == tree_before
    # The worktree is untouched too: the user's edits are still theirs.
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "reviewed\n"
    assert (repo / "staged.txt").read_text(encoding="utf-8") == "staged content\n"
