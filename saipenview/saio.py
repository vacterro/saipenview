"""The canonical SAIOPS client bridge.

SAIPENVIEW is a CLIENT of the SAIPEN protocol, never a second implementation of
it. Every structural `.saipen/` mutation is committed through the canonical
engine's OperationPlan + APPLY pipeline (tools/saipen_engine in the resolved
`saipen_home`): OS writer lock, recovery preflight, immutable PREPARED journal,
ordered targets, byte + semantic verification, COMMITTED. Decisions are bound
to the exact snapshot whose hashes become the plan's preconditions.

When `saipen_home` is unreachable or the canonical engine cannot load, ALL
mutation FAILS CLOSED (SAIO_UNAVAILABLE) -- a viewer that cannot prove its
writes are canonical may not write at all.

The normalized result contract every mutation returns:
    {ok, code, message, changed_files, retryable, recovery_required, op_id}
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

from saipenview.textio import read_doc

# Viewer-side refusal codes (outside the canonical CODES set on purpose --
# these name failures the ENGINE cannot see: no canonical home, a boundary
# violation, a freshness proof that went stale between gate and apply).
SAIO_UNAVAILABLE = "SAIO_UNAVAILABLE"
BOUNDARY_VIOLATION = "BOUNDARY_VIOLATION"
STALE_FRESHNESS = "STALE_FRESHNESS"
MALFORMED_OUTBOX = "MALFORMED_OUTBOX"


class SaioUnavailable(Exception):
    """The canonical engine could not be resolved or loaded."""


_ENGINE_CACHE: dict[str, dict[str, object]] = {}


def _state_frontmatter(root: Path) -> dict[str, str]:
    state_path = root / ".saipen" / "STATE.md"
    if not state_path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in read_doc(state_path).splitlines():
        line = line.strip()
        if line.startswith("---") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip("\"'")
    return out


def resolve_home(root: Path) -> Path:
    """The project's `saipen_home` (STATE.md § 1.7 bootloader pointer)."""
    state = _state_frontmatter(root)
    if not state:
        raise SaioUnavailable(
            f"{root}: no .saipen/STATE.md -- cannot resolve saipen_home"
        )
    home = (state.get("saipen_home") or "").strip().strip("'\"")
    if not home:
        raise SaioUnavailable(
            f"{root}: STATE.md carries no saipen_home -- the "
            "canonical writer authority cannot be located"
        )
    home_path = Path(home)
    if not (home_path / "tools" / "saipen_engine").is_dir():
        raise SaioUnavailable(
            f"{root}: saipen_home {home!r} has no "
            "tools/saipen_engine -- clone the canonical "
            "SAIPEN repo there"
        )
    return home_path


