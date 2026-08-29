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
import os
import re
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

# Authority-bearing STATE keys: a duplicated one MUST NOT pick a winner.
_AUTHORITY_STATE_KEYS = frozenset(
    {
        "saipen_home",
        "agent",
        "phase",
        "task",
        "last_event",
        "schema_version",
        "saipen_version",
        "mode",
        "transition_from",
    }
)


def _strict_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """Parse the DELIMITED STATE frontmatter WITHOUT last-write-wins: a
    duplicated authority-bearing key is a structural error (P1 #10), and
    an UNCLOSED frontmatter block is a structural error (P1 #9). Scans
    only the `---`-delimited head, never the Markdown body (a body line like
    `phase: example` inside prose must not trip the duplicate-key refusal).
    Returns (fields, errors)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, []
    body: list[str] = []
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        body.append(line)
    fields: dict[str, str] = {}
    errors: list[str] = []
    if not closed:
        errors.append("missing closing frontmatter delimiter")
        return fields, errors
    seen: set[str] = set()
    for line in body:
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in seen:
            if key in _AUTHORITY_STATE_KEYS:
                errors.append(f"duplicate authority key {key!r}")
            continue
        seen.add(key)
        fields[key] = value.strip().strip("\"'")
    return fields, errors


def _state_frontmatter(root: Path) -> dict[str, str]:
    """STATE frontmatter, refusing on duplicated authority keys."""
    state_path = root / ".saipen" / "STATE.md"
    if not state_path.is_file():
        return {}
    fields, errors = _strict_frontmatter(read_doc(state_path))
    if errors:
        raise SaioUnavailable(f"{root}: STATE.md " + "; ".join(errors))
    return fields


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
    # W2-002: check multi-home BEFORE mutating sys.path to prevent contamination
    key = str(home)
    if _ENGINE_CACHE:
        existing_key = next(iter(_ENGINE_CACHE.keys()))
        if existing_key.lower() != key.lower():
            raise SaioUnavailable(
                f"MULTI-HOME CONTAMINATION BLOCKED: engine already loaded from "
                f"{existing_key}. Cannot load codec from distinct home {key}."
            )
    tools = str(home / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import importlib as _il

    return _il.import_module("saipen_engine.codec")


def engine(root: Path) -> dict[str, object]:
    """Load the canonical engine modules into the process.

    Exactly ONE canonical SAIPEN_HOME is supported per process.
    Attempting to load a distinct home fails closed to prevent
    sys.modules identity contamination (repair mission P0).

    Returns {"operations", "plan", "journal", "log", "lock", "fast_check",
    "codec", "freshness"}.
    """
    home = resolve_home(root)
    key = str(home).lower()
    cached = _ENGINE_CACHE.get(key)
    if cached is not None and "operations" in cached:
        return cached

    if _ENGINE_CACHE:
        # A different home was already loaded
        existing = next(iter(_ENGINE_CACHE.keys()))
        if existing.lower() != key.lower():
            raise RuntimeError(
                f"MULTI-HOME CONTAMINATION BLOCKED: Process already loaded saipen_engine "
                f"from {existing}. Cannot concurrently load distinct home {key} "
                f"because Python sys.modules global identity is module-name based."
            )

    tools = str(home / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    loaded: dict[str, object] = {}
    try:
        loaded["engine_pkg"] = importlib.import_module("saipen_engine")
        loaded["operations"] = importlib.import_module("saipen_engine.operations")
        loaded["plan"] = importlib.import_module("saipen_engine.plan")
        loaded["journal"] = importlib.import_module("saipen_engine.journal")
        loaded["log"] = importlib.import_module("saipen_engine.log")
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
    plan_builder = engine(root)["plan"]
    journal = engine(root)["journal"]
    import importlib

    paths_mod = importlib.import_module("saipen_engine.paths")
    identity = paths_mod.project_identity(root)
    
    missing_paths = set(missing_paths or ())
    built = []
    for rel, role, new_text, doc in targets:
        encoded_content = doc.encode(new_text)
        after_hash = journal.hash_bytes(encoded_content)
        target = plan_builder.TargetPlan(
            path=rel,
            role=role,
            content=encoded_content,
            before_hash=doc.raw_hash,
            after_hash=after_hash,
        )
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


def normalize(result) -> dict:
    """PUBLIC wrapper of the one Result adapter: a canonical `Result` dataclass
    or a raw commit dict -> the normalized viewer contract. The ONLY place the
    viewer probes a canonical result; never getattr(...) with an eager dict
    default."""
    return _normalize(result)


def refusal_message(result) -> str | None:
    """One adapter for the UI: None when *result* is a canonical success,
    else its human message (or code when the message is empty)."""
    norm = normalize(result)
    if norm["ok"]:
        return None
    return norm["message"] or norm["code"]


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


def apply(
    root: Path,
    operation_plan,
    precheck=None,
    verification_policy: str = "core_fast",
) -> dict:
    """APPLY a plan through the canonical writer lock + journal + recovery.

    `precheck(root)` runs INSIDE the canonical writer lock, immediately before
    the journal is PREPARED -- the right place to revalidate a non-file proof
    (source identity, OUTBOX hash, boundary registry) whose freshness must
    hold AT COMMIT TIME, not merely at gate time. Returning a dict with
    `ok: False` refuses the mutation with zero canonical writes.

    `verification_policy` defaults to core_fast (structural ops). A raw
    hand-edit (file editor) uses `none`: byte-verify only, so a user repairing
    a non-conformant project is not blocked by the very state they are fixing.

    Returns the normalized result. No partial write is ever reported as
    success: any commit failure returns its own refusal (WRITER_BUSY /
    STALE_STATE / RECOVERY_REQUIRED / CONFLICT) with recovery_required set.
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
    except Exception as exc:  # noqa: BLE001 - normalize any apply failure
        # A raised exception AFTER the journal was PREPARED means real journal
        # debt exists: report RECOVERY_REQUIRED with the actual pending ops,
        # never a hardcoded clean failure.
        try:
            debt = pending_ops(root)
        except Exception:  # noqa: BLE001
            debt = None
        if debt:
            return {
                "ok": False,
                "code": "RECOVERY_REQUIRED",
                "message": f"apply raised {exc.__class__.__name__} after the "
                "journal was prepared; pending operation(s) must be "
                "recovered",
                "changed_files": [],
                "retryable": False,
                "recovery_required": True,
                "op_id": getattr(operation_plan, "op_id", None),
                "pending_op_ids": [p.get("op_id") for p in debt],
            }
        return {
            "ok": False,
            "code": "INTERNAL_ERROR",
            "message": f"apply failed before any journal write: {exc}",
            "changed_files": [],
            "retryable": False,
            "recovery_required": False,
            "op_id": getattr(operation_plan, "op_id", None),
        }
    out = _normalize(commit, operation_plan)
    if commit.get("ok"):
        out["changed_files"] = [t.path for t in operation_plan.targets]
    return out


