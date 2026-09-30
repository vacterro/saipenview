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

Snapshot binding (CORE-001): a preview fingerprint authorizes a scope, and
the reviewed *content* of that scope is captured with it. Commit writes git
objects from the captured bytes instead of asking `git add` to re-read the
worktree; Revert and Delete claim each authorized path with a single atomic
rename and check the claimed object against the reviewed identity before
destroying anything. A write that lands inside that window is refused or
preserved -- never silently committed, overwritten or deleted.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Sequence


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
    h = hashlib.sha256()
    h.update(status_raw.encode("utf-8", "replace"))
    for args in (["diff", "--cached"], ["diff"]):
        try:
            _stream_git_diff(root, args, h, 1)
        except (OSError, subprocess.SubprocessError, GitError):
            pass
    unreadable: list[str] = []
    for path in sorted(scope["untracked"]):
        try:
            with (Path(root) / path).open("rb") as handle:
                h.update(path.encode("utf-8", "replace"))
                h.update(b"\x00")
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    h.update(chunk)
        except OSError:
            unreadable.append(path)
    return h.hexdigest(), unreadable


def _stream_git_diff(root: str, args: list[str], hasher, cap_bytes: int) -> str:
    process = subprocess.Popen(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    preview = bytearray()
    if process.stdout is None:
        process.kill()
        process.wait()
        raise GitError("git diff produced no output stream")
    try:
        while chunk := process.stdout.read(64 * 1024):
            hasher.update(chunk)
            if len(preview) < cap_bytes:
                preview.extend(chunk[: cap_bytes - len(preview)])
        stderr = (
            process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        )
        returncode = process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        process.kill()
        process.wait()
        raise
    if returncode != 0:
        raise GitError((stderr or "git diff failed").strip())
    return bytes(preview).decode("utf-8", errors="replace")


def _read_untracked(path: Path, hasher, cap_bytes: int) -> tuple[bytes, bool]:
    preview = bytearray()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            hasher.update(chunk)
            if len(preview) <= cap_bytes:
                preview.extend(chunk[: cap_bytes + 1 - len(preview)])
    truncated = len(preview) > cap_bytes
    if truncated:
        del preview[cap_bytes:]
    return bytes(preview), truncated


def _preview_lines(data: bytes, cap_lines: int) -> tuple[list[str], int]:
    raw_lines = data.split(b"\n", cap_lines)
    shown = [
        line.rstrip(b"\r").decode("utf-8", errors="replace")
        for line in raw_lines[:cap_lines]
    ]
    line_count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return shown, line_count


def _state_with_preview(
    root: str,
    cap_lines: int = 200,
    cap_total: int = 2000,
    cap_bytes: int = 2 * 1024 * 1024,
) -> dict:
    """PERF-008: single-pass scope + fingerprint + diff preview.

    Runs git status, git diff --cached, and git diff exactly once each.
    The outputs are reused for scope categorisation, fingerprint hashing,
    and preview rendering -- eliminating the redundant subprocess calls
    that _current_state + get_working_diff previously issued.
    """
    # 1. Status (scope + raw for fingerprint)
    try:
        status_r = _run_git(
            root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}
    if status_r.returncode != 0:
        return {"ok": False, "error": (status_r.stderr or "git status failed").strip()}
    status_raw = status_r.stdout

    staged, modified, deleted, renamed, untracked = [], [], [], [], []
    for codes, first, second in _parse_status_entries(status_raw):
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
            "total": len(staged)
            + len(modified)
            + len(deleted)
            + len(renamed)
            + len(untracked),
        },
    }

    # 2. Diffs (for fingerprint + preview display) -- one call each
    h = hashlib.sha256()
    h.update(status_raw.encode("utf-8", "replace"))
    staged_diff = ""
    unstaged_diff = ""
    try:
        staged_diff = _stream_git_diff(root, ["diff", "--cached"], h, cap_bytes)
    except (OSError, subprocess.SubprocessError, GitError):
        staged_diff = ""
    try:
        unstaged_diff = _stream_git_diff(root, ["diff"], h, cap_bytes)
    except (OSError, subprocess.SubprocessError, GitError):
        unstaged_diff = ""

    unreadable: list[str] = []
    untracked_parts: list[str] = []
    total = 0
    for path in sorted(untracked):
        if total >= cap_total:
            untracked_parts.append("... untracked preview truncated ...")
            break
        p = Path(root) / path
        h.update(path.encode("utf-8", "replace"))
        h.update(b"\x00")
        try:
            data, truncated = _read_untracked(p, h, cap_bytes)
        except OSError:
            unreadable.append(path)
            continue
        if b"\x00" in data[:8192]:
            untracked_parts.append(
                f"diff --git a/{path} b/{path}\nnew file mode 100644\nBinary file\n"
            )
            total += 1
            continue
        lines, line_count = _preview_lines(data, min(cap_lines, cap_total - total))
        shown = lines[: min(cap_lines, cap_total - total)]
        omitted = line_count > len(shown) or truncated
        if omitted:
            shown.append(
                f"... ({cap_bytes} bytes shown, file larger -- truncated)"
                if truncated
                else f"... ({line_count - len(shown)} more lines not shown)"
            )
        body = "\n".join("+" + line for line in shown)
        untracked_parts.append(
            f"diff --git a/{path} b/{path}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
        total += len(shown)
        if omitted or total >= cap_total:
            untracked_parts.append("... untracked preview truncated ...")
            break

    if unreadable:
        return {
            "ok": False,
            "error": (
                f"Cannot preview: {len(unreadable)} untracked file(s) unreadable "
                f"({', '.join(unreadable[:5])}); refusing to mutate with "
                "incomplete evidence"
            ),
        }

    # 4. Assemble diff text
    diff_text = staged_diff + unstaged_diff
    untracked_text = "\n".join(untracked_parts)
    if untracked_text:
        diff_text = (
            (diff_text.rstrip("\n") + "\n" + untracked_text)
            if diff_text.strip()
            else untracked_text
        )

    return {
        "ok": True,
        "scope": scope,
        "fingerprint": h.hexdigest(),
        "diff": diff_text,
    }


def _current_state(root: str) -> dict:
    """scope + fingerprint in one call (the honest preview state).

    When untracked files are unreadable, returns a failure so the preview
    refuses instead of silently omitting evidence (CORE-003)."""
    scope_res = status_scope(root)
    if not scope_res.get("ok"):
        return scope_res
    fingerprint, unreadable = _tree_fingerprint(
        root, scope_res["scope"], scope_res["status_raw"]
    )
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


def _commit_paths(scope: dict) -> list[str]:
    """Paths Commit is authorised to stage, in preview order.

    Exactly the verified preview scope: staged, modified, deleted, rename
    destinations and untracked. Nothing discovered after authorisation is
    ever added (CORE-001).
    """
    paths: list[str] = []
    paths.extend(scope["staged"])
    paths.extend(scope["modified"])
    paths.extend(scope["deleted"])
    paths.extend(r["to"] for r in scope["renamed"])
    paths.extend(scope["untracked"])
    return _dedupe(paths)


def _revert_paths(scope: dict) -> list[str]:
    """Paths Revert is authorised to restore, in preview order.

    Both rename endpoints are restored so a staged rename is undone to the
    committed layout; the repository-wide ``git reset --hard`` is never used.
    """
    paths: list[str] = []
    paths.extend(scope["staged"])
    paths.extend(scope["modified"])
    paths.extend(scope["deleted"])
    for r in scope["renamed"]:
        if r.get("from"):
            paths.append(r["from"])
        paths.append(r["to"])
    return _dedupe(paths)


def _delete_paths(scope: dict) -> list[str]:
    """The exact untracked paths Delete is authorised to remove."""
    return _dedupe(list(scope["untracked"]))


def _authorized_paths(scope: dict) -> list[str]:
    """Every path any mutation may touch -- the identity snapshot domain."""
    paths: list[str] = []
    paths.extend(_commit_paths(scope))
    paths.extend(_revert_paths(scope))
    return _dedupe(paths)


def _dedupe(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


_ABSENT = "absent"

# ``None`` in the captured-content map means "authorized deletion": the path
# held ``absent`` at authorization and the commit must record its removal.
_CAPTURE_FILE_LIMIT = 16 * 1024 * 1024
_CAPTURE_TOTAL_LIMIT = 96 * 1024 * 1024

_STALE_MESSAGE = (
    "Working tree changed since the preview was shown; "
    "refresh and review the new scope before mutating."
)


def _stale_error() -> dict:
    """The one stale-preview refusal every mutation shares."""
    return {"ok": False, "error": _STALE_MESSAGE}


def _conflict_error(rel: str, preserved: str = "") -> dict:
    """A late write landed inside the destructive window and was preserved.

    Distinct from ``_stale_error`` because nothing was destroyed: the reviewed
    bytes still exist (at *preserved* when a second write already took the path).
    """
    error = (
        "Working tree changed since the preview was shown; the late write to "
        f"{rel!r} was preserved and no mutation was applied to it."
    )
    if preserved:
        error += f" The reviewed bytes are kept at {preserved!r}."
    return {"ok": False, "code": "PREVIEW_STALE", "error": error}


def _kept_note(error: dict, kept: list[str]) -> dict:
    """T-900: name every claim whose reviewed bytes stayed on disk.

    A refused release leaves the bytes in the scratch dir -- ``_Staging.cleanup``
    cannot rmdir it while they are there -- so that path is the only pointer to
    recoverable user work and a refusal that is not reported is a lost file.
    """
    if not kept:
        return error
    return {
        **error,
        "error": (
            f"{error.get('error', '')} Reviewed bytes kept at {', '.join(kept)}."
        ).lstrip(),
    }


def _identity_at(path: Path) -> str:
    """Content-bound identity of an explicit path (see ``_path_identity``)."""
    try:
        if path.is_dir():
            return "dir"
    except OSError:
        pass
    try:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                h.update(chunk)
        return "file:" + h.hexdigest()
    except FileNotFoundError:
        return _ABSENT
    except OSError as e:
        return f"unreadable:{type(e).__name__}"


def _path_identity(root: str, rel: str) -> str:
    """Content-bound identity of one path in the worktree.

    Binds the exact bytes a verified path held, so a late external write to
    that same path is detectable at the destructive boundary (CORE-001).
    Absence is a first-class identity: a path created after verification no
    longer matches the ``absent`` identity it was authorised with.
    """
    return _identity_at(Path(root) / rel)


def _capture_commit_content(
    root: str, paths: list[str], identities: dict[str, str]
) -> tuple[dict | None, dict[str, bytes | None] | None]:
    """Read the reviewed bytes ONCE and bind them to the commit.

    The returned map *is* the commit's content: ``bytes`` for an authorized
    file, ``None`` for an authorized deletion. Nothing later re-reads the
    worktree, so a write that lands after this boundary can neither enter the
    commit nor replace reviewed bytes inside it (CORE-001).

    A path whose reviewed bytes cannot be captured is refused rather than
    silently widening the authorization: no oversized file, no directory and no
    unreadable identity ever falls back to a later ``git add``.
    """
    contents: dict[str, bytes | None] = {}
    total = 0
    for rel in paths:
        expected = identities.get(rel)
        if expected == _ABSENT:
            contents[rel] = None
            continue
        if not expected or not expected.startswith("file:"):
            return {
                "ok": False,
                "code": "CAPTURE_UNSUPPORTED",
                "error": (
                    f"Commit cannot be snapshot-bound for {rel!r} (reviewed "
                    f"identity {expected!r}); refusing to widen authorization."
                ),
            }, None
        path = Path(root) / rel
        try:
            size = path.stat().st_size
        except OSError as e:
            return {"ok": False, "error": f"Cannot read {rel!r}: {e}"}, None
        if size > _CAPTURE_FILE_LIMIT or total + size > _CAPTURE_TOTAL_LIMIT:
            return {
                "ok": False,
                "code": "CAPTURE_TOO_LARGE",
                "error": (
                    f"Commit cannot be snapshot-bound for {rel!r}: {size} bytes "
                    "exceed the reviewed-content capture limit. Commit a smaller "
                    "scope; staging bytes no review saw is never the alternative."
                ),
            }, None
        try:
            data = path.read_bytes()
        except OSError as e:
            return {"ok": False, "error": f"Cannot read {rel!r}: {e}"}, None
        if "file:" + hashlib.sha256(data).hexdigest() != expected:
            return _stale_error(), None
        contents[rel] = data
        total += len(data)
    return None, contents


def _chunks(items: list, size: int = 200):
    """Bounded command lines: an unbounded argv is an OSError waiting to happen."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _mutation_seam(stage: str, paths: "Sequence[str]") -> None:
    """Deterministic barrier contract for the post-revalidation regressions.

    Called after ``_revalidate_authorized`` has returned success and before the
    irreversible work of a stage (``capture-complete`` for Commit, then
    ``before-claim`` and ``claimed`` for Revert and Delete). Production is a
    no-op; the CORE-001 regressions patch it to inject an external write inside
    the remaining window and assert the mutation is still snapshot-bound.
    """
    return None


def _git_dir(root: str) -> Path | None:
    r = _run_git(root, ["rev-parse", "--absolute-git-dir"])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip())


def _index_path(root: str, git_dir: Path) -> Path:
    r = _run_git(root, ["rev-parse", "--git-path", "index"])
    if r.returncode == 0 and r.stdout.strip():
        candidate = Path(r.stdout.strip())
        return candidate if candidate.is_absolute() else Path(root) / candidate
    return git_dir / "index"


class _Staging:
    """Per-mutation scratch area that ``git status`` never sees.

    Claims (``_claim_path``) and materialized head content live here. The area
    sits inside the git directory when that is on the same device as the
    mutation target, otherwise in a hidden sibling of the target itself:
    ``os.replace`` cannot cross devices, and a scratch file inside the worktree
    would perturb the very fingerprint the mutation is bound to.
    """

    def __init__(self, root: str, git_dir: Path | None):
        self.root = Path(root)
        self.token = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.counter = 0
        self.base: Path | None = None
        self.index_backup: Path | None = None
        self._local: dict[Path, Path] = {}
        self._scratch: list[Path] = []
        if git_dir is not None:
            self.index_backup = git_dir / f"saipenview-tx-{self.token}.index.before"
            try:
                base = git_dir / f"saipenview-tx-{self.token}"
                base.mkdir(parents=True, exist_ok=True)
                if os.stat(base).st_dev == os.stat(self.root).st_dev:
                    self.base = base
                else:
                    base.rmdir()
            except OSError:
                self.base = None

    def dir_for(self, target: Path) -> Path:
        """Scratch dir on the same device as *target*'s directory."""
        parent = target.parent
        probe = parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        if self.base is not None:
            try:
                if os.stat(self.base).st_dev == os.stat(probe).st_dev:
                    return self.base
            except OSError:
                pass
        existing = self._local.get(parent)
        if existing is not None:
            return existing
        local = probe / f".saipenview-tx-{self.token}"
        local.mkdir(parents=True, exist_ok=True)
        self._local[parent] = local
        return local

    def scratch(self, prefix: str) -> Path:
        path = (self.base or self.root) / f"{prefix}-{self.token}"
        path.mkdir(parents=True, exist_ok=True)
        self._scratch.append(path)
        return path

    def cleanup(self) -> None:
        """Drop scratch only: a preserved claim must survive to be reportable."""
        for path in self._scratch:
            shutil.rmtree(path, ignore_errors=True)
        if self.index_backup is not None:
            try:
                self.index_backup.unlink()
            except OSError:
                pass
        dirs = ([self.base] if self.base else []) + list(self._local.values())
        for path in dirs:
            try:
                path.rmdir()
            except OSError:
                pass


def _claim_path(root: str, rel: str, staging: _Staging) -> Path | None:
    """Atomically take whatever is at *rel* out of the worktree.

    ``os.replace`` resolves the name exactly once, so the claimed object is
    precisely what stood at the path at that instant. That rename is the
    compare-and-swap the destructive step is conditioned on, not a hash check
    followed by an unprotected read (CORE-001). ``None`` means the path held
    nothing.
    """
    target = Path(root) / rel
    if not os.path.lexists(target):
        return None
    scratch = staging.dir_for(target)
    staging.counter += 1
    claim = scratch / f"claim-{staging.counter:04d}-{target.name}"
    os.replace(target, claim)
    return claim


def _release_claim(claim: Path, target: Path) -> bool:
    """Put claimed bytes back without clobbering a newer write."""
    try:
        if os.path.lexists(target):
            return False
        os.makedirs(target.parent, exist_ok=True)
        os.replace(claim, target)
        return True
    except OSError:
        return False


def _discard_claim(claim: Path) -> None:
    if claim.is_symlink() or not claim.is_dir():
        try:
            claim.unlink()
        except OSError:
            pass
        return
    shutil.rmtree(claim, ignore_errors=True)


def _release_claims(root: str, claims: dict[str, Path | None]) -> list[str]:
    """Put every claim back; return the locations of any that could not be."""
    preserved: list[str] = []
    for rel, claim in claims.items():
        if claim is None:
            continue
        if not _release_claim(claim, Path(root) / rel):
            preserved.append(str(claim))
    return preserved


def _claim_all(
    root: str, paths: list[str], identities: dict[str, str], staging: _Staging
) -> tuple[dict[str, Path | None], dict | None]:
    """Claim and verify every authorized path, or release all and fail closed.

    The whole claim set is verified before any destructive step runs, so a
    conflict leaves the tree exactly as the late writer left it.
    """
    claims: dict[str, Path | None] = {}
    for rel in paths:
        expected = identities.get(rel)
        try:
            claim = _claim_path(root, rel, staging)
        except OSError as e:
            kept = _release_claims(root, claims)
            return {}, _kept_note(
                {"ok": False, "error": f"Cannot claim {rel!r}: {e}"}, kept
            )
        if claim is None:
            if expected != _ABSENT:
                kept = _release_claims(root, claims)
                return {}, _kept_note(_stale_error(), kept)
            claims[rel] = None
            continue
        if _identity_at(claim) != expected:
            restored = _release_claim(claim, Path(root) / rel)
            kept = _release_claims(root, claims)
            # T-900: `kept` holds the OTHER paths, so naming kept[0] pointed at
            # the wrong location and dropped this claim's own bytes whenever
            # the restore succeeded. Name every path that survived.
            preserved = ([] if restored else [str(claim)]) + kept
            return {}, _conflict_error(rel, ", ".join(preserved))
        claims[rel] = claim
    return claims, None


def _install_exclusive(src: Path, target: Path, mode: str) -> bool:
    """Write *src* at *target* only when nothing else took the path first.

    ``O_EXCL`` makes the install the second half of the compare-and-swap: a file
    that appeared after the claim is never overwritten.
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o644,
        )
    except OSError:
        return False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(src.read_bytes())
    except OSError:
        try:
            target.unlink()
        except OSError:
            pass
        return False
    if os.name != "nt":
        try:
            os.chmod(target, 0o755 if mode == "100755" else 0o644)
        except OSError:
            pass
    return True


def _set_index_entries(
    root: str, adds: list[tuple[str, str, str]], removals: list[str]
) -> dict | None:
    """Point index entries at explicit blobs -- index-only, never the worktree."""
    for group in _chunks(adds):
        args = ["update-index", "--add"]
        for mode, sha, rel in group:
            args += ["--cacheinfo", f"{mode},{sha},{rel}"]
        r = _run_git(root, args)
        if r.returncode != 0:
            return {
                "ok": False,
                "error": f"git update-index failed: {(r.stderr or '').strip()}",
            }
    for group in _chunks(removals):
        r = _run_git(root, ["update-index", "--force-remove", "--", *group])
        if r.returncode != 0:
            return {
                "ok": False,
                "error": f"git update-index failed: {(r.stderr or '').strip()}",
            }
    return None


def _record_entries(
    root: str, args: list[str], sha_index: int = 1
) -> dict[str, tuple[str, str]]:
    """Parse ``ls-files -s -z`` / ``ls-tree -z`` records into (mode, sha).

    The two commands order their fields differently -- ``ls-files`` is
    ``<mode> <sha> <stage>`` and ``ls-tree`` is ``<mode> <type> <sha>`` -- so the
    caller states where the object id is instead of this guessing from ``parts[1]``
    (which silently produced ``blob`` as a sha).
    """
    entries: dict[str, tuple[str, str]] = {}
    r = _run_git(root, args)
    if r.returncode != 0:
        raise GitError((r.stderr or "git listing failed").strip())
    for record in r.stdout.split("\x00"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        parts = meta.split()
        if not path or len(parts) < 3:
            continue
        entries[path] = (parts[0], parts[sha_index])
    return entries


def _tree_entries(root: str, paths: list[str]) -> dict[str, tuple[str, str]]:
    """mode/sha of index entries for *paths*, in bounded batches."""
    entries: dict[str, tuple[str, str]] = {}
    for group in _chunks(_dedupe(paths)):
        entries.update(_record_entries(root, ["ls-files", "-s", "-z", "--", *group]))
    return entries


def _head_entries(root: str, paths: list[str]) -> dict[str, tuple[str, str]]:
    """mode/sha of HEAD entries for *paths* (paths absent from HEAD are omitted)."""
    entries: dict[str, tuple[str, str]] = {}
    for group in _chunks(_dedupe(paths)):
        entries.update(
            _record_entries(root, ["ls-tree", "-z", "HEAD", "--", *group], 2)
        )
    return entries


def _staged_paths(root: str) -> list[str] | None:
    r = _run_git(root, ["diff", "--cached", "--name-only", "-z", "--no-renames"])
    if r.returncode != 0:
        # T-899: an empty list here reads as "nothing is staged outside the
        # reviewed scope", so a git failure used to pass the guard vacuously.
        # None means UNKNOWN, and the caller refuses rather than committing.
        return None
    return [p for p in r.stdout.split("\x00") if p]


def _worktree_mode(path: Path) -> str:
    if os.name != "nt" and os.access(path, os.X_OK):
        return "100755"
    return "100644"


def _restore_index(index_path: Path, backup: Path | None) -> None:
    """Undo this mutation's index writes after a refusal."""
    try:
        if backup is not None and backup.is_file():
            shutil.copy2(backup, index_path)
    except OSError:
        pass
def _authorize_and_snapshot(root: str, expected: str | None) -> tuple[dict | None, dict | None]:
    """Verify the preview fingerprint and bind the verified scope.

    Returns ``(error, None)`` when the fingerprint is missing, the tree cannot
    be read, or the tree moved since the preview was shown; otherwise
    ``(None, snapshot)`` where ``snapshot`` holds the verified scope and a
    per-path content identity captured from that same observation.

    This replaces the old ``_verify_fingerprint`` early-precondition pattern:
    the verified scope is the mutation target, never a fresh ``status_scope``.
    """
    req = _require_fingerprint(expected)
    if req:
        return req, None
    current = _current_state(root)
    if not current.get("ok"):
        return current, None
    if current["fingerprint"] != expected:
        return {
            "ok": False,
            "error": (
                "Working tree changed since the preview was shown; "
                "refresh and review the new scope before mutating."
            ),
        }, None
    scope = current["scope"]
    identities = {rel: _path_identity(root, rel) for rel in _authorized_paths(scope)}
    error, contents = _capture_commit_content(
        root, _commit_paths(scope), identities
    )
    if error:
        return error, None
    return None, {"scope": scope, "identities": identities, "contents": contents}


def _revalidate_authorized(root: str, snapshot: dict, paths: list[str]) -> dict | None:
    """Re-check authorized path identities at the destructive boundary.

    Only paths belonging to the verified scope are re-read, so an unrelated
    late change cannot abort an authorized mutation and a late change to an
    authorized path fails closed as a stale preview (CORE-001).
    """
    identities = snapshot["identities"]
    for rel in paths:
        if _path_identity(root, rel) != identities.get(rel):
            return {
                "ok": False,
                "error": (
                    "Working tree changed since the preview was shown; "
                    "refresh and review the new scope before mutating."
                ),
            }
    return None


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


def get_working_diff(
    root: str, untracked_cap_lines: int = 200, untracked_cap_total: int = 2000
) -> dict:
    """Full preview: tracked diffs plus untracked-file content, plus scope.

    PERF-008: uses _state_with_preview for a single-pass that runs each
    git subprocess exactly once, reusing outputs for scope, fingerprint,
    and preview rendering.
    """
    if not is_git_repo(root):
        return {"ok": False, "error": "Not a git repository"}
    return _state_with_preview(root, untracked_cap_lines, untracked_cap_total)


def _commit_index_paths(scope: dict) -> list[str]:
    """Every path whose index entry the snapshot-bound commit may set.

    The commit writes captured content into the index and then commits that
    index, so a staged rename's source deletion -- an index change the reviewer
    already saw as part of ``renamed`` -- is included instead of leaving the
    rename half-applied in the index.
    """
    paths = _commit_paths(scope)
    paths.extend(r["from"] for r in scope["renamed"] if r.get("from"))
    return _dedupe(paths)


def _snapshot_bound_commit(
    root: str,
    message: str,
    contents: dict[str, bytes | None],
    index_paths: list[str],
) -> dict:
    """Commit exactly the reviewed bytes, never re-reading the worktree.

    Blobs are written from the captured snapshot, the index is pointed at those
    blob ids, and the commit is taken from that index alone. A write landing
    after the capture boundary therefore cannot enter the commit, cannot replace
    reviewed bytes inside it, and is left standing in the worktree.
    """
    git_dir = _git_dir(root)
    if git_dir is None:
        return {"ok": False, "error": "Not a git repository"}
    staging = _Staging(root, git_dir)
    index_path = _index_path(root, git_dir)
    try:
        if index_path.is_file():
            shutil.copy2(index_path, staging.index_backup)
        blob_dir = staging.scratch("blobs")
        entries = _tree_entries(root, index_paths)
        blobs: dict[str, str] = {}
        for rel, data in contents.items():
            if data is None:
                continue
            tmp = blob_dir / f"blob-{len(blobs):05d}"
            tmp.write_bytes(data)
            r = _run_git(root, ["hash-object", "-w", "--path", rel, "--", str(tmp)])
            if r.returncode != 0:
                return {
                    "ok": False,
                    "error": f"git hash-object failed: {(r.stderr or '').strip()}",
                }
            blobs[rel] = r.stdout.strip()
        adds = [
            (
                entries.get(rel, ("", ""))[0] or _worktree_mode(Path(root) / rel),
                sha,
                rel,
            )
            for rel, sha in blobs.items()
        ]
        removals = [rel for rel, data in contents.items() if data is None]
        error = _set_index_entries(root, adds, removals)
        if error:
            _restore_index(index_path, staging.index_backup)
            return error
        # The index may carry nothing outside the reviewed scope: the commit
        # below is index-only, so an unknown staged entry would widen what the
        # user authorized.
        authorized = set(index_paths)
        staged = _staged_paths(root)
        if staged is None:
            _restore_index(index_path, staging.index_backup)
            return {
                "ok": False,
                "code": "SCOPE_UNVERIFIABLE",
                "error": (
                    "git could not list the staged paths, so the index cannot be "
                    "checked against the reviewed scope; nothing was committed."
                ),
            }
        outside = sorted({p for p in staged if p not in authorized})
        if outside:
            _restore_index(index_path, staging.index_backup)
            return {
                "ok": False,
                "code": "SCOPE_CONFLICT",
                "error": (
                    "Index holds staged changes outside the reviewed scope "
                    f"({', '.join(outside[:5])}); refresh and review the scope again."
                ),
            }
        commit = _run_git(root, ["commit", "-m", message])
        if commit.returncode != 0:
            if "nothing to commit" in (commit.stdout + commit.stderr).lower():
                # T-892: nothing was committed, so nothing should be left
                # staged either -- the index goes back to what it was.
                _restore_index(index_path, staging.index_backup)
                return {"ok": True}
            # T-892: a rejected commit (pre-commit hook, signing key, unset
            # identity) must leave the index exactly as it was. Without this
            # the rewritten entries survive AND staging.cleanup() below
            # unlinks index_backup, so the original index is unrecoverable.
            _restore_index(index_path, staging.index_backup)
            return {
                "ok": False,
                "error": f"Git command failed: {(commit.stderr or '').strip()}",
            }
        return {"ok": True}
    finally:
        staging.cleanup()


def commit_agent_work(root: str, message: str, fingerprint: str | None = None) -> dict:
    """Stage exactly the verified preview scope and commit it.

    The mutation scope is the scope that was successfully verified against
    ``fingerprint`` -- it is never recomputed from a later ``status_scope``.
    The bytes that enter the commit are the bytes captured at authorization:
    ``git add`` never re-reads the worktree, so there is no check-then-act
    window between validation and the commit (CORE-001). A late external write
    to an authorized path is refused as a stale preview when it lands before
    the capture, and kept out of the commit while still standing in the
    worktree when it lands after; a path that appeared after the preview is not
    part of the scope and cannot enter the commit (CORE-003).

    Requires a non-empty fingerprint: the caller must have shown the user the
    exact scope via get_working_diff() (CORE-003)."""
    if not message or not message.strip():
        return {"ok": False, "error": "Commit message is empty"}
    error, snapshot = _authorize_and_snapshot(root, fingerprint)
    if error:
        return error
    paths = _commit_paths(snapshot["scope"])
    index_paths = _commit_index_paths(snapshot["scope"])
    mismatch = _revalidate_authorized(root, snapshot, index_paths)
    if mismatch:
        return mismatch
    if not paths:
        # Nothing in the verified scope: never run a bare ``git commit``,
        # which would sweep any entry of the index into the commit.
        return {"ok": False, "error": "Nothing to commit"}
    contents = snapshot["contents"]
    uncaptured = [rel for rel in paths if rel not in contents]
    if uncaptured:
        return {
            "ok": False,
            "code": "CAPTURE_UNSUPPORTED",
            "error": (
                "Commit cannot be snapshot-bound for "
                f"{', '.join(uncaptured[:5])}; refresh and review the scope again."
            ),
        }
    _mutation_seam("capture-complete", tuple(paths))
    try:
        return _snapshot_bound_commit(root, message, contents, index_paths)
    except (OSError, subprocess.SubprocessError, GitError) as e:
        return {"ok": False, "error": str(e)}


def _prune_empty_parents(root: str, paths: list[str]) -> None:
    """Remove the directories this deletion emptied, never a tracked one.

    ``git clean -fd`` used to do this as a side effect. A directory that is not
    empty, or that holds tracked content, is left alone -- so a directory a late
    writer filled is never removed.
    """
    top = Path(root).resolve()
    for rel in paths:
        parent = (Path(root) / rel).parent
        while parent != top and top in parent.parents:
            try:
                if any(parent.iterdir()):
                    break
            except OSError:
                break
            r = _run_git(root, ["ls-files", "--", str(parent)])
            if r.returncode != 0 or r.stdout.strip():
                break
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def revert_agent_work(root: str, fingerprint: str | None = None) -> dict:
    """Restore only the verified tracked/staged/deleted paths.

    Replaces the repository-wide ``git reset --hard``: only the paths in the
    verified preview scope are restored from ``HEAD``. Untracked files are
    deliberately NOT removed -- deleting them is the separate
    ``delete_untracked_files`` operation (T-162).

    Every authorized path is claimed out of the worktree with a single atomic
    rename and then verified against the reviewed content identity, so an edit
    that lands after revalidation is put back instead of being destroyed, and
    the ``HEAD`` content is installed with ``O_EXCL`` so a write arriving during
    the restore is preserved too (CORE-001). The index is repointed with
    explicit blob ids, never by re-reading the worktree.

    Requires a non-empty fingerprint (CORE-003)."""
    error, snapshot = _authorize_and_snapshot(root, fingerprint)
    if error:
        return error
    paths = _revert_paths(snapshot["scope"])
    mismatch = _revalidate_authorized(root, snapshot, paths)
    if mismatch:
        return mismatch
    if not paths:
        return {"ok": True}
    git_dir = _git_dir(root)
    staging = _Staging(root, git_dir)
    index_path = _index_path(root, git_dir)
    claims: dict[str, Path | None] = {}
    try:
        # Revert repoints index entries at the HEAD blob ids, so a failure
        # after that write must put the index back exactly as it was: a
        # half-reverted index silently unstages the user's own work while the
        # returned error names a different cause.
        if index_path.is_file():
            shutil.copy2(index_path, staging.index_backup)
        head = _head_entries(root, paths)
        _mutation_seam("before-claim", tuple(paths))
        claims, conflict = _claim_all(root, paths, snapshot["identities"], staging)
        if conflict:
            return conflict

        def abort(error: dict) -> dict:
            _restore_index(index_path, staging.index_backup)
            return _kept_note(error, _release_claims(root, claims))

        _mutation_seam("claimed", tuple(paths))
        absent = [rel for rel in paths if rel not in head]
        present = [rel for rel in paths if rel in head]
        if absent:
            error = _set_index_entries(root, [], absent)
            if error:
                return abort(error)
        if present:
            error = _set_index_entries(
                root, [(head[rel][0], head[rel][1], rel) for rel in present], []
            )
            if error:
                return abort(error)
            material = staging.scratch("head")
            for group in _chunks(present):
                r = _run_git(
                    root,
                    [
                        "checkout-index",
                        "--force",
                        "--prefix",
                        str(material) + os.sep,
                        "--",
                        *group,
                    ],
                )
                if r.returncode != 0:
                    return abort(
                        {
                            "ok": False,
                            "error": (
                                "git checkout-index failed: "
                                f"{(r.stderr or '').strip()}"
                            ),
                        }
                    )
            for rel in present:
                source = material / rel
                if not source.is_file():
                    return abort(
                        {
                            "ok": False,
                            "error": (
                                f"Cannot restore {rel!r}: HEAD content was not "
                                "materialized"
                            ),
                        }
                    )
                if not _install_exclusive(source, Path(root) / rel, head[rel][0]):
                    # T-891: this branch skipped abort(), so the index kept the
                    # HEAD repointing _set_index_entries already made while the
                    # worktree stayed unreverted. abort() is also what names the
                    # claims whose bytes had to be preserved.
                    return abort(_conflict_error(rel, ""))
        for claim in claims.values():
            if claim is not None:
                _discard_claim(claim)
        return {"ok": True}
    except (OSError, subprocess.SubprocessError, GitError) as e:
        _restore_index(index_path, staging.index_backup)
        kept = _release_claims(root, claims)
        return _kept_note({"ok": False, "error": str(e)}, kept)
    finally:
        staging.cleanup()


def delete_untracked_files(root: str, fingerprint: str | None = None) -> dict:
    """Delete exactly the verified untracked files and directories.

    Replaces the repository-wide ``git clean -fd``: only the untracked paths
    present in the verified preview are removed, each claimed out of the
    worktree with one atomic rename before its reviewed content identity is
    checked. No ``git clean`` runs at all -- a file that appeared after
    verification is never swept in, and a target that was changed or replaced
    after the last check is put back and the operation fails closed. Ignored
    files are never touched (CORE-001).

    Requires a non-empty fingerprint (CORE-003)."""
    error, snapshot = _authorize_and_snapshot(root, fingerprint)
    if error:
        return error
    paths = _delete_paths(snapshot["scope"])
    if not paths:
        return {"ok": True}
    mismatch = _revalidate_authorized(root, snapshot, paths)
    if mismatch:
        return mismatch
    staging = _Staging(root, _git_dir(root))
    claims: dict[str, Path | None] = {}
    try:
        _mutation_seam("before-claim", tuple(paths))
        claims, conflict = _claim_all(root, paths, snapshot["identities"], staging)
        if conflict:
            return conflict
        _mutation_seam("claimed", tuple(paths))
        for claim in claims.values():
            if claim is not None:
                _discard_claim(claim)
        _prune_empty_parents(root, paths)
        return {"ok": True}
    except (OSError, subprocess.SubprocessError, GitError) as e:
        kept = _release_claims(root, claims)
        return _kept_note({"ok": False, "error": str(e)}, kept)
    finally:
        staging.cleanup()