def _load_codec_from(home: Path):
    """Load the canonical codec directly from a known home path (no root
    resolution needed -- used to re-encode bytes in a project whose STATE is
    not yet writable)."""
    tools = str(home / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import importlib as _il

    return _il.import_module("saipen_engine.codec")


def engine(root: Path) -> dict[str, object]:
    """Load (once per home) the canonical engine modules into the process.

    Returns {"operations", "plan", "journal", "lock", "fast_check", "codec",
    "freshness"}. The canonical tools/ dir is placed on sys.path so the
    package's own relative imports and the top-level `freshness` module both
    resolve.
    """
    home = resolve_home(root)
    key = str(home)
    cached = _ENGINE_CACHE.get(key)
    if cached is not None:
        return cached
    tools = str(home / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    loaded: dict[str, object] = {}
    try:
        loaded["engine_pkg"] = importlib.import_module("saipen_engine")
        loaded["operations"] = importlib.import_module("saipen_engine.operations")
        loaded["plan"] = importlib.import_module("saipen_engine.plan")
        loaded["journal"] = importlib.import_module("saipen_engine.journal")
        loaded["lock"] = importlib.import_module("saipen_engine.lock")
        loaded["fast_check"] = importlib.import_module("saipen_engine.fast_check")
        loaded["codec"] = importlib.import_module("saipen_engine.codec")
        loaded["freshness"] = importlib.import_module("freshness")
    except Exception as exc:  # noqa: BLE001 - fail closed on any load defect
        raise SaioUnavailable(f"{root}: canonical engine load failed: {exc}") from exc
    _ENGINE_CACHE[key] = loaded
    return loaded


def agent_for(root: Path) -> str:
    """The project's seat (STATE.agent) -- the identity mutations are recorded
    under. Refuses a placeholder the way the validator does."""
    agent = (_state_frontmatter(root).get("agent") or "").strip()
    if not agent or agent.lower() in (
        "id",
        "<name>",
        "agentid",
        "unknown",
        "agent",
        "name",
        "todo",
        "tbd",
        "your-agent-id",
        "<agent>",
        "none",
    ):
        raise SaioUnavailable(
            f"{root}: STATE.agent is not a real seat -- mutation identity unavailable"
        )
    return agent


def snapshot(root: Path, rel_paths: list[str]) -> dict[str, object]:
    """Read the exact bytes of `rel_paths` through the canonical codec.

    Returns {rel: Document} where Document carries raw_hash (the hash of the
    exact bytes read), text_norm, encoding/BOM/newline facts and encode().
    Decisions MUST be made from THIS snapshot; its raw_hash values become the
    plan's preconditions, so a decision is provably bound to the read.
    """
    codec = engine(root)["codec"]
    return {rel: codec.read_document(root / rel) for rel in rel_paths}


def plan(
    root: Path,
    operation: str,
    semantic_request: dict,
    targets: list[tuple[str, str, str, object]],
    preconditions: dict[str, str],
    read_deps: dict[str, str] | None = None,
    op_id: str | None = None,
    expected: dict | None = None,
    missing_paths: list[str] | None = None,
):
    """Build an immutable OperationPlan from one snapshot.

    `targets` is [(rel_path, role, new_text, doc)] where `doc` is the snapshot
    Document the decision was made from -- the plan's before/after hashes come
    from THAT read and the exact encoded bytes. `preconditions` maps rel ->
    raw_hash for every file the decision depended on. `missing_paths` names
    targets that did NOT exist at snapshot time (before-hash = the canonical
    journal's "" sentinel, so creating a file is not mistaken for a conflict
    and MISSING never equals empty). `expected` is the semantic success
    metadata (ticket/event/...) surfaced by APPLY on success. Returns the
    canonical OperationPlan; nothing is written.
    """
    ops = engine(root)["operations"]
    plan_builder = engine(root)["plan"]
    identity = ops._identity(root)
    missing_paths = set(missing_paths or ())
    built = []
    for rel, role, new_text, doc in targets:
        target = ops._target(doc, rel, role, new_text)
        if rel in missing_paths:
            # The canonical journal's sentinel for an ABSENT file is "" -- a
            # plan for a new file must carry that before-hash or recovery
            # misreads the missing target as a conflict. Missing != empty.
            target = plan_builder.TargetPlan(
                target.path, target.role, target.content, "", target.after_hash
            )
        built.append(target)
    merged_preconditions = dict(preconditions)
    merged_preconditions.update(read_deps or {})
    for rel in missing_paths:
        merged_preconditions[rel] = ""
    exp = {"ok": True, "code": operation.upper()}
    exp.update(expected or {})
    return plan_builder.build_plan(
        operation,
        agent_for(root),
        identity,
        semantic_request,
        merged_preconditions,
        built,
        exp,
        op_id=op_id,
    )


def _normalize(result, plan=None) -> dict:
    """Canonical Result / commit dict -> the one viewer failure contract.

    Handles both the canonical `Result` dataclass and the raw commit dict
    `run_mutation` returns. On success the plan's `expected` metadata
    (ticket/event/...) is surfaced so callers get the semantic identity of the
    commit, not just "COMMITTED"."""
    if isinstance(result, dict):
        ok = bool(result.get("ok"))
        code = result.get("code", "COMMITTED")
        message = result.get("detail") or result.get("message", "")
        changed = list(result.get("changed_files") or [])
        recovery = bool(result.get("recovery_required", False))
        op_id = result.get("op_id")
    else:
        ok = bool(result.ok)
        code = result.code
        message = result.message
        changed = list(result.changed_files)
        recovery = bool(result.recovery_required)
        op_id = result.op_id
    retryable = code in ("WRITER_BUSY", "STALE_STATE", "STALE_FRESHNESS")
    out = {
        "ok": ok,
        "code": code,
        "message": message,
        "changed_files": changed,
        "retryable": retryable,
        "recovery_required": recovery,
        "op_id": op_id,
    }
    if ok and plan is not None:
        out.update(
            {
                k: v
                for k, v in plan.expected.items()
                if k not in ("ok", "code", "message")
            }
        )
    return out


def apply(root: Path, operation_plan) -> dict:
    """APPLY a plan through the canonical lock + journal + recovery + verify.

    Returns the normalized result. No partial write is ever reported as
    success: any commit failure returns its own refusal (WRITER_BUSY /
    STALE_STATE / RECOVERY_REQUIRED / CONFLICT) with recovery_required set.
    """
    ops = engine(root)["operations"]
    try:
        result = ops.apply_plan(root, operation_plan)
    except SaioUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize any apply failure
        return {
            "ok": False,
            "code": "VALIDATION_FAILED",
            "message": f"apply failed: {exc}",
            "changed_files": [],
            "retryable": False,
            "recovery_required": False,
            "op_id": getattr(operation_plan, "op_id", None),
        }
    return _normalize(result, operation_plan)


def apply_with_precheck(
    root: Path, operation_plan, precheck=None, verification_policy: str = "core_fast"
) -> dict:
    """APPLY under the writer lock with a caller-supplied precheck.

    `precheck(root)` runs INSIDE the canonical writer lock, immediately before
    the journal is PREPARED -- the right place to revalidate a non-file proof
    (source identity, OUTBOX hash, boundary registry) whose freshness must
    hold AT COMMIT TIME, not merely at gate time. Returning a dict with
    `ok: False` refuses the mutation with zero canonical writes.

    `verification_policy` defaults to core_fast (structural ops). A raw
    hand-edit (file editor) uses `none`: byte-verify only, so a user repairing
    a non-conformant project is not blocked by the very state they are fixing.
    """
    journal = engine(root)["journal"]
    lock = engine(root)["lock"]
    root = Path(root)
    try:
        with lock.project_writer_lock(root):
            if precheck is not None:
                check = precheck(root)
                if check is not None and not check["ok"]:
                    return check
            commit = journal.run_mutation(
                root,
                operation_plan.op_id,
                operation_plan.operation,
                operation_plan.agent,
                operation_plan.project_identity,
                operation_plan.semantic_payload_hash,
                [
                    {
                        "path": t.path,
                        "role": t.role,
                        "content": t.content,
                        "before_hash": t.before_hash,
                        "after_hash": t.after_hash,
                    }
                    for t in operation_plan.targets
                ],
                preconditions=operation_plan.preconditions,
                read_preconditions={
                    p: h
                    for p, h in operation_plan.preconditions.items()
                    if p not in {t.path for t in operation_plan.targets}
                },
                verify=engine(root)["fast_check"].validate_project
                if verification_policy == "core_fast"
                else None,
                verification_policy=verification_policy,
            )
    except PermissionError:
        commit = {
            "ok": False,
            "code": "WRITER_BUSY",
            "detail": "another live writer holds the project lock",
        }
    except Exception as exc:  # noqa: BLE001 - normalize
        return {
            "ok": False,
            "code": "VALIDATION_FAILED",
            "message": f"apply failed: {exc}",
            "changed_files": [],
            "retryable": False,
            "recovery_required": False,
            "op_id": getattr(operation_plan, "op_id", None),
        }
    out = _normalize(commit, operation_plan)
    if commit.get("ok"):
        out["changed_files"] = [t.path for t in operation_plan.targets]
    return out


def recovery_status(root: Path) -> dict:
    """Unresolved canonical operations / conflicts that block new mutation."""
    journal = engine(root)["journal"]
    conflicts = journal.pending_conflicts(root)
    pending = journal.pending_ops(root)
    return {
        "ok": True,
        "conflicts": conflicts,
        "pending": pending,
        "blocked": bool(pending),
    }


def recover(root: Path, op_id: str | None = None) -> dict:
    """Recover pending canonical operations (roll-forward, conflict-safe)."""
    journal = engine(root)["journal"]
    try:
        if op_id:
            result = journal.recover(root, op_id)
        else:
            result = journal.auto_recover_pending(root)
    except Exception as exc:  # noqa: BLE001 - normalize
        return {
            "ok": False,
            "code": "VALIDATION_FAILED",
            "message": f"recover failed: {exc}",
            "changed_files": [],
            "retryable": False,
            "recovery_required": True,
        }
    return _normalize(result)


def writer_lock(root: Path):
    """The canonical OS writer lock (context manager)."""
    lock = engine(root)["lock"]
    return lock.project_writer_lock(root)


def source_identity(root: Path):
    """Current source identity via the canonical freshness primitive."""
    freshness = engine(root)["freshness"]
    return freshness.compute_source_identity(root)


# --- canonical ticket operations (delegation, never re-implementation) ------


def claim(root: Path, ticket_id: str, agent: str, explicit: bool = True) -> dict:
    ops = engine(root)["operations"]
    return _normalize(ops.apply_claim(root, ticket_id, agent, explicit=explicit))


def ticket_block(root: Path, ticket_id: str, agent: str, reason: str) -> dict:
    ops = engine(root)["operations"]
    return _normalize(ops.ticket_move(root, "block", ticket_id, agent, reason))


def ticket_unblock(root: Path, ticket_id: str, agent: str, decision: str) -> dict:
    ops = engine(root)["operations"]
    return _normalize(ops.ticket_move(root, "unblock", ticket_id, agent, decision))


def finish(root: Path, ticket_id: str, agent: str) -> dict:
    ops = engine(root)["operations"]
    return _normalize(ops.finish_ticket(root, ticket_id, agent))


def transition(
    root: Path, phase: str, agent: str, ticket: str | None = None, text: str = ""
) -> dict:
    ops = engine(root)["operations"]
    return _normalize(ops.transition_phase(root, phase, agent, ticket, text))


def source_hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def fingerprint_missing() -> str:
    """Typed identity for an ABSENT file: distinct from any existing file."""
    return "MISSING"


def fingerprint_file(path: Path) -> str:
    """Typed identity for an existing file: FILE\\0<sha256 of exact bytes>.

    Distinct from MISSING by construction -- an empty file and a missing file
    never compare equal, so a missing file cannot be silently treated as an
    empty one in a conflict identity."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return fingerprint_missing()
    return "FILE\0" + hashlib.sha256(raw).hexdigest()