def apply_with_precheck(
    root: Path, operation_plan, precheck=None, verification_policy: str = "core_fast"
) -> dict:
    """Back-compat alias: `apply` now carries precheck + policy."""
    return apply(
        root, operation_plan, precheck=precheck, verification_policy=verification_policy
    )


def pending_ops(root: Path) -> list[dict]:
    """Every UNRESOLVED canonical operation journal for a project (used by the
    recovery-aware exception normalizer to report real journal debt)."""
    journal = engine(root)["journal"]
    return journal.pending_ops(root)


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
    """Current source identity via the canonical freshness primitive.
    Stateless: hashes ANY directory (a `.saipen/` is not required), exactly
    like the canonical compute_source_identity. Resolved from the project's
    own saipen_home when the path is a project root (carries STATE.md) or
    sits under one, else env/hardcoded home."""
    home = None
    if isinstance(root, Path):
        r = _root_for_saipen_path(root)
        if r is None and (Path(root) / ".saipen" / "STATE.md").is_file():
            r = Path(root)
        if r is not None:
            try:
                home = resolve_home(r)
            except SaioUnavailable:
                home = None
    return _freshness_module(home).compute_source_identity(root)


def _root_for_saipen_path(path: Path) -> Path | None:
    """Derive the project root from any path under some `<root>/.saipen/`."""
    p = Path(path).resolve()
    for part in p.parents:
        if part.name == ".saipen":
            return part.parent
    return None


