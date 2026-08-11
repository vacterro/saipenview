"""The collect gate: one adapter for SAIPEN package validity.

Collect consumes a subSaipen's OUTBOX entry into the main project. Before ANY
main-project write the entry must pass the CURRENT package contract -- the
same gate tools/validate.py enforces under `--gate collect:<producer>`:

* ``status`` is EXACTLY ``ready`` (never a substring search, never "not
  quite"); draft/blocked/stale is a controlled refusal, reviewed is an
  idempotent no-op, malformed/unknown is a refusal.
* every ``PACKAGE_HANDOFF_FIELDS`` field plus ``summary``/``critical`` is
  present with usable content;
* ``producer`` names the requested sub;
* ``source_head`` equals the current source identity's HEAD and
  ``source_tree_fingerprint`` equals the current tree fingerprint -- a stale
  or dirty tree (same HEAD or not) is refused;
* ``role_revision`` equals the current project-local charter's derived
  revision;
* the source identity itself FAILS CLOSED: if it cannot be computed (no git,
  unmerged inputs, tree changing under the read), no package passes.

The source-identity and role-revision computations are direct ports of the
canonical ``tools/freshness.py`` primitives so the viewer does not maintain a
second partial idea of "what is current". tests/test_collect_gate.py asserts
byte-equality against the canonical implementation on the same trees.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from saipenview import protocol


class FreshnessError(RuntimeError):
    """Package freshness evidence could not be computed without omitting input."""


@dataclass(frozen=True)
class SourceIdentity:
    source_head: str
    source_tree_fingerprint: str
    discovery_model: str


# --- source identity (ported from tools/freshness.py, git-delta-v1) --------

_NO_GIT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".freebuff",
        ".claude",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
    }
)
_NO_GIT_EXCLUDED_ROOT_FILES = frozenset({"nul"})

_SOURCE_MAGIC = b"saipen-source-fingerprint-v1\0"
_ROLE_MAGIC = b"saipen-role-revision-v1\0"
_GENERIC_ROLE_MAGIC = b"saipen-generic-role-revision-v1\0"


@dataclass(frozen=True)
class _Record:
    kind: bytes
    path: bytes
    mode: int
    content: bytes


def _run_git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(root), *args],
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FreshnessError(f"Git discovery failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise FreshnessError(
            f"git {' '.join(args)} failed with exit {result.returncode}"
            + (f": {detail}" if detail else "")
        )
    return result.stdout


def _is_saipen_path(path: bytes) -> bool:
    return path == b".saipen" or path.startswith(b".saipen/")


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        info = path.lstat()
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & 0x400)


def _frame(record: _Record) -> bytes:
    if len(record.kind) != 1:
        raise FreshnessError("fingerprint record type must be exactly one byte")
    return b"".join(
        (
            record.kind,
            struct.pack(">Q", len(record.path)),
            record.path,
            struct.pack(">I", record.mode),
            struct.pack(">Q", len(record.content)),
            record.content,
        )
    )


def _digest(model: str, records) -> str:
    model_bytes = model.encode("ascii")
    h = hashlib.sha256()
    h.update(_SOURCE_MAGIC)
    h.update(struct.pack(">Q", len(model_bytes)))
    h.update(model_bytes)
    for record in sorted(records, key=lambda item: item.path):
        h.update(_frame(record))
    return f"{model}:{h.hexdigest()}"


def _path_from_git(root: Path, raw_path: bytes) -> Path:
    if not raw_path or raw_path.startswith(b"/") or b"\0" in raw_path:
        raise FreshnessError(f"Git returned an invalid path: {raw_path!r}")
    if any(part in (b"", b".", b"..") for part in raw_path.split(b"/")):
        raise FreshnessError(f"Git returned a non-canonical path: {raw_path!r}")
    rel = os.fsdecode(raw_path)
    candidate = root.joinpath(*rel.split("/"))
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FreshnessError(f"Git path escapes project root: {rel!r}") from exc
    return candidate


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        before = path.lstat()
        fd = os.open(path, flags)
    except OSError as exc:
        raise FreshnessError(
            f"cannot stat/read fingerprint input {path}: {exc}"
        ) from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise FreshnessError(
                f"fingerprint input changed type while opening: {path}"
            )
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise FreshnessError(f"fingerprint input raced while opening: {path}")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if (opened.st_size, opened.st_mtime_ns, opened.st_mode) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        ):
            raise FreshnessError(f"fingerprint input changed while reading: {path}")
        return b"".join(chunks)
    except OSError as exc:
        raise FreshnessError(f"cannot read fingerprint input {path}: {exc}") from exc
    finally:
        os.close(fd)


def _read_symlink(path: Path) -> bytes:
    try:
        before = path.lstat()
        target = os.readlink(path)
        repeated = os.readlink(path)
        after = path.lstat()
    except OSError as exc:
        raise FreshnessError(f"cannot read fingerprint symlink {path}: {exc}") from exc
    if target != repeated or (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_mode, after.st_mtime_ns):
        raise FreshnessError(f"fingerprint symlink changed while reading: {path}")
    return os.fsencode(target)


def _record_current(root: Path, raw_path: bytes, declared_mode: int | None) -> _Record:
    path = _path_from_git(root, raw_path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise FreshnessError(f"cannot stat fingerprint input {path}: {exc}") from exc

    if stat.S_ISLNK(info.st_mode):
        mode = 0o120000
        kind = b"L"
        content = _read_symlink(path)
    elif stat.S_ISREG(info.st_mode):
        mode = 0o100755 if info.st_mode & 0o111 else 0o100644
        if declared_mode in (0o100644, 0o100755):
            mode = declared_mode
        kind = b"F"
        content = _read_regular(path)
    else:
        raise FreshnessError(
            f"unsupported fingerprint input type at {path}; only regular files "
            "and symlinks are supported"
        )

    if declared_mode is not None and declared_mode not in (mode, 0):
        raise FreshnessError(
            f"Git mode {declared_mode:o} disagrees with filesystem type at {path}"
        )
    return _Record(kind, raw_path, mode, content)


def _git_delta_listing(root: Path) -> tuple[bytes, bytes]:
    raw = _run_git(
        root,
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--ignore-submodules=none",
        "HEAD",
        "--",
    )
    untracked = _run_git(root, "ls-files", "-z", "--others", "--exclude-standard", "--")
    return raw, untracked


def _parse_git_delta(root: Path, raw: bytes, untracked: bytes) -> list[_Record]:
    records: dict[bytes, _Record] = {}
    fields = raw.split(b"\0")
    index = 0
    while index < len(fields) and fields[index]:
        header = fields[index]
        index += 1
        if index >= len(fields) or not fields[index]:
            raise FreshnessError("Git returned a truncated --raw delta record")
        raw_path = fields[index]
        index += 1
        if _is_saipen_path(raw_path):
            continue
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(b":"):
            raise FreshnessError(
                f"Git returned an unparseable --raw record: {header!r}"
            )
        try:
            old_mode = int(parts[0][1:], 8)
            new_mode = int(parts[1], 8)
        except ValueError as exc:
            raise FreshnessError(f"Git returned an invalid mode: {header!r}") from exc
        status_code = parts[4][:1]
        if status_code == b"U":
            raise FreshnessError(
                "unmerged fingerprint input cannot become ready: "
                + os.fsdecode(raw_path)
            )
        if status_code not in (b"A", b"D", b"M", b"T"):
            raise FreshnessError(
                f"unsupported Git delta status {parts[4]!r}: {os.fsdecode(raw_path)}"
            )
        if status_code == b"D" or new_mode == 0:
            records[raw_path] = _Record(b"D", raw_path, old_mode, b"")
            continue
        if new_mode == 0o160000:
            raise FreshnessError(
                f"changed Git submodule is unsupported: {os.fsdecode(raw_path)}"
            )
        records[raw_path] = _record_current(root, raw_path, new_mode)

    for raw_path in untracked.split(b"\0"):
        if not raw_path or _is_saipen_path(raw_path):
            continue
        records[raw_path] = _record_current(root, raw_path, None)
    return list(records.values())


def _git_identity(root: Path) -> SourceIdentity:
    head = _run_git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    before = _git_delta_listing(root)
    first_records = _parse_git_delta(root, *before)
    middle = _git_delta_listing(root)
    second_records = _parse_git_delta(root, *middle)
    after = _git_delta_listing(root)
    third_records = _parse_git_delta(root, *after)
    final = _git_delta_listing(root)
    final_head = _run_git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if (
        head != final_head
        or not (before == middle == after == final)
        or not (first_records == second_records == third_records)
    ):
        raise FreshnessError(
            "source tree or HEAD changed while fingerprint inputs were being read"
        )
    model = "git-delta-v1"
    return SourceIdentity(head, _digest(model, third_records), model)


def _walk_no_git(root: Path) -> list[_Record]:
    records: list[_Record] = []

    def visit(directory: Path, rel_parts: tuple[str, ...]) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: os.fsencode(entry.name)
            )
        except OSError as exc:
            raise FreshnessError(
                f"cannot enumerate fingerprint directory {directory}: {exc}"
            ) from exc
        for entry in entries:
            next_parts = (*rel_parts, entry.name)
            raw_path = b"/".join(os.fsencode(part) for part in next_parts)
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise FreshnessError(
                    f"cannot stat fingerprint input {path}: {exc}"
                ) from exc
            if stat.S_ISDIR(info.st_mode) and (
                (not rel_parts and entry.name == ".saipen")
                or entry.name in _NO_GIT_EXCLUDED_DIRS
            ):
                continue
            if not rel_parts and entry.name in _NO_GIT_EXCLUDED_ROOT_FILES:
                continue
            if stat.S_ISLNK(info.st_mode) or _is_reparse_point(path):
                records.append(_Record(b"L", raw_path, 0o120000, _read_symlink(path)))
            elif stat.S_ISDIR(info.st_mode):
                visit(path, next_parts)
            elif stat.S_ISREG(info.st_mode):
                mode = 0o100755 if info.st_mode & 0o111 else 0o100644
                records.append(_Record(b"F", raw_path, mode, _read_regular(path)))
            else:
                raise FreshnessError(
                    f"unsupported fingerprint input type at {path}; only regular "
                    "files, directories, and symlinks are supported"
                )

    visit(root, ())
    return records


def compute_source_identity(project_root: Path | str) -> SourceIdentity:
    """The current source identity of a project root, byte-identical to the
    canonical tools/freshness.py computation. FAILS CLOSED: any input that
    cannot be discovered, stat'ed, classified or read is a FreshnessError, and
    no package may pass with unknown input."""
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise FreshnessError(f"project root is not a directory: {root}")
    git_marker = root / ".git"
    try:
        probe = subprocess.run(
            ["git", "-C", os.fspath(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if git_marker.exists():
            raise FreshnessError(f"Git repository discovery failed: {exc}") from exc
        probe = None
    if probe is not None and probe.returncode == 0 and probe.stdout.strip() == b"true":
        try:
            top = _run_git(root, "rev-parse", "--show-toplevel")
            git_root = Path(os.fsdecode(top.strip())).resolve()
        except (FreshnessError, OSError) as exc:
            raise FreshnessError(
                f"Git repository root discovery failed: {exc}"
            ) from exc
        if git_root == root:
            return _git_identity(root)
    elif git_marker.exists():
        detail = ""
        if probe is not None:
            detail = probe.stderr.decode("utf-8", "replace").strip()
        raise FreshnessError(
            "Git metadata exists but work-tree discovery failed"
            + (f": {detail}" if detail else "")
        )
    model = "no-git-tree-v1"
    first_records = _walk_no_git(root)
    second_records = _walk_no_git(root)
    if first_records != second_records:
        raise FreshnessError(
            "no-Git source tree changed while fingerprint inputs were being read"
        )
    return SourceIdentity("no-git", _digest(model, second_records), model)


def compute_role_revision(charter_path: Path | str) -> str:
    path = Path(charter_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FreshnessError(f"cannot read role charter {path}: {exc}") from exc
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = raw.splitlines(keepends=True)
    in_yaml = False
    removed = 0
    body: list[bytes] = []
    for line in lines:
        stripped = line.strip()
        if stripped == b"```yaml" and not in_yaml:
            in_yaml = True
            body.append(line)
            continue
        if stripped == b"```" and in_yaml:
            in_yaml = False
            body.append(line)
            continue
        if in_yaml and line.lstrip().startswith(b"role_revision:"):
            removed += 1
            continue
        body.append(line)
    if removed != 1:
        raise FreshnessError(
            f"role charter {path} must contain exactly one role_revision field; found {removed}"
        )
    canonical = b"".join(body)
    h = hashlib.sha256()
    h.update(_ROLE_MAGIC)
    h.update(struct.pack(">Q", len(canonical)))
    h.update(canonical)
    return "sha256:" + h.hexdigest()


def compute_generic_role_revision(protocol_path: Path | str) -> str:
    path = Path(protocol_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FreshnessError(
            f"cannot read generic role protocol {path}: {exc}"
        ) from exc
    canonical = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    h = hashlib.sha256()
    h.update(_GENERIC_ROLE_MAGIC)
    h.update(struct.pack(">Q", len(canonical)))
    h.update(canonical)
    return "sha256:" + h.hexdigest()


# --- the package gate -------------------------------------------------------

# Charter metadata: the closed set of consumption authorities (PROTOCOL.md
# § 3.1). `automatic` allows autonomous intake; `core-review` creates normal
# Core work and NEVER applies a payload directly; `explicit` refuses every
# autonomous sweep and requires an explicit named collect authorization.
COLLECT_POLICIES = frozenset({"automatic", "core-review", "explicit"})


def _charter_paths(root: Path, producer: str) -> list[Path]:
    candidates = (
        root / ".saipen" / "extensions" / "subs" / f"{producer}.md",
        root / "extensions" / "subs" / f"{producer}.md",
    )
    return [p for p in candidates if p.is_file()]


def _charter_text(root: Path, producer: str) -> str | None:
    for charter in _charter_paths(root, producer):
        try:
            return charter.read_text(encoding="utf-8-sig")
        except OSError:
            continue
    return None


def current_role_revision(root: Path, producer: str) -> str:
    """The project-local charter revision for *producer*. Mirrors the
    canonical derivation; raises FreshnessError when nothing resolves."""
    for charter in _charter_paths(root, producer):
        return compute_role_revision(charter)
    for generic in (
        root / ".saipen" / "extensions" / "subs" / "PROTOCOL.md",
        root / "extensions" / "subs" / "PROTOCOL.md",
    ):
        if generic.is_file():
            return compute_generic_role_revision(generic)
    raise FreshnessError(
        f"no charter or generic PROTOCOL.md resolves for producer {producer!r}"
    )


def resolve_collect_policy(root: Path, sub_name: str) -> str | None:
    """The producer's consumption authority from its CURRENT effective
    charter metadata (PROTOCOL.md § 3.1). Never inferred from the sub name.
    None = the charter is missing a collect_policy or is unreadable."""
    text = _charter_text(root, sub_name)
    if text is None:
        return None
    m = re.search(r"(?m)^\s*collect_policy:\s*([a-z-]+)\s*$", text)
    if not m:
        return None
    policy = m.group(1).strip()
    return policy if policy in COLLECT_POLICIES else None


def check_package(
    root: Path,
    sub_name: str,
    entry,
) -> tuple[bool, str, str, dict]:
    """The full collect gate for one OUTBOX entry (strict-parsed).

    Returns ``(ok, message, kind, proof)`` where kind is one of ``ready``,
    ``reviewed`` (idempotent no-op), ``not-ready`` (draft/blocked/stale),
    ``incomplete``, ``stale``, ``malformed``. No main-project write may happen
    unless ok is True.

    On `ready`, `proof` is the immutable freshness proof the APPLY must
    revalidate under the canonical writer lock immediately before commit:
    source identity (head/tree/role) plus the exact OUTBOX and main-checkpoint
    hashes the decision was made from.
    """
    if getattr(entry, "errors", None):
        return (
            False,
            "malformed OUTBOX: " + "; ".join(entry.errors[:3]),
            "malformed",
            {},
        )
    status = (entry.status or "").strip()
    if status == "reviewed":
        return True, "already reviewed; no-op", "reviewed", {}
    if status == "":
        return False, "entry has no usable status field", "malformed", {}
    if status not in ("ready", "draft", "blocked", "stale"):
        return False, f"status {status!r} is not a known OUTBOX status", "malformed", {}
    if status != "ready":
        return (
            False,
            f"entry '{entry.entry_id}' is not ready (status: {status})",
            "not-ready",
            {},
        )

    fields = entry.fields
    missing = [
        f for f in protocol.PACKAGE_HANDOFF_FIELDS if not (fields.get(f) or "").strip()
    ]
    if missing:
        return (
            False,
            f"status: ready but missing {', '.join(sorted(missing))} "
            f"-- complete ready packages bind every handoff and freshness field",
            "incomplete",
            {},
        )
    for extra in ("summary", "critical"):
        if not (fields.get(extra) or "").strip():
            return (
                False,
                f"status: ready but missing **{extra}:** -- collect reads it "
                f"to decide what to do with the entry",
                "incomplete",
                {},
            )

    producer = (fields.get("producer") or "").strip()
    if producer != sub_name:
        return (
            False,
            f"entry producer {producer!r} != requested sub {sub_name!r}",
            "malformed",
            {},
        )

    # Source identity FAILS CLOSED: a package cannot be judged fresh if the
    # current identity cannot be computed.
    try:
        identity = compute_source_identity(root)
    except FreshnessError as exc:
        return False, f"source freshness computation BLOCKED: {exc}", "stale", {}

    head = (fields.get("source_head") or "").strip()
    if head != identity.source_head:
        return (
            False,
            f"source_head {head!r} != current source_head "
            f"{identity.source_head!r} -- package is stale",
            "stale",
            {},
        )
    fp = (fields.get("source_tree_fingerprint") or "").strip()
    if fp != identity.source_tree_fingerprint:
        return (
            False,
            f"source_tree_fingerprint {fp!r} != current "
            f"{identity.source_tree_fingerprint!r} -- the tree changed since "
            f"the package was produced (same HEAD or not), so it is stale",
            "stale",
            {},
        )

    rr = (fields.get("role_revision") or "").strip()
    try:
        current_rr = current_role_revision(root, sub_name)
    except FreshnessError as exc:
        return False, f"cannot derive current role_revision: {exc}", "stale", {}
    if rr != current_rr:
        return (
            False,
            f"role_revision {rr!r} != current charter revision "
            f"{current_rr!r} -- produced under a superseded role",
            "stale",
            {},
        )

    proof = {
        "source_head": head,
        "source_tree_fingerprint": fp,
        "role_revision": rr,
        "sub_name": sub_name,
        "entry_id": entry.entry_id,
        "outbox_hash": _hash_of(
            root
            / ".saipen"
            / "extensions"
            / "subs"
            / sub_name
            / "kitchen"
            / "OUTBOX.md"
        ),
        "state_hash": _hash_of(root / ".saipen" / "STATE.md"),
        "board_hash": _hash_of(root / ".saipen" / "BOARD.md"),
        "log_hash": _hash_of(root / ".saipen" / "LOG.md"),
    }
    return True, "package is complete, fresh and role-current", "ready", proof


def _hash_of(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(raw).hexdigest()[:16]


def critical_flag(entry) -> bool:
    """The TYPED critical value -- `true` | `false` exactly (the strict parser
    already refused anything else)."""
    return entry.critical is True
