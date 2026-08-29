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
import re
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


def compute_source_identity(project_root):
    """Canonical source identity -- ONE freshness algorithm (the VIEW
    never re-implements git-delta framing). Fail-closed on any unreadable
    input; canonical failures surface as this module's FreshnessError."""
    from saipenview import saio

    try:
        return saio.source_identity(Path(project_root))
    except FreshnessError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed on any freshness failure
        raise FreshnessError(str(exc)) from exc


def compute_role_revision(charter_path) -> str:
    from saipenview import saio

    try:
        return saio.role_revision(Path(charter_path))
    except FreshnessError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed
        raise FreshnessError(str(exc)) from exc


def compute_generic_role_revision(protocol_path) -> str:
    from saipenview import saio

    try:
        return saio.generic_role_revision(Path(protocol_path))
    except FreshnessError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed
        raise FreshnessError(str(exc)) from exc


# --- the package gate -------------------------------------------------------

# Charter metadata: the closed set of consumption authorities (PROTOCOL.md
# § 3.1). `automatic` allows autonomous intake; `core-review` creates normal
# Core work and NEVER applies a payload directly; `explicit` refuses every
# autonomous sweep and requires an explicit named collect authorization.
COLLECT_POLICIES = frozenset({"automatic", "core-review", "explicit"})


# CORE-005: SubSaipen identifier validation. A sub name must be exactly one
# non-empty path segment -- no separators, no traversal, no absolute/drive/UNC.
_BAD_SUB_CHARS = frozenset("/\\")
_BAD_SUB_NAMES = frozenset({".", "..", ""})


def validate_sub_id(name: str) -> str | None:
    """Return None if *name* is a valid SubSaipen identifier, else an error
    message. A valid name is one non-empty segment: no separators, no
    traversal, no absolute/drive/UNC forms."""
    if not name or not name.strip():
        return "SubSaipen identifier is empty"
    name = name.strip()
    if name in _BAD_SUB_NAMES:
        return f"SubSaipen identifier {name!r} is not a valid name"
    # Reject path separators and traversal
    if any(c in name for c in _BAD_SUB_CHARS):
        return f"SubSaipen identifier {name!r} contains path separators"
    if ".." in name:
        return f"SubSaipen identifier {name!r} contains traversal"
    # Reject absolute paths and drive letters (C:\, /foo, UNC \\server)
    if len(name) >= 2 and name[1] == ":":
        return f"SubSaipen identifier {name!r} looks like an absolute/drive path"
    if name.startswith("\\\\"):
        return f"SubSaipen identifier {name!r} looks like a UNC path"
    return None


def _require_valid_sub_id(name: str) -> None:
    """Raise ValueError if *name* is not a valid SubSaipen identifier."""
    err = validate_sub_id(name)
    if err:
        raise ValueError(err)


def _charter_paths(root: Path, producer: str) -> list[Path]:
    _require_valid_sub_id(producer)
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
    _require_valid_sub_id(sub_name)
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

    # OUTBOX identity: canonical preferred, legacy fallback -- same resolution as parser
    canonical_outbox = (
        root / ".saipen" / "extensions" / "subs" / sub_name / "kitchen" / "OUTBOX.md"
    )
    legacy_outbox = root / "extensions" / "subs" / sub_name / "kitchen" / "OUTBOX.md"
    if canonical_outbox.is_file():
        outbox_hash = _hash_of(canonical_outbox)
        outbox_rel = f".saipen/extensions/subs/{sub_name}/kitchen/OUTBOX.md"
    elif legacy_outbox.is_file():
        outbox_hash = _hash_of(legacy_outbox)
        outbox_rel = f"extensions/subs/{sub_name}/kitchen/OUTBOX.md"
    else:
        outbox_hash = ""
        outbox_rel = f".saipen/extensions/subs/{sub_name}/kitchen/OUTBOX.md"
    proof = {
        "source_head": head,
        "source_tree_fingerprint": fp,
        "role_revision": rr,
        "sub_name": sub_name,
        "entry_id": entry.entry_id,
        "outbox_hash": outbox_hash,
        "outbox_rel": outbox_rel,
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