def _freshness_module(root: Path | None = None):
    """The canonical freshness module from the project's OWN `saipen_home`
    (STATE.md § 1.7) when a root is resolvable, else any reachable SAIPEN home
    (SAIPEN_HOME env, then the known local canonical checkout). The freshness
    authority MUST match the project's declared canonical home -- a project
    pinned to one protocol version must hash roles with that version, not with
    whatever the machine happens to have on PATH (T-204 review finding). A
    project that declares NO home falls back to env/machine resolution (its
    writer authority would fail the same way, but stateless hashing still
    works)."""
    if root is not None:
        try:
            home = resolve_home(root)
        except SaioUnavailable:
            home = None
        if home is not None:
            return _load_freshness_from(home)
    env = os.environ.get("SAIPEN_HOME")
    for home in ([Path(env)] if env else []) + [
        Path(r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN"),
    ]:
        if (home / "tools" / "freshness.py").is_file():
            return _load_freshness_from(home)
    raise SaioUnavailable("canonical SAIPEN home unreachable for freshness")


def _load_freshness_from(home: Path):
    """Load freshness from exactly one canonical home.

    CORE-008: The cache lookup uses the normalized home identity. A second
    distinct home is refused when a different home is already loaded in the
    same process, to prevent sys.modules global identity contamination.
    """
    import importlib as _il

    # W2-002: check multi-home BEFORE mutating sys.path
    key = str(home)
    if _ENGINE_CACHE:
        existing_key = next(iter(_ENGINE_CACHE.keys()))
        if existing_key.lower() != key.lower():
            raise SaioUnavailable(
                f"MULTI-HOME CONTAMINATION BLOCKED: freshness already loaded from "
                f"{existing_key}. Cannot load from distinct home {key} because "
                f"Python sys.modules is global by name."
            )
    tools = str(home / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    cached = _ENGINE_CACHE.get(key)
    if cached is not None and "_freshness_only" in cached:
        return cached["_freshness_only"]
    # Load into a private slot, never a partial engine cache: engine() checks
    # for a COMPLETE module set, so a half-built cache can never leak out.
    mod = _il.import_module("freshness")
    _ENGINE_CACHE.setdefault(key, {})["_freshness_only"] = mod
    return mod


def role_revision(charter: Path) -> str:
    """Canonical role-charter revision (stateless hashing), resolved from the
    project's own saipen_home when the charter sits under one."""
    return _freshness_module(_root_for_saipen_path(charter)).compute_role_revision(
        charter
    )


def generic_role_revision(protocol_path: Path) -> str:
    """Canonical generic PROTOCOL.md role revision (stateless hashing),
    resolved from the project's own saipen_home when the path sits under one."""
    return _freshness_module(
        _root_for_saipen_path(protocol_path)
    ).compute_generic_role_revision(protocol_path)


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


def fingerprint_bytes(content: bytes) -> str:
    """Typed identity for EXACT bytes the app wrote: FILE\\0<sha256>. Same
    format as fingerprint_file but computed from known bytes -- the caller
    registering a self-write must fingerprint what IT wrote, never a post-lock
    disk re-read that could have been overwritten by an external writer
    (T-204 review finding)."""
    return "FILE\0" + hashlib.sha256(content).hexdigest()


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


# --- canonical ID allocation (the ONE authority, incl. sealed history) --------

_SEG_RE = re.compile(r"LOG-(\d+)\.md$")


def _sealed_log_text(root: Path) -> str:
    """Only the sealed LOG segments (numeric order), joined as the canonical
    tail machinery sees them. Sealed segments are immutable by definition, so
    reading them fresh at allocation time never violates snapshot binding."""
    root = Path(root)
    parts: list[str] = []
    seg_dir = root / ".saipen" / "logs"
    if seg_dir.is_dir():
        segs = sorted(
            (p for p in seg_dir.glob("LOG-*.md") if _SEG_RE.match(p.name)),
            key=lambda p: int(_SEG_RE.match(p.name).group(1)),
        )
        codec = engine(root)["codec"]
        for seg in segs:
            parts.append(codec.read_document(seg).text_norm + "\n")
    return "\n".join(parts)


def full_log_text(root: Path) -> str:
    """Sealed LOG segments (numeric order) + the active LOG, joined as the
    canonical tail machinery sees them. Allocation must NEVER depend on the
    active file alone: a fresh active LOG after rotation still derives its
    tail from the sealed segments."""
    root = Path(root)
    sealed = _sealed_log_text(root).rstrip("\n")
    active = engine(root)["codec"].read_document(root / ".saipen" / "LOG.md").text_norm
    return (sealed + "\n" if sealed else "") + active


def next_ticket_id(root: Path, board_text: str, log_text: str | None = None) -> int:
    """The next production ticket ID via the canonical allocator: scans BOARD
    AND LOG (full sequence incl. sealed), excludes the synthetic fixture
    namespace (T-998/T-999). Never a VIEW-local copy of the rule.

    `log_text` is the ACTIVE log snapshot the caller already holds; the sealed
    segments are always merged in (immutable), so a caller-supplied active text
    can never bypass the sealed history (T-204 review finding)."""
    ops = engine(root)["operations"]
    if log_text is None:
        log_text = full_log_text(root)
    else:
        sealed = _sealed_log_text(root).rstrip("\n")
        log_text = (sealed + "\n" if sealed else "") + log_text
    return ops.next_ticket_id(board_text, log_text)


def event_tail(root: Path, log_text: str | None = None) -> int:
    """The ACTUAL current event tail (max E-### across sealed + active) -- the
    value STATE.last_event MUST equal. Never bumps to a nonexistent id."""
    log = engine(root)["log"]
    if log_text is None:
        log_text = full_log_text(root)
    else:
        sealed = _sealed_log_text(root).rstrip("\n")
        log_text = (sealed + "\n" if sealed else "") + log_text
    return log.log_tail_event(log_text) or 0


def next_event_id(root: Path, log_text: str | None = None) -> int:
    """The next event ID: the canonical tail (actual max E-### across sealed +
    active, order-independent) + 1. Same sealed-merge contract as
    next_ticket_id."""
    log = engine(root)["log"]
    if log_text is None:
        log_text = full_log_text(root)
    else:
        sealed = _sealed_log_text(root).rstrip("\n")
        log_text = (sealed + "\n" if sealed else "") + log_text
    tail = log.log_tail_event(log_text)
    return (tail or 0) + 1
