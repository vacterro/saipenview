"""Git mutation-scope layer (T-162).

The old implementation showed only `git diff` output (staged + unstaged
tracked) while `commit_agent_work()` ran `git add .` and
`revert_agent_work()` ran `git reset --hard` + `git clean -fd`. Commit could
therefore include files that were never shown in the preview, and Revert
could delete untracked files that were equally invisible. This module makes
the *mutation scope* explicit: every operation re-reads `git status`, works
only on the categories it was authorised for, and aborts when the status
changed since the preview was shown.

Scope categories (from `git status --porcelain=v1 -z`):

- staged       -- index carries a change (M/A/D/R/C/U in column 1)
- modified     -- tracked worktree modification (M in column 2)
- deleted      -- tracked deletion (D in either column)
- renamed      -- R/C entries; destination is the operative path
- untracked    -- ``??``; never includes ignored files, git itself excludes
                  them from ``git status`` output, so ignored files cannot
                  enter any mutation scope by construction
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _run_git(root: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=10,
    )


def is_git_repo(root: str) -> bool:
    """True when *root* sits inside a git worktree.

    ``(root / ".git").exists()`` is not used on purpose: a linked worktree
    carries ``.git`` as a FILE, so the directory probe would reject valid
    worktrees (T-162 required test 10).
    """
    try:
        r = _run_git(root, ["rev-parse", "--git-dir"])
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def status_scope(root: str) -> dict:
    """Read and categorise the full mutation scope.

    Returns ``{"ok": True, "scope": {...}}`` or an error dict. The
    fingerprint is NOT computed here -- porcelain status cannot see the
    content of an already-modified tracked file, so the fingerprint lives in
    ``_current_state`` which also hashes the diffs and untracked contents.
    """
    try:
        r = _run_git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "git status failed").strip()}

    staged: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    renamed: list[dict] = []
    untracked: list[str] = []

    entries = _parse_status_entries(r.stdout)
    for codes, first, second in entries:
        if codes == "??":
            untracked.append(first)
            continue
        if codes[0] in "RC":
            renamed.append({"from": second or "", "to": first})
            continue
        if codes[0] in "MADU" or (codes[0] != " " and codes[1] != " "):
            staged.append(first)
        if codes[1] == "M":
            modified.append(first)
        if "D" in codes:
            deleted.append(first)

    scope = {
        "staged": staged,
        "modified": modified,
        "deleted": deleted,
        "renamed": renamed,
        "untracked": untracked,
        "counts": {
            "staged": len(staged),
            "modified": len(modified),
            "deleted": len(deleted),
            "renamed": len(renamed),
            "untracked": len(untracked),
            "total": (
                len(staged)
                + len(modified)
                + len(deleted)
                + len(renamed)
                + len(untracked)
            ),
        },
    }
    return {"ok": True, "scope": scope, "status_raw": r.stdout}


def _tree_fingerprint(root: str, scope: dict, status_raw: str) -> tuple[str, list[str]]:
    """Hash the working tree's real mutation evidence.

    Porcelain status alone is insufficient: a tracked file that was already
    `` M`` keeps the same status line when its content changes, so a preview
    fingerprint built only from status would not notice the content drift.
    The hash therefore covers status output, both diffs (staged + unstaged)
    and the bytes of every untracked file -- any of them moving invalidates
    the fingerprint (T-162 required test 8).

    Returns (fingerprint, unreadable_files). When unreadable_files is
    non-empty the caller MUST refuse the preview (CORE-003 fail-closed).
    """
    h = hashlib.sha256()
    h.update(status_raw.encode("utf-8", "replace"))
    for args in (["diff", "--cached"], ["diff"]):
        try:
            r = _run_git(root, args)
            h.update(r.stdout.encode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError):
            pass
    unreadable: list[str] = []
    for path in sorted(scope["untracked"]):
        try:
            data = Path(root, path).read_bytes()
        except OSError:
            unreadable.append(path)
            continue
        h.update(path.encode("utf-8", "replace"))
        h.update(b"\x00")
        h.update(data)
    return h.hexdigest(), unreadable


def _current_state(root: str) -> dict:
    """scope + fingerprint in one call (the honest preview state).

    When untracked files are unreadable, returns a failure so the preview
    refuses instead of silently omitting evidence (CORE-003)."""
    scope_res = status_scope(root)
    if not scope_res.get("ok"):
        return scope_res
    fingerprint, unreadable = _tree_fingerprint(root, scope_res["scope"], scope_res["status_raw"])
    if unreadable:
        return {
            "ok": False,
            "error": (
                f"Cannot preview: {len(unreadable)} untracked file(s) unreadable "
                f"({', '.join(unreadable[:5])}); refusing to mutate with "
                "incomplete evidence"
            ),
        }
    return {"ok": True, "scope": scope_res["scope"], "fingerprint": fingerprint}


def _parse_status_entries(raw: str) -> list[tuple[str, str, str]]:
    """Parse NUL-separated porcelain v1 output into (codes, path, extra).

    Each header is ``<XY> <path>``; a rename/copy header is immediately
    followed by a second NUL-delimited record carrying the source path. The
    sequential walk is unambiguous because ``-z`` emits raw (unquoted) paths
    separated by NUL -- a source path is just the next record.
    """
    parts = raw.split("\x00")
    entries: list[tuple[str, str, str]] = []
    i = 0
    n = len(parts)
    while i < n:
        part = parts[i]
        if not part:
            i += 1
            continue
        codes = part[:2]
        path = part[2:]
        if path.startswith(" "):
            path = path[1:]
        src = ""
        if codes[0] in "RC" and i + 1 < n:
            src = parts[i + 1]
            i += 1
        entries.append((codes, path, src))
        i += 1
    return entries


def _mutation_paths(scope: dict) -> list[str]:
    """All paths Commit is authorised to stage, in preview order."""
    paths: list[str] = []
    paths.extend(scope["staged"])
    paths.extend(scope["modified"])
    paths.extend(scope["deleted"])
    paths.extend(r["to"] for r in scope["renamed"])
    paths.extend(scope["untracked"])
    return paths


def _require_fingerprint(fingerprint: str | None) -> dict | None:
    """Return an error dict when the fingerprint is missing/empty.

    Every public Commit/Revert/Delete MUST carry a non-empty preview
    fingerprint (CORE-003). Without it the caller never showed the user
    the exact mutation scope, so proceeding is an authorization gap.
    """
    if not fingerprint:
        return {
            "ok": False,
            "code": "PREVIEW_REQUIRED",
            "error": (
                "No preview fingerprint provided. Run get_working_diff() first "
                "and review the scope before mutating."
            ),
        }
    return None


def _verify_fingerprint(root: str, expected: str | None) -> dict | None:
    """Re-read status and compare fingerprints.

    Returns an error dict when the working tree moved after the preview was
    shown, else None. Any status change means the preview is stale and the
    mutation must not proceed (T-162 required test 8).
    """
    if not expected:
        return _require_fingerprint(expected)
    current = _current_state(root)
    if not current.get("ok"):
        return current
    if current["fingerprint"] != expected:
        return {
            "ok": False,
            "error": (
                "Working tree changed since the preview was shown; "
                "refresh and review the new scope before mutating."
            ),
        }
    return None


def get_working_diff(
    root: str, untracked_cap_lines: int = 200, untracked_cap_total: int = 2000
) -> dict:
    """Full preview: tracked diffs plus untracked-file content, plus scope."""
    if not is_git_repo(root):
        return {"ok": False, "error": "Not a git repository"}
    try:
        staged = _run_git(root, ["diff", "--cached"])
        unstaged = _run_git(root, ["diff"])
        if staged.returncode != 0 or unstaged.returncode != 0:
            return {
                "ok": False,
                "error": (
                    staged.stderr or unstaged.stderr or "git diff failed"
                ).strip(),
            }
        current = _current_state(root)
        if not current.get("ok"):
            return current
        untracked_text = _render_untracked(
            root,
            current["scope"]["untracked"],
            cap_lines=untracked_cap_lines,
            cap_total=untracked_cap_total,
        )
        diff_text = staged.stdout + unstaged.stdout
        if untracked_text:
            diff_text = (
                (diff_text.rstrip("\n") + "\n" + untracked_text)
                if diff_text.strip()
                else untracked_text
            )
        return {
            "ok": True,
            "diff": diff_text,
            "scope": current["scope"],
            "fingerprint": current["fingerprint"],
        }
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def _render_untracked(
    root: str,
    files: list[str],
    cap_lines: int = 200,
    cap_total: int = 2000,
    cap_bytes: int = 2 * 1024 * 1024,
) -> str:
    """Render untracked files as new-file diff hunks so the preview shows
    everything Commit would actually include (T-162: no invisible files)."""
    parts: list[str] = []
    total = 0
    for f in files:
        p = Path(root) / f
        try:
            with p.open("rb") as fh:
                data = fh.read(cap_bytes + 1)
        except OSError:
            continue
        truncated = len(data) > cap_bytes
        if truncated:
            data = data[:cap_bytes]
        if b"\x00" in data[:8192]:
            parts.append(f"diff --git a/{f} b/{f}\nnew file mode 100644\nBinary file\n")
            total += 1
            continue
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if truncated:
            lines.append(f"... ({cap_bytes} bytes shown, file larger -- truncated)")
        shown = lines[:cap_lines]
        if len(lines) > cap_lines:
            shown.append(f"... ({len(lines) - cap_lines} more lines not shown)")
        body = "\n".join("+" + line for line in shown)
        parts.append(
            f"diff --git a/{f} b/{f}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{f}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
        total += len(lines)
        if total > cap_total:
            parts.append("... untracked preview truncated ...")
            break
    return "\n".join(parts)


def commit_agent_work(root: str, message: str, fingerprint: str | None = None) -> dict:
    """Stage exactly the previewed scope and commit it.

    Never runs ``git add .`` -- only the paths that were shown in the preview
    are staged, so a file that appeared after the preview cannot slip in
    unnoticed (the fingerprint guard rejects it outright).

    Requires a non-empty fingerprint: the caller must have shown the user
    the exact scope via get_working_diff() (CORE-003)."""
    if not message or not message.strip():
        return {"ok": False, "error": "Commit message is empty"}
    req = _require_fingerprint(fingerprint)
    if req:
        return req
    mismatch = _verify_fingerprint(root, fingerprint)
    if mismatch:
        return mismatch
    scope_res = status_scope(root)
    if not scope_res.get("ok"):
        return scope_res
    paths = _mutation_paths(scope_res["scope"])
    try:
        if paths:
            add = _run_git(root, ["add", "--"] + paths)
            if add.returncode != 0:
                return {"ok": False, "error": f"git add failed: {add.stderr.strip()}"}
        commit = _run_git(root, ["commit", "-m", message])
        if commit.returncode != 0:
            return {
                "ok": False,
                "error": f"Git command failed: {commit.stderr.strip()}",
            }
        return {"ok": True}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def revert_agent_work(root: str, fingerprint: str | None = None) -> dict:
    """Restore tracked changes only.

    ``git reset --hard`` re-stages-and-restores tracked modified/deleted/
    staged work. Untracked files are deliberately NOT removed -- deleting
    them is the separate ``delete_untracked_files`` operation (T-162).

    Requires a non-empty fingerprint (CORE-003)."""
    req = _require_fingerprint(fingerprint)
    if req:
        return req
    mismatch = _verify_fingerprint(root, fingerprint)
    if mismatch:
        return mismatch
    try:
        reset = _run_git(root, ["reset", "--hard"])
        if reset.returncode != 0:
            return {"ok": False, "error": f"git reset failed: {reset.stderr.strip()}"}
        return {"ok": True}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}


def delete_untracked_files(root: str, fingerprint: str | None = None) -> dict:
    """Delete untracked (non-ignored) files and directories.

    This is the destructive operation that ordinary Revert must NOT do. It
    requires its own explicit authorisation, and it never touches ignored
    files (``git clean -fd`` excludes them).

    Requires a non-empty fingerprint (CORE-003)."""
    req = _require_fingerprint(fingerprint)
    if req:
        return req
    mismatch = _verify_fingerprint(root, fingerprint)
    if mismatch:
        return mismatch
    try:
        clean = _run_git(root, ["clean", "-fd"])
        if clean.returncode != 0:
            return {"ok": False, "error": f"git clean failed: {clean.stderr.strip()}"}
        return {"ok": True}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}
