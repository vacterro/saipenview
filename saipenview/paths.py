"""Canonical path layer (T-138).

One place that turns a Windows path into its one true spelling, so the rest
of the app can compare paths without re-deriving the rules at every call
site. The canonical form is: absolute, case-normalised, symlink-resolved,
collapsed (no `.`/`..`), with a single trailing separator on drive roots and
nowhere else.

Call sites that write or compare paths MUST go through here instead of
hand-rolling `str(Path(x).resolve())` -- the whole point is that a path
stored as `C:\foo` and one stored as `c:/foo/` compare equal.
"""

from __future__ import annotations

import os
from pathlib import Path

_ALLOWED_EXTENSIONS = frozenset({".md", ".json"})


def canonical(path: str | Path) -> str:
    """Return the canonical form of *path*.

    normcase (Windows: lower + backslashes) -> resolve (absolute, symlinks
    resolved, `.`/`..` collapsed) -> normpath (clean up any trailing debris)
    -> drive-root trailing-slash rule.
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        # resolve() can fail on a dead symlink or an inaccessible parent; fall
        # back to the purely lexical form so a missing drive still gets a
        # canonical string instead of an exception from the path layer.
        resolved = Path(os.path.normpath(os.path.abspath(os.fspath(path))))
    text = os.path.normpath(os.path.normcase(str(resolved)))
    if _is_drive_root(text):
        return text[:2] + os.sep
    return text


def canonical_key(path: str | Path) -> str:
    """Canonical form with the drive-root separator dropped, so a drive root
    and a path under it are different keys but case/slash variants are one."""
    c = canonical(path)
    if _is_drive_root(c):
        return c
    return c.rstrip("\\/") or c


def dedupe(paths: list[str] | None) -> list[str]:
    """Deduplicate a list of paths by canonical key, preserving first-seen order."""
    if not paths:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        key = canonical_key(p)
        if key not in seen:
            seen.add(key)
            out.append(canonical(p))
    return out


def _is_drive_root(p: str) -> bool:
    return len(p) == 2 and p[1] == ":" or len(p) == 3 and p[1] == ":" and p[2] in "/\\"


def is_inside(root: str | Path, path: str | Path) -> bool:
    """True when *path* is *root* itself or lives under it (no parent-climb escape).

    Both sides are canonicalised before the prefix test, so a path like
    ``C:/foo/../bar`` resolves to ``C:/bar`` and the containment answer is
    about the real target, not the spelling that arrived.
    """
    r = canonical(root)
    p = canonical(path)
    if _is_drive_root(r):
        return p.upper().startswith(r.upper())
    return p.upper() == r.upper() or p.upper().startswith(r.upper() + os.sep)


def validate_file_path(
    path: str | Path,
    known_roots: list[str | Path],
    allowed_extensions: frozenset[str] | None = None,
) -> tuple[bool, str]:
    """Frontend file-viewer boundary (T-138 layer 3).

    Returns ``(ok, reason)``. Rejects when the canonical path sits outside
    every known root, or its extension is not in the whitelist. Empty
    ``known_roots`` rejects everything -- fail closed, never open.
    """
    allowed = (
        allowed_extensions if allowed_extensions is not None else _ALLOWED_EXTENSIONS
    )
    if not known_roots:
        return False, "no known roots configured"
    ext = os.path.splitext(os.fspath(path))[1].lower()
    if ext not in allowed:
        return (
            False,
            f"extension {ext or '(none)'!r} not allowed (only {sorted(allowed)})",
        )
    for root in known_roots:
        if is_inside(root, path):
            return True, ""
    return False, "path escapes every known project root"
